"""Gold predictions from a frozen price model (MODEL-06 / MODEL-07).

Scoring never fits anything. It loads a persisted artifact whose identity is pinned
in ``FROZEN_MODELS``, checks it against the code's feature contract, and produces one
row per input listing with a baseline prediction (frozen lookup), a model prediction
and, where a valid actual price exists, the errors.

Residual direction: ``signed_residual_eur = model_prediction_eur - actual_price_eur``.
Negative means the model under-predicts, positive means it over-predicts.

pandas/numpy/scikit-learn only; notebooks convert Spark frames with ``toPandas()``.
"""

import hashlib
import io
import math
from datetime import date, datetime

import numpy as np
import pandas as pd

from airbnb import price_model as pm
from airbnb.model import LEVEL_CELL, LOOKUP_COLUMNS, PRICE_COL, _valid_positive, predict_baseline

SCORING_VERSION = "score-v1"
PREDICTION_SCHEMA_VERSION = "predictions-v1"
KEYS = ("city", "snapshot_date", "listing_id")
TABLE_KEYS = (*KEYS, "model_version")

# Values of evaluation_split in the predictions table.
SPLIT_TRAIN, SPLIT_TEST, SPLIT_EXCLUDED, SPLIT_UNSEEN = "train", "test", "excluded", "unseen"
# prediction_status
STATUS_WITH_ACTUAL = "scored_with_actual"   # model prediction and errors present
STATUS_NO_ACTUAL = "scored_no_actual"       # model prediction present, no valid actual price
STATUS_NOT_SCORED = "not_scored"            # no model prediction; see scoring_exclusion_reason
# evaluation_exclusion_reason (null when errors are present)
EVAL_NO_ACTUAL = "no_valid_actual_price"
EVAL_NOT_IN_SPLIT = "not_in_evaluation_split"
EVAL_NOT_SCORED = "model_not_scored"
# scoring_exclusion_reason (null when the model scored the row)
SCORE_NON_FINITE = "non_finite_model_prediction"
SCORE_NON_POSITIVE = "non_positive_model_prediction"

# Pinned identity of every frozen model. Scoring refuses anything that does not match.
# Values come from the MODEL-04/05 runs recorded in docs/model_selection.md.
FROZEN_MODELS = {
    "price-v1": {
        "model_version": "price-v1",
        "artifact_path": "/Volumes/{catalog}/airbnb_gold/model_artifacts/price-v1/model.joblib",
        "artifact_sha256": "c0416cde7f652342ce5217a936a6aa0a60d2476cc059c7e970b0c8001640fb2c",
        "artifact_bytes": 1484150,
        "mlflow_run_id": "a08250c6bcb5415c9591c6427e3d6bf7",
        "spec_sha256": "acd5e6e0e6a0badec0d34b4d2266c6485bba6135c679d92169db8a419992ea99",
        "selection_record_sha256": "9122ca565f036895a0b41fff61f1ac39bfa5066ea0a4ef8195bb8c0402af49db",
        "selected_candidate": "hgb_leaves_31_iter_400",
        "selected_family": "hgb_log",
        "selected_params": {"l2_regularization": 1.0, "learning_rate": 0.05, "max_iter": 400,
                            "max_leaf_nodes": 31, "min_samples_leaf": 40},
        "random_seed": 20261111,
        "train_code_revision": "d1c2bd6",
        "sklearn_version": "1.7.2",
        "features": list(pm.FEATURES),
        "training_snapshots": {"milan": "2026-09-19", "florence": "2026-09-19"},
        "split_salt": "airbnb-v1",
        "split_counts": {"milan": {"train": 17255, "test": 4399, "excluded": 3684},
                         "florence": {"train": 9684, "test": 2464, "excluded": 1423}},
        "split_fingerprint": "d4625414b6181cecf5de7548b376d77377b500b5e758f0a49236a356ae00a880",
        "baseline_version": "airbnb-v1",
        "baseline_lookup_rows": 44,
        "baseline_lookup_fingerprint": "0ca4b685a4b85babccc0810105eb35c074b34808f28d1a54d4012149b987b65c",
        # Official held-out MAE (test_all_valid_positive_price), from airbnb_gold.model_evaluation.
        "official_test_n": {"milan": 4399, "florence": 2464, "milan+florence": 6863},
        "official_test_mae": {
            "model": {"milan": 75.72109460621044, "florence": 76.17608368869547, "milan+florence": 75.88444781898083},
            "baseline": {"milan": 94.37535348942943, "florence": 97.41181412337663, "milan+florence": 95.46552382340084},
        },
    },
}

# Output schema. Order is the table's column order.
PREDICTION_SCHEMA = (
    ("city", "string"),
    ("snapshot_date", "date"),
    ("listing_id", "bigint"),
    ("model_version", "string"),
    ("scoring_version", "string"),
    ("prediction_schema_version", "string"),
    ("model_artifact_sha256", "string"),
    ("mlflow_run_id", "string"),
    ("baseline_version", "string"),
    ("split_salt", "string"),
    ("evaluation_split", "string"),
    ("actual_price_eur", "double"),
    ("baseline_prediction_eur", "double"),
    ("baseline_fallback_level", "string"),
    ("model_prediction_eur", "double"),
    ("absolute_error_eur", "double"),
    ("signed_residual_eur", "double"),
    ("baseline_absolute_error_eur", "double"),
    ("baseline_signed_residual_eur", "double"),
    ("prediction_status", "string"),
    ("evaluation_exclusion_reason", "string"),
    ("scoring_exclusion_reason", "string"),
    ("scoring_run_id", "string"),
    ("scored_at", "timestamp"),
    ("source_feature_table_version", "bigint"),
)
PREDICTION_COLUMNS = tuple(name for name, _ in PREDICTION_SCHEMA)
# Run metadata; everything else must be identical for a rerun to be a no-op.
RUN_METADATA_COLUMNS = ("scoring_run_id", "scored_at", "source_feature_table_version")
CONTENT_COLUMNS = tuple(c for c in PREDICTION_COLUMNS if c not in RUN_METADATA_COLUMNS)


def spark_schema_ddl():
    return ", ".join(f"{name} {kind}" for name, kind in PREDICTION_SCHEMA)


class FrozenModelError(RuntimeError):
    """The artifact, contract or reference data do not match the frozen model."""


# --------------------------------------------------------------------------- #
# Frozen model identity
# --------------------------------------------------------------------------- #

def frozen_model(model_version):
    if model_version not in FROZEN_MODELS:
        raise FrozenModelError(f"{model_version!r} is not a frozen model version; known: {sorted(FROZEN_MODELS)}")
    return FROZEN_MODELS[model_version]


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def load_artifact(data, frozen):
    """Unpickle artifact bytes after checking their SHA-256 against the frozen record."""
    import joblib

    digest = sha256_bytes(data)
    if digest != frozen["artifact_sha256"]:
        raise FrozenModelError(f"artifact sha256 {digest} != frozen {frozen['artifact_sha256']}; refusing to score")
    return joblib.load(io.BytesIO(data))


def check_artifact_record(record, frozen):
    """Compare a ``model_artifacts`` row (dict) with the frozen record."""
    pairs = {
        "artifact_sha256": "artifact_sha256", "spec_sha256": "spec_sha256",
        "selection_record_sha256": "selection_record_sha256", "selected_candidate": "selected_candidate",
        "selected_family": "selected_family", "sklearn_version": "sklearn_version", "mlflow_run_id": "mlflow_run_id",
    }
    diffs = {k: (record.get(k), frozen[v]) for k, v in pairs.items() if record.get(k) != frozen[v]}
    if diffs:
        raise FrozenModelError(f"model_artifacts row differs from the frozen record: {diffs}")


def check_model_contract(model, frozen, sklearn_version=None):
    """Refuse to score unless the code, the artifact and the frozen record describe the same model."""
    problems = []
    code_spec = pm.sha256_text(pm.canonical_json(pm.model_spec()))
    if code_spec != frozen["spec_sha256"]:
        problems.append(f"code spec_sha256 {code_spec} != frozen {frozen['spec_sha256']} (features/preprocessing changed)")
    if list(pm.FEATURES) != list(frozen["features"]):
        problems.append("code FEATURES differ from the frozen feature list")
    names = list(getattr(model, "feature_names_in_", []))
    if names != list(frozen["features"]):
        problems.append(f"artifact was fitted on columns {names}, frozen contract is {frozen['features']}")
    try:
        estimator = model.regressor_.named_steps["model"]
    except (AttributeError, KeyError):
        problems.append("artifact is not a fitted TransformedTargetRegressor(Pipeline(prep, model))")
    else:
        params = estimator.get_params()
        wrong = {k: (params.get(k), v) for k, v in frozen["selected_params"].items() if params.get(k) != v}
        if wrong:
            problems.append(f"artifact hyperparameters differ from the locked selection: {wrong}")
        if frozen["selected_family"] == "hgb_log" and params.get("random_state") != frozen["random_seed"]:
            problems.append("artifact random_state differs from the locked seed")
    if sklearn_version is not None and sklearn_version != frozen["sklearn_version"]:
        problems.append(f"scikit-learn {sklearn_version} != {frozen['sklearn_version']} used to write the artifact")
    if problems:
        raise FrozenModelError("; ".join(problems))


def split_fingerprint(split):
    """SHA-256 over sorted ``city|snapshot_date|listing_id|evaluation_split`` lines (matches the SQL in the docs)."""
    lines = sorted(
        f"{c}|{_date_text(d)}|{int(i)}|{'' if s is None or (isinstance(s, float) and math.isnan(s)) else s}"
        for c, d, i, s in zip(split["city"], split["snapshot_date"], split["listing_id"], split["evaluation_split"])
    )
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def lookup_fingerprint(lookup):
    """SHA-256 over sorted lookup lines, medians in micro-EUR (matches the SQL in the docs)."""
    lines = sorted(
        f"{lvl}|{'' if _is_null(r) else r}|{'' if _is_null(a) else int(a)}|{int(round(float(m) * 1e6))}|{int(n)}"
        for lvl, r, a, m, n in zip(lookup["baseline_level"], lookup["room_type"], lookup["accommodates"],
                                   lookup["median_price_eur"], lookup["n_train"])
    )
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def check_reference_data(frozen, lookup, split=None):
    """The baseline lookup (and, when given, the full training split) must be the frozen ones."""
    lookup_fp = lookup_fingerprint(lookup)
    if len(lookup) != frozen["baseline_lookup_rows"] or lookup_fp != frozen["baseline_lookup_fingerprint"]:
        raise FrozenModelError(f"baseline lookup is not the frozen {frozen['baseline_version']} ({len(lookup)} rows, {lookup_fp})")
    if split is not None:
        split_fp = split_fingerprint(split)
        if split_fp != frozen["split_fingerprint"]:
            raise FrozenModelError(f"persisted split fingerprint {split_fp} != frozen {frozen['split_fingerprint']}")


def _is_null(value):
    return value is None or value is pd.NA or (isinstance(value, float) and math.isnan(value))


def _date_text(value):
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return date.fromisoformat(str(value)[:10]).isoformat()


# --------------------------------------------------------------------------- #
# MODEL-07 entry point: score any configured city with a frozen model
# --------------------------------------------------------------------------- #

def score_listings(features, model, frozen, lookup, split=None, *, scoring_run_id, scored_at,
                   source_feature_table_version=None):
    """Return one prediction row per row of ``features`` (no row is dropped).

    ``features``: ``model_features`` rows for one or more city/snapshots (keys, ``price_eur``
    and the frozen feature columns). ``split``: persisted ``model_split`` rows; required for a
    training city at its training snapshot and forbidden otherwise. Any other city/snapshot is
    labelled ``unseen`` and every row with a valid price is evaluated. Nothing is fitted.
    """
    missing = [c for c in (*KEYS, PRICE_COL, *frozen["features"]) if c not in features.columns]
    if missing:
        raise FrozenModelError(f"model_features lacks columns required by the frozen contract: {missing}")
    if features[list(KEYS)].isna().any().any():
        raise ValueError("score_listings: null key values (silver key contract)")
    frame = features.reset_index(drop=True).copy()
    frame["snapshot_date"] = frame["snapshot_date"].map(lambda v: date.fromisoformat(_date_text(v)))
    frame["listing_id"] = frame["listing_id"].astype("int64")
    if frame.duplicated(list(KEYS)).any():
        raise ValueError(f"score_listings: {int(frame.duplicated(list(KEYS)).sum())} duplicated (city, snapshot_date, listing_id) keys")

    frame["evaluation_split"] = _evaluation_split(frame, frozen, split)

    # Frozen baseline: room_type x accommodates -> room_type -> overall.
    frame = predict_baseline(frame, lookup, prediction_col="baseline_prediction_eur", level_col="baseline_fallback_level")

    # Frozen model: predict only, never fit.
    raw = np.asarray(model.predict(pm.model_inputs(frame)), dtype="float64")
    reason = np.where(~np.isfinite(raw), SCORE_NON_FINITE, np.where(raw <= 0, SCORE_NON_POSITIVE, None))
    scored = pd.isna(pd.Series(reason))
    frame["model_prediction_eur"] = np.where(scored, raw, np.nan)
    frame["scoring_exclusion_reason"] = reason

    actual = _valid_positive(frame[PRICE_COL])
    frame["actual_price_eur"] = actual
    evaluable = actual.notna() & frame["evaluation_split"].isin([SPLIT_TRAIN, SPLIT_TEST, SPLIT_UNSEEN])
    with_errors = evaluable & scored
    frame["signed_residual_eur"] = (frame["model_prediction_eur"] - actual).where(with_errors)
    frame["absolute_error_eur"] = frame["signed_residual_eur"].abs()
    frame["baseline_signed_residual_eur"] = (frame["baseline_prediction_eur"] - actual).where(evaluable)
    frame["baseline_absolute_error_eur"] = frame["baseline_signed_residual_eur"].abs()

    frame["prediction_status"] = np.where(~scored, STATUS_NOT_SCORED, np.where(with_errors, STATUS_WITH_ACTUAL, STATUS_NO_ACTUAL))
    frame["evaluation_exclusion_reason"] = np.select(
        [~scored, actual.isna(), ~evaluable], [EVAL_NOT_SCORED, EVAL_NO_ACTUAL, EVAL_NOT_IN_SPLIT], default=None
    )

    frame = frame.assign(
        model_version=frozen["model_version"], scoring_version=SCORING_VERSION,
        prediction_schema_version=PREDICTION_SCHEMA_VERSION, model_artifact_sha256=frozen["artifact_sha256"],
        mlflow_run_id=frozen["mlflow_run_id"], baseline_version=frozen["baseline_version"],
        split_salt=frozen["split_salt"], scoring_run_id=str(scoring_run_id), scored_at=scored_at,
        source_feature_table_version=source_feature_table_version,
    )
    out = frame[list(PREDICTION_COLUMNS)].copy()
    for col in ("evaluation_exclusion_reason", "scoring_exclusion_reason"):
        out[col] = out[col].astype(object).where(out[col].notna(), None)
    if len(out) != len(features):
        raise AssertionError("score_listings changed the number of rows")
    return out


def _evaluation_split(frame, frozen, split):
    training = frozen["training_snapshots"]
    is_training = frame.apply(lambda r: training.get(r["city"]) == r["snapshot_date"].isoformat(), axis=1)
    training_city_other_snapshot = frame["city"].isin(list(training)) & ~is_training
    if training_city_other_snapshot.any():
        raise FrozenModelError(
            "a training city at a snapshot other than its training snapshot cannot be labelled train/test/unseen: "
            f"{sorted(set(zip(frame.loc[training_city_other_snapshot, 'city'], frame.loc[training_city_other_snapshot, 'snapshot_date'].map(str))))}"
        )
    labels = pd.Series(SPLIT_UNSEEN, index=frame.index, dtype=object)
    if not is_training.any():
        if split is not None and len(split):
            raise FrozenModelError("a persisted split was passed for rows that are not training rows")
        return labels
    if split is None:
        raise FrozenModelError("training-city rows need the persisted split")
    s = split[list(KEYS) + ["evaluation_split"]].copy()
    s["snapshot_date"] = s["snapshot_date"].map(lambda v: date.fromisoformat(_date_text(v)))
    s["listing_id"] = s["listing_id"].astype("int64")
    if s.duplicated(list(KEYS)).any():
        raise FrozenModelError("persisted split has duplicated keys")
    joined = frame.loc[is_training, list(KEYS)].merge(s, on=list(KEYS), how="left", indicator=True)
    if (joined["_merge"] != "both").any():
        raise FrozenModelError(f"{int((joined['_merge'] != 'both').sum())} training-city listings have no persisted split row")
    scoped = set(zip(frame.loc[is_training, "city"], frame.loc[is_training, "snapshot_date"]))
    in_scope = [(c, d) in scoped for c, d in zip(s["city"], s["snapshot_date"])]
    if int(sum(in_scope)) != int(is_training.sum()):
        raise FrozenModelError("persisted split and model_features do not cover the same listings")
    values = joined["evaluation_split"].map(lambda v: SPLIT_EXCLUDED if _is_null(v) else v).to_numpy()
    labels.loc[is_training[is_training].index] = values
    if not set(labels.loc[is_training]).issubset({SPLIT_TRAIN, SPLIT_TEST, SPLIT_EXCLUDED}):
        raise FrozenModelError(f"unexpected split labels {sorted(set(labels.loc[is_training]))}")
    return labels


# --------------------------------------------------------------------------- #
# Checks on a predictions frame
# --------------------------------------------------------------------------- #

def official_test_metrics(predictions, frozen):
    """MAE of model and baseline on the persisted test rows, per training city and pooled."""
    test = predictions[predictions["evaluation_split"] == SPLIT_TEST]
    if test["model_prediction_eur"].isna().any() or test["actual_price_eur"].isna().any():
        raise FrozenModelError("some official test rows have no model prediction or no valid actual price")
    cities = list(frozen["training_snapshots"])
    test = test.sort_values(["city", "listing_id"])  # same row order as the MODEL-05 evaluation
    groups = [(c, test["city"] == c) for c in cities] + [("+".join(cities), test["city"].isin(cities))]
    out = {"n": {}, "model": {}, "baseline": {}}
    for name, mask in groups:
        out["n"][name] = int(mask.sum())
        out["model"][name] = float(test.loc[mask, "absolute_error_eur"].mean())
        out["baseline"][name] = float(test.loc[mask, "baseline_absolute_error_eur"].mean())
    return out


def check_official_metrics(metrics, frozen, tolerance=1e-9):
    """Return the largest absolute difference to the official numbers; raise if it exceeds ``tolerance``."""
    if metrics["n"] != frozen["official_test_n"]:
        raise FrozenModelError(f"official test population changed: {metrics['n']} != {frozen['official_test_n']}")
    diffs = [abs(metrics[k][g] - frozen["official_test_mae"][k][g]) for k in ("model", "baseline") for g in metrics["n"]]
    worst = max(diffs)
    if worst > tolerance:
        raise FrozenModelError(f"scored test rows do not reproduce the official MAE (max difference {worst:.3e} EUR)")
    return worst


def reconcile(predictions, features):
    """Row-level reconciliation of a predictions frame against its input features."""
    keys = list(KEYS)
    dup = int(predictions.duplicated([*keys, "model_version"]).sum())
    pk = predictions[keys].assign(snapshot_date=lambda d: d["snapshot_date"].map(_date_text), listing_id=lambda d: d["listing_id"].astype("int64"))
    fk = features[keys].assign(snapshot_date=lambda d: d["snapshot_date"].map(_date_text), listing_id=lambda d: d["listing_id"].astype("int64"))
    merged = fk.merge(pk.drop_duplicates(), on=keys, how="outer", indicator=True)
    return {
        "feature_rows": int(len(features)), "prediction_rows": int(len(predictions)), "duplicate_keys": dup,
        "missing_from_predictions": int((merged["_merge"] == "left_only").sum()),
        "extra_in_predictions": int((merged["_merge"] == "right_only").sum()),
        "baseline_null": int(predictions["baseline_prediction_eur"].isna().sum()),
    }


def counts(predictions, columns):
    grouped = predictions.assign(**{c: predictions[c].astype(object).where(predictions[c].notna(), "NULL") for c in columns})
    return {"|".join(str(v) for v in k) if isinstance(k, tuple) else str(k): int(n)
            for k, n in grouped.groupby(list(columns)).size().items()}


# --------------------------------------------------------------------------- #
# Version-safe, idempotent writes
# --------------------------------------------------------------------------- #

def _canonical_rows(frame):
    def norm(value):
        if _is_null(value):
            return None
        if isinstance(value, (datetime, pd.Timestamp, date)):
            return _date_text(value)
        if isinstance(value, (np.integer,)):
            return int(value)
        if isinstance(value, (np.floating, float)):
            return float(value)
        return value

    cols = list(CONTENT_COLUMNS)
    rows = [tuple(norm(v) for v in row) for row in frame[cols].itertuples(index=False, name=None)]
    return sorted(rows, key=lambda r: tuple("" if v is None else str(v) for v in r))


def write_decision(existing, new):
    """Decide how to publish ``new`` given the table rows for the same model_version/city/snapshot.

    Returns ``"append"`` when no such rows exist, ``"unchanged"`` when the content columns are
    identical (an identical rerun is a no-op), and raises when the content differs: a frozen
    model version is never overwritten.
    """
    versions = set(new["model_version"])
    if len(versions) != 1:
        raise ValueError("write_decision: publish one model_version at a time")
    if new.duplicated(list(TABLE_KEYS)).any():
        raise ValueError("write_decision: new rows contain duplicated prediction keys")
    scope = set(zip(new["city"], new["snapshot_date"].map(_date_text)))
    if existing is not None and len(existing):
        existing = existing[existing["model_version"].isin(versions)]
        existing = existing[[(c, _date_text(d)) in scope for c, d in zip(existing["city"], existing["snapshot_date"])]]
    if existing is None or not len(existing):
        return "append"
    if existing.duplicated(list(TABLE_KEYS)).any():
        raise FrozenModelError("table already holds duplicated prediction keys for this model_version")
    if _canonical_rows(existing) == _canonical_rows(new):
        return "unchanged"
    raise FrozenModelError(
        f"predictions for {sorted(versions)} / {sorted(scope)} already exist with different content; "
        "a frozen model_version is never overwritten. Use a new model_version or scoring_version and record why."
    )
