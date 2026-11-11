"""Price model (MODEL-04): feature allowlist, leak-free preprocessing, candidates, selection.

Requires scikit-learn (installed on Databricks serverless). Split, baseline and MAE
helpers come from ``airbnb.model``. Decisions are documented in
docs/model_feature_review.md and docs/model_selection.md.

Rules encoded here:
- Every fitted step (category grouping, clipping bounds, imputation, scaling, the
  model itself) lives inside one scikit-learn pipeline, so it is fitted only on
  the rows passed to ``fit``.
- Model selection uses a validation subset carved out of the official training
  rows with its own salt; the official test rows are never read for selection.
- The target is ``log1p(price_eur)``; predictions are converted back to EUR.
"""

import hashlib
import json
import time

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer, TransformedTargetRegressor
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from airbnb.model import PRICE_COL, SPLIT_COL, TRAINING_CITIES, split_hash_unit

MODEL_VERSION = "price-v1"
VALIDATION_SALT = "airbnb-v1-model-selection"
VALIDATION_SHARE = 0.20
FOLD_COL = "selection_fold"
RANDOM_SEED = 20261111

MIN_CATEGORY_COUNT = 50   # levels with fewer fit rows become OTHER
CLIP_QUANTILE = 0.99      # numeric features are capped at their fit-row p99
MISSING = "__missing__"
OTHER = "__other__"

# Final allowlist. Booleans are treated as categories (true / false / __missing__).
CATEGORICAL_FEATURES = ("room_type", "property_type", "bath_shared", "long_stay", "has_reviews", "host_is_superhost")
GROUPED_FEATURES = ("property_type",)  # rare levels (< MIN_CATEGORY_COUNT fit rows) -> OTHER
UNGROUPED_CATEGORICAL = tuple(c for c in CATEGORICAL_FEATURES if c not in GROUPED_FEATURES)
SIZE_FEATURES = ("accommodates", "bedrooms", "beds", "bathrooms_n")
OTHER_NUMERIC_FEATURES = ("minimum_nights", "dist_center_km", "log_host_listings_count")
REVIEW_FEATURES = ("review_scores_rating", "review_scores_cleanliness", "review_scores_location")
LOG1P_FEATURES = ("minimum_nights", "dist_center_km")
NUMERIC_FEATURES = SIZE_FEATURES + OTHER_NUMERIC_FEATURES + REVIEW_FEATURES
FEATURES = CATEGORICAL_FEATURES + NUMERIC_FEATURES

# Candidates from gold.PREDICTORS that are not in the allowlist, with the reason.
EXCLUDED_FEATURES = {
    "instant_bookable": "100 % missing in Milan and Florence training rows; a frozen model cannot learn it",
    "review_scores_value": "rates quality relative to the price paid, so it partly encodes the target",
    "review_scores_accuracy": "Spearman 0.81 with review_scores_rating on training rows; no distinct price meaning",
    "review_scores_checkin": "Spearman 0.68 with review_scores_rating; host-service score",
    "review_scores_communication": "Spearman 0.72 with review_scores_rating; host-service score",
}

# Never allowed as predictors (price-derived, target-derived or identifiers).
FORBIDDEN_FEATURES = (
    PRICE_COL, "price", "raw_price", "estimated_revenue_l365d", "estimated_occupancy_l365d",
    "price_class", "city_price_p99", "exclusion_reason", "exclusion_reasons", "eligible_for_analysis",
    "eligible_for_training", "quality_flags", "city", "listing_id", "snapshot_date", "latitude",
    "longitude", "neighbourhood_cleansed", SPLIT_COL, FOLD_COL,
)

# Predeclared candidate set, fixed before any validation result is read.
CANDIDATES = (
    *({"name": f"ridge_alpha_{a:g}", "family": "ridge_log", "params": {"alpha": float(a)}} for a in (0.1, 1, 10, 100)),
    *(
        {
            "name": f"hgb_leaves_{leaves}_iter_{iters}",
            "family": "hgb_log",
            "params": {
                "learning_rate": 0.05, "max_iter": iters, "max_leaf_nodes": leaves,
                "min_samples_leaf": 40, "l2_regularization": 1.0,
            },
        }
        for leaves in (15, 31) for iters in (200, 400)
    ),
)
FAMILY_COMPLEXITY_ORDER = ("ridge_log", "hgb_log")  # simplest first

# Predeclared selection rule.
MIN_GAIN_OVER_BASELINE = 0.05   # a family qualifies if it beats the baseline by >= 5 % in every group
MIN_GAIN_FOR_COMPLEXITY = 0.03  # a more complex family must beat the simpler one by >= 3 % in every group

DISTANCE_BANDS_KM = (0, 1, 2, 4, 8, np.inf)


def _check_allowlist():
    overlap = set(FEATURES) & (set(FORBIDDEN_FEATURES) | set(EXCLUDED_FEATURES))
    if overlap:
        raise AssertionError(f"Allowlist contains forbidden or excluded features: {sorted(overlap)}")


_check_allowlist()


# --------------------------------------------------------------------------- #
# Transformers
# --------------------------------------------------------------------------- #

def _as_text(value):
    if value is None or (isinstance(value, float) and np.isnan(value)) or value is pd.NA or value is pd.NaT:
        return MISSING
    if isinstance(value, (bool, np.bool_)):
        return "true" if value else "false"
    text = str(value).strip()
    return text if text else MISSING


class CategoryGrouper(BaseEstimator, TransformerMixin):
    """Map missing values to ``__missing__`` and levels with < ``min_count`` fit rows to ``__other__``.

    A level never seen in fit rows is also ``__other__``, so a new city cannot break scoring.
    """

    def __init__(self, min_count=MIN_CATEGORY_COUNT):
        self.min_count = min_count

    def _text(self, X):
        frame = pd.DataFrame(X).copy()
        return frame.apply(lambda col: col.map(_as_text)).astype(object)

    def fit(self, X, y=None):
        frame = self._text(X)
        self.feature_names_in_ = np.asarray(frame.columns, dtype=object)
        self.level_counts_ = {c: frame[c].value_counts().astype(int).to_dict() for c in frame.columns}
        self.kept_levels_ = {
            c: sorted(level for level, n in counts.items() if n >= self.min_count and level != MISSING)
            for c, counts in self.level_counts_.items()
        }
        return self

    def transform(self, X):
        frame = self._text(X)
        frame.columns = self.feature_names_in_
        for c in frame.columns:
            keep = frame[c].isin(self.kept_levels_[c]) | (frame[c] == MISSING)
            frame[c] = frame[c].where(keep, OTHER)
        return frame

    def get_feature_names_out(self, input_features=None):
        return np.asarray(self.feature_names_in_, dtype=object)


class NumericPrep(BaseEstimator, TransformerMixin):
    """Coerce to float, cap each column at its fit-row ``clip_quantile`` and apply ``log1p`` where listed.

    Values that are not finite become NaN for the imputer. Capping limits how far a
    linear model extrapolates on an unseen city.
    """

    def __init__(self, log1p=(), clip_quantile=CLIP_QUANTILE):
        self.log1p = log1p
        self.clip_quantile = clip_quantile

    @staticmethod
    def _numeric(X):
        frame = pd.DataFrame(X).apply(lambda col: pd.to_numeric(col, errors="coerce")).astype("float64")
        return frame.where(np.isfinite(frame))

    def fit(self, X, y=None):
        frame = self._numeric(X)
        self.feature_names_in_ = np.asarray(frame.columns, dtype=object)
        self.upper_ = {c: (float(frame[c].quantile(self.clip_quantile)) if frame[c].notna().any() else np.nan)
                       for c in frame.columns}
        return self

    def transform(self, X):
        frame = self._numeric(X)
        frame.columns = self.feature_names_in_
        for c in frame.columns:
            if np.isfinite(self.upper_[c]):
                frame[c] = frame[c].clip(upper=self.upper_[c])
            if c in self.log1p:
                frame[c] = np.log1p(frame[c].clip(lower=0))
        return frame

    def get_feature_names_out(self, input_features=None):
        return np.asarray(self.feature_names_in_, dtype=object)


def _one_hot():
    try:
        return OneHotEncoder(handle_unknown="ignore", sparse_output=False)
    except TypeError:  # scikit-learn < 1.2
        return OneHotEncoder(handle_unknown="ignore", sparse=False)


def build_preprocessor(scale):
    def numeric(columns, indicator):
        steps = [
            ("cap_log", NumericPrep(log1p=tuple(c for c in columns if c in LOG1P_FEATURES))),
            ("impute", SimpleImputer(strategy="median", add_indicator=indicator)),
        ]
        if scale:
            steps.append(("scale", StandardScaler()))
        return Pipeline(steps)

    return ColumnTransformer(
        [
            # Only the long-tailed property_type is grouped; low-cardinality categories keep every
            # level seen in fit rows (room_type has < 50 Hotel/Shared rows that must stay distinct).
            ("prop", Pipeline([("group", CategoryGrouper(MIN_CATEGORY_COUNT)), ("onehot", _one_hot())]), list(GROUPED_FEATURES)),
            ("cat", Pipeline([("group", CategoryGrouper(1)), ("onehot", _one_hot())]), list(UNGROUPED_CATEGORICAL)),
            # Missing indicators for size/other numerics; review scores are null exactly when
            # has_reviews is false, so has_reviews already plays the indicator role.
            ("num", numeric(SIZE_FEATURES + OTHER_NUMERIC_FEATURES, True), list(SIZE_FEATURES + OTHER_NUMERIC_FEATURES)),
            ("rev", numeric(REVIEW_FEATURES, False), list(REVIEW_FEATURES)),
        ],
        remainder="drop",
    )


def build_model(family, params, seed=RANDOM_SEED):
    """Unfitted pipeline that maps a ``model_features`` frame to a price in EUR."""
    if family == "ridge_log":
        preprocessor, estimator = build_preprocessor(scale=True), Ridge(**params)
    elif family == "hgb_log":
        preprocessor = build_preprocessor(scale=False)
        estimator = HistGradientBoostingRegressor(early_stopping=False, random_state=seed, **params)
    else:
        raise ValueError(f"Unknown model family {family!r}")
    return TransformedTargetRegressor(
        regressor=Pipeline([("prep", preprocessor), ("model", estimator)]),
        func=np.log1p, inverse_func=np.expm1, check_inverse=False,
    )


def model_inputs(df):
    missing = [c for c in FEATURES if c not in df.columns]
    if missing:
        raise ValueError(f"model inputs: missing feature columns {missing}")
    return df[list(FEATURES)]


def training_target(df):
    y = pd.to_numeric(df[PRICE_COL], errors="coerce").astype("float64")
    if not (np.isfinite(y) & (y > 0)).all():
        raise ValueError("training rows must all have a valid positive price")
    return y.to_numpy()


def fit_model(family, params, train_df, seed=RANDOM_SEED):
    model = build_model(family, params, seed)
    start = time.perf_counter()
    model.fit(model_inputs(train_df), training_target(train_df))
    return model, time.perf_counter() - start


def predict_eur(model, df):
    start = time.perf_counter()
    predictions = np.asarray(model.predict(model_inputs(df)), dtype="float64")
    elapsed = time.perf_counter() - start
    if not np.isfinite(predictions).all():
        raise ValueError("model produced non-finite predictions")
    return predictions, elapsed


# --------------------------------------------------------------------------- #
# Validation fold inside the official training rows
# --------------------------------------------------------------------------- #

def assign_validation_fold(train_df, salt=VALIDATION_SALT, share=VALIDATION_SHARE):
    """Split official ``train`` rows into ``subtrain`` and ``validation`` by a separate salted hash."""
    if SPLIT_COL in train_df.columns and (train_df[SPLIT_COL] != "train").any():
        raise ValueError("assign_validation_fold: only official training rows may be passed")
    if salt == "airbnb-v1":
        raise ValueError("validation salt must differ from the official split salt")
    units = np.array([split_hash_unit(c, i, salt) for c, i in zip(train_df["city"], train_df["listing_id"])])
    out = train_df.copy()
    out[FOLD_COL] = np.where(units < share, "validation", "subtrain")
    return out


# --------------------------------------------------------------------------- #
# Training-row feature profile
# --------------------------------------------------------------------------- #

def profile_features(train_df, candidates, min_count=MIN_CATEGORY_COUNT):
    """Missingness, cardinality and distribution of each candidate on the rows given (training rows only)."""
    records = []
    for feature in candidates:
        col = train_df[feature]
        text = col.map(_as_text)
        record = {"feature": feature, "n_rows": int(len(col))}
        for city in TRAINING_CITIES:
            mask = train_df["city"] == city
            record[f"missing_rate_{city}"] = float((text[mask] == MISSING).mean()) if mask.any() else np.nan
        record["missing_rate"] = float((text == MISSING).mean())
        numeric = pd.to_numeric(col, errors="coerce") if not _is_categorical(col) else None
        if numeric is not None and numeric.notna().any():
            record["kind"] = "numeric"
            q = numeric.quantile([0.0, 0.01, 0.25, 0.5, 0.75, 0.99, 1.0]).to_numpy()
            record.update(min=q[0], p01=q[1], p25=q[2], p50=q[3], p75=q[4], p99=q[5], max=q[6],
                          mean=float(numeric.mean()), n_levels=int(numeric.nunique()))
        else:
            counts = text[text != MISSING].value_counts()
            rare = counts[counts < min_count]
            record.update(kind="categorical", n_levels=int(len(counts)), n_rare_levels=int(len(rare)),
                          rare_rows=int(rare.sum()), top_levels=json.dumps(counts.head(8).astype(int).to_dict()))
        records.append(record)
    return pd.DataFrame.from_records(records)


def _is_categorical(col):
    sample = col.dropna()
    return sample.empty or sample.map(lambda v: isinstance(v, (str, bool, np.bool_))).any()


# --------------------------------------------------------------------------- #
# Selection
# --------------------------------------------------------------------------- #

def mae_by_group(df, prediction, actual_col=PRICE_COL, cities=TRAINING_CITIES):
    """MAE per city and pooled on the rows given."""
    errors = (pd.Series(prediction, index=df.index) - pd.to_numeric(df[actual_col])).abs()
    out = {c: float(errors[df["city"] == c].mean()) for c in cities}
    out["+".join(cities)] = float(errors[df["city"].isin(cities)].mean())
    return out


def select_candidate(candidate_mae, baseline_mae):
    """Apply the predeclared rule. ``candidate_mae``: {name: {group: mae}}; ``baseline_mae``: {group: mae}.

    1. Within each family, the candidate with the lowest pooled MAE.
    2. A family qualifies if that candidate beats the baseline by >= MIN_GAIN_OVER_BASELINE in every group.
    3. The simplest qualifying family wins unless a more complex one beats it by
       >= MIN_GAIN_FOR_COMPLEXITY in every group.
    """
    groups = list(baseline_mae)
    pooled = groups[-1]
    by_name = {c["name"]: c for c in CANDIDATES}
    best = {}
    for family in FAMILY_COMPLEXITY_ORDER:
        names = [n for n in candidate_mae if by_name[n]["family"] == family]
        if names:
            best[family] = min(names, key=lambda n: (candidate_mae[n][pooled], n))

    def gain(new, old):
        return 1.0 - new / old

    qualifying = [
        f for f in FAMILY_COMPLEXITY_ORDER
        if f in best and all(gain(candidate_mae[best[f]][g], baseline_mae[g]) >= MIN_GAIN_OVER_BASELINE for g in groups)
    ]
    if not qualifying:
        return None, {"best_per_family": best, "qualifying_families": [], "reason": "no family beats the baseline in every group"}
    chosen = qualifying[0]
    for family in qualifying[1:]:
        if all(gain(candidate_mae[best[family]][g], candidate_mae[best[chosen]][g]) >= MIN_GAIN_FOR_COMPLEXITY for g in groups):
            chosen = family
    return best[chosen], {"best_per_family": best, "qualifying_families": qualifying, "chosen_family": chosen}


def selection_rule_text():
    return (
        f"Within each family pick the lowest pooled validation MAE. A family qualifies if it beats the "
        f"subtrain-fitted baseline by >= {MIN_GAIN_OVER_BASELINE:.0%} in Milan, Florence and pooled. "
        f"Choose the simplest qualifying family ({' < '.join(FAMILY_COMPLEXITY_ORDER)}) unless a more complex "
        f"one beats it by >= {MIN_GAIN_FOR_COMPLEXITY:.0%} in every group."
    )


def model_spec():
    """Everything that defines the model apart from fitted values; hashed into the selection record."""
    return {
        "model_version": MODEL_VERSION,
        "features": list(FEATURES),
        "categorical_features": list(CATEGORICAL_FEATURES),
        "grouped_categorical_features": list(GROUPED_FEATURES),
        "numeric_features_with_missing_indicator": list(SIZE_FEATURES + OTHER_NUMERIC_FEATURES),
        "review_features_no_indicator": list(REVIEW_FEATURES),
        "log1p_features": list(LOG1P_FEATURES),
        "excluded_features": EXCLUDED_FEATURES,
        "preprocessing": {
            "categorical": f"missing -> {MISSING}; property_type levels with < {MIN_CATEGORY_COUNT} fit rows -> {OTHER}; "
                           f"other categoricals keep every fit-row level; unseen levels -> {OTHER}; "
                           "one-hot with handle_unknown=ignore",
            "numeric": f"coerce to float; cap at fit-row p{int(CLIP_QUANTILE * 100)}; log1p on {list(LOG1P_FEATURES)}; "
                       "fit-row median imputation (+ missing indicator except review scores); "
                       "standard scaling for ridge only",
            "target": "log1p(price_eur), predictions expm1 back to EUR",
        },
        "category_min_count": MIN_CATEGORY_COUNT,
        "clip_quantile": CLIP_QUANTILE,
        "candidates": [dict(c) for c in CANDIDATES],
        "selection_rule": selection_rule_text(),
        "validation_salt": VALIDATION_SALT,
        "validation_share": VALIDATION_SHARE,
        "random_seed": RANDOM_SEED,
    }


def canonical_json(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=_json_default)


def _json_default(value):
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    return str(value)


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# Explanations and failure modes (reporting only; never used for decisions on test)
# --------------------------------------------------------------------------- #

def ridge_coefficients(model):
    pipe = model.regressor_
    names = pipe.named_steps["prep"].get_feature_names_out()
    coef = pipe.named_steps["model"].coef_
    out = pd.DataFrame({"term": names, "coef_log": coef, "price_effect_pct": np.expm1(coef) * 100})
    return out.reindex(out["coef_log"].abs().sort_values(ascending=False).index).reset_index(drop=True)


def permutation_importance_eur(model, df, n_repeats=3, seed=RANDOM_SEED):
    from sklearn.inspection import permutation_importance

    X = model_inputs(df)
    y = pd.to_numeric(df[PRICE_COL]).to_numpy()
    result = permutation_importance(model, X, y, scoring="neg_mean_absolute_error", n_repeats=n_repeats, random_state=seed)
    out = pd.DataFrame({"feature": list(X.columns), "mae_increase_eur": result.importances_mean,
                        "std_eur": result.importances_std})
    return out.sort_values("mae_increase_eur", ascending=False).reset_index(drop=True)


def model_complexity(model, family):
    pipe = model.regressor_
    n_inputs = len(pipe.named_steps["prep"].get_feature_names_out())
    est = pipe.named_steps["model"]
    if family == "ridge_log":
        return {"encoded_inputs": n_inputs, "coefficients": int(np.size(est.coef_)) + 1}
    return {"encoded_inputs": n_inputs, "trees": int(est.n_iter_), "max_leaves_per_tree": int(est.max_leaf_nodes)}


def property_other_share(model, df):
    """Share of rows whose property_type falls into OTHER or MISSING after the fitted grouping."""
    grouper = model.regressor_.named_steps["prep"].named_transformers_["prop"].named_steps["group"]
    grouped = grouper.transform(df[list(GROUPED_FEATURES)])
    return {c: float(grouped.loc[(df["city"] == c).to_numpy(), "property_type"].isin([OTHER, MISSING]).mean())
            for c in TRAINING_CITIES}


def price_band_edges(fit_df, quantiles=(0.25, 0.5, 0.75, 0.95)):
    """Band edges for error analysis, fitted on the fit rows' prices."""
    prices = pd.to_numeric(fit_df[PRICE_COL])
    return [0.0, *[float(prices.quantile(q)) for q in quantiles], np.inf]


def error_breakdown(df, predictions, by, actual_col=PRICE_COL):
    """Long table of n, MAE and mean signed error (prediction - actual) per city and group."""
    frame = pd.DataFrame({"city": df["city"].to_numpy(), "group": by.astype(str).to_numpy()})
    actual = pd.to_numeric(df[actual_col]).to_numpy()
    records = []
    for name, pred in predictions.items():
        signed = np.asarray(pred) - actual
        frame["signed"], frame["abs"] = signed, np.abs(signed)
        for (city, group), g in frame.groupby(["city", "group"], sort=True):
            records.append({"city": city, "group": group, "prediction": name, "n": int(len(g)),
                            "mae_eur": float(g["abs"].mean()), "mean_error_eur": float(g["signed"].mean())})
    return pd.DataFrame.from_records(records)


def failure_mode_tables(df, predictions, band_edges):
    price_band = pd.cut(pd.to_numeric(df[PRICE_COL]), band_edges, right=False)
    dist = pd.to_numeric(df["dist_center_km"], errors="coerce")
    dist_band = pd.cut(dist, DISTANCE_BANDS_KM, right=False).astype(str).where(dist.notna(), "missing")
    return {
        "by_room_type": error_breakdown(df, predictions, df["room_type"].map(_as_text)),
        "by_actual_price_band": error_breakdown(df, predictions, price_band),
        "by_distance_band_km": error_breakdown(df, predictions, dist_band),
    }
