# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "6"
# ///
# MAGIC %md
# MAGIC # Train, select and evaluate the price model (Milan + Florence)
# MAGIC Requires notebooks 01-03 for both training cities and `06_baseline_eval` (persisted
# MAGIC `model_split` and `baseline_lookup`). Logic lives in `airbnb/price_model.py`.
# MAGIC
# MAGIC Run the stages in order; each reads only what it is allowed to:
# MAGIC
# MAGIC | `stage` | Reads | Writes |
# MAGIC |---|---|---|
# MAGIC | `profile` | official **train** rows only | nothing (feature profile in the exit JSON) |
# MAGIC | `select` | official **train** rows only, split into subtrain / validation | `model_selection`, `model_candidate_metrics` (once per `model_version`) |
# MAGIC | `final` | locked selection record, train and **test** rows | model file in a volume, `model_artifacts`, `model_evaluation` (once per `model_version`) |
# MAGIC
# MAGIC `final` refuses to run without a locked selection record whose model specification matches
# MAGIC the code, and refuses to evaluate the same `model_version` twice.

# COMMAND ----------

import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from pyspark.sql import functions as F

root = next((p for p in [Path.cwd(), *Path.cwd().parents] if (p / "config/sources.json").is_file()), None)
if root is None:
    raise ValueError("Run inside the project's Databricks Git folder (or an exact import of a commit).")
sys.path.insert(0, str(root))
import sklearn

from airbnb import price_model as pm
from airbnb.gold import PREDICTORS
from airbnb.model import (
    LOOKUP_COLUMNS, SPLIT_SALT, TRAINING_CITIES, fit_baseline, fit_upper_price_threshold, mae_table, predict_baseline,
)

dbutils.widgets.dropdown("stage", "profile", ["profile", "select", "final"])
dbutils.widgets.text("catalog", "workspace")
dbutils.widgets.text("model_version", pm.MODEL_VERSION)
dbutils.widgets.text("baseline_version", "airbnb-v1")
dbutils.widgets.text("code_revision", "")
stage = dbutils.widgets.get("stage")
catalog = dbutils.widgets.get("catalog").strip()
model_version = dbutils.widgets.get("model_version").strip()
baseline_version = dbutils.widgets.get("baseline_version").strip()
code_revision = dbutils.widgets.get("code_revision").strip()
if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", catalog):
    raise ValueError("Invalid catalog identifier.")
for name, value in (("model_version", model_version), ("baseline_version", baseline_version)):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", value):
        raise ValueError(f"Invalid {name}.")
if model_version != pm.MODEL_VERSION:
    raise ValueError(f"This code defines {pm.MODEL_VERSION}; a new model_version needs a code change.")
if stage != "profile" and not re.fullmatch(r"[0-9a-f]{7,40}", code_revision):
    raise ValueError("code_revision (the Git commit being run) is required for select and final.")

sources = json.loads((root / "config/sources.json").read_text())
missing = [c for c in TRAINING_CITIES if c not in sources]
if missing:
    raise ValueError(f"Training cities missing from config/sources.json: {missing}")
snapshots = {c: date.fromisoformat(sources[c]["snapshot_date"]).isoformat() for c in TRAINING_CITIES}
scope = " OR ".join(f"(city = '{c}' AND snapshot_date = '{d}')" for c, d in snapshots.items())
training_snapshots = ";".join(f"{c}={d}" for c, d in snapshots.items())
gold = f"{catalog}.airbnb_gold"
KEYS = ["city", "snapshot_date", "listing_id"]
spec = pm.model_spec()
spec_sha = pm.sha256_text(pm.canonical_json(spec))
summary = {
    "stage": stage, "catalog": catalog, "model_version": model_version, "code_revision": code_revision,
    "training_snapshots": training_snapshots, "split_salt": SPLIT_SALT, "spec_sha256": spec_sha,
    "sklearn": sklearn.__version__, "numpy": np.__version__, "pandas": pd.__version__, "python": sys.version.split()[0],
}
print(json.dumps(summary, indent=1))

# COMMAND ----------


def table_version(table):
    return int(spark.sql(f"DESCRIBE HISTORY {table} LIMIT 1").collect()[0]["version"])


def load_rows(splits):
    """Join persisted split rows of the given official splits to model_features. Other rows are never read."""
    split = (
        spark.table(f"{gold}.model_split")
        .where(f"split_salt = '{SPLIT_SALT}' AND ({scope})")
        .where(F.col("evaluation_split").isin(*splits))
        .select(*KEYS, "evaluation_split")
    )
    features = spark.table(f"{gold}.model_features").where(scope).select(*KEYS, "price_eur", *PREDICTORS)
    frame = split.join(features, KEYS, "inner").toPandas()
    if not set(frame["evaluation_split"]).issubset(splits):
        raise RuntimeError("Rows outside the requested splits were loaded.")
    expected = split.count()
    if len(frame) != expected or frame.duplicated(["city", "listing_id"]).any():
        raise RuntimeError(f"Split/feature join returned {len(frame)} rows for {expected} split rows.")
    price = pd.to_numeric(frame["price_eur"])
    if not (np.isfinite(price) & (price > 0)).all():
        raise RuntimeError("Some split rows have no valid positive price.")
    return frame.sort_values(["city", "listing_id"]).reset_index(drop=True)


def rows_to_spark(frame, schema):
    return spark.createDataFrame(frame.astype(object).where(frame.notna(), None).values.tolist(), schema)


def counts_by(frame, column):
    return {f"{c}:{v}": int(n) for (c, v), n in frame.groupby(["city", column]).size().items()}


summary["input_versions"] = {t: table_version(f"{gold}.{t}") for t in ("model_features", "model_split", "baseline_lookup")}

# COMMAND ----------

if stage == "profile":
    train = load_rows(["train"])
    summary["rows"] = counts_by(train, "evaluation_split")
    profile = pm.profile_features(train, PREDICTORS)
    reviews = ["review_scores_rating", "review_scores_accuracy", "review_scores_cleanliness", "review_scores_checkin",
               "review_scores_communication", "review_scores_location", "review_scores_value"]
    corr = train[reviews].apply(pd.to_numeric, errors="coerce").corr(method="spearman").round(3)
    property_counts = train["property_type"].fillna(pm.MISSING).value_counts()
    summary.update(
        feature_profile=profile.to_dict(orient="records"),
        review_score_spearman=corr.to_dict(),
        property_type_levels=int(len(property_counts)),
        property_type_levels_ge_min_count=int((property_counts >= pm.MIN_CATEGORY_COUNT).sum()),
        property_type_rows_in_rare_levels=int(property_counts[property_counts < pm.MIN_CATEGORY_COUNT].sum()),
        property_type_counts=property_counts.astype(int).to_dict(),
        room_type_by_city=counts_by(train.assign(room_type=train["room_type"].fillna(pm.MISSING)), "room_type"),
    )
    display(profile)
    display(corr.reset_index())

# COMMAND ----------

if stage == "select":
    if spark.catalog.tableExists(f"{gold}.model_selection") and (
        spark.table(f"{gold}.model_selection").where(F.col("model_version") == model_version).limit(1).count()
    ):
        raise RuntimeError(f"Selection for {model_version} is already locked; choose a new model_version.")

    train = pm.assign_validation_fold(load_rows(["train"]))
    labelled = train.assign(_fold=np.where(train[pm.FOLD_COL] == "subtrain", "train", "validation"))
    fit_rows = labelled[labelled["_fold"] == "train"]
    valid = labelled[labelled["_fold"] == "validation"].copy()
    summary["fold_rows"] = counts_by(labelled, pm.FOLD_COL)

    # Baseline refitted on subtrain only, for a fair comparison on the validation rows.
    lookup = fit_baseline(labelled, split_col="_fold")
    valid = predict_baseline(valid, lookup)
    summary["validation_baseline_levels"] = counts_by(valid, "baseline_level")
    threshold = fit_upper_price_threshold(labelled, split_col="_fold")
    summary["validation_supplementary_threshold_eur"] = threshold

    fits = {}
    for cand in pm.CANDIDATES:
        model, fit_s = pm.fit_model(cand["family"], cand["params"], fit_rows)
        valid[cand["name"]], pred_s = pm.predict_eur(model, valid)
        fits[cand["name"]] = {"model": model, "fit_seconds": fit_s, "predict_seconds": pred_s,
                              "complexity": pm.model_complexity(model, cand["family"])}
        print(f"{cand['name']}: fit {fit_s:.1f}s predict {pred_s:.2f}s {fits[cand['name']]['complexity']}")

    names = [c["name"] for c in pm.CANDIDATES]
    metrics = mae_table(
        valid, ["baseline_prediction_eur", *names], split_col="_fold", split_value="validation",
        upper_price_threshold=threshold, threshold_source="p99 of subtrain prices (Milan+Florence)",
    )
    base = metrics[metrics["prediction"] == "baseline_prediction_eur"][["evaluation_population", "city_group", "mae_eur"]]
    metrics = metrics.merge(base.rename(columns={"mae_eur": "baseline_mae_eur"}), on=["evaluation_population", "city_group"])
    metrics["improvement_eur"] = metrics["baseline_mae_eur"] - metrics["mae_eur"]
    metrics["improvement_pct"] = 100 * metrics["improvement_eur"] / metrics["baseline_mae_eur"]
    display(metrics)

    headline = metrics[metrics["evaluation_population"] == "test_all_valid_positive_price"]
    groups = [*TRAINING_CITIES, "+".join(TRAINING_CITIES)]
    table = headline.pivot(index="prediction", columns="city_group", values="mae_eur")[groups]
    candidate_mae = {n: table.loc[n].to_dict() for n in names}
    baseline_mae = table.loc["baseline_prediction_eur"].to_dict()
    selected, decision = pm.select_candidate(candidate_mae, baseline_mae)
    if selected is None:
        raise RuntimeError(f"No candidate clears the predeclared rule: {decision}")
    chosen = next(c for c in pm.CANDIDATES if c["name"] == selected)

    # Explanations and failure modes for the best candidate of each family (validation rows only).
    explain = {}
    edges = pm.price_band_edges(fit_rows)
    for family, name in decision["best_per_family"].items():
        model = fits[name]["model"]
        info = {
            "permutation_importance": pm.permutation_importance_eur(model, valid).round(3).to_dict(orient="records"),
            "property_type_other_or_missing_share": pm.property_other_share(model, valid),
            "kept_property_types": model.regressor_.named_steps["prep"].named_transformers_["prop"]
            .named_steps["group"].kept_levels_["property_type"],
        }
        if family == "ridge_log":
            info["coefficients"] = pm.ridge_coefficients(model).round(4).to_dict(orient="records")
        tables = pm.failure_mode_tables(valid, {"baseline": valid["baseline_prediction_eur"], name: valid[name]}, edges)
        info["failure_modes"] = {k: v.round(2).to_dict(orient="records") for k, v in tables.items()}
        explain[name] = info

    record = {
        "model_version": model_version, "code_revision": code_revision, "spec": spec, "spec_sha256": spec_sha,
        "training_snapshots": training_snapshots, "split_salt": SPLIT_SALT, "input_versions": summary["input_versions"],
        "fold_rows": summary["fold_rows"], "validation_baseline_levels": summary["validation_baseline_levels"],
        "validation_supplementary_threshold_eur": threshold,
        "validation_metrics": metrics.drop(columns=["population_description"]).to_dict(orient="records"),
        "timing_and_complexity": {n: {k: v for k, v in f.items() if k != "model"} for n, f in fits.items()},
        "decision": decision, "selected_candidate": chosen, "explanations": explain,
        "environment": {k: summary[k] for k in ("sklearn", "numpy", "pandas", "python")},
    }
    record_json = pm.canonical_json(record)
    record_sha = pm.sha256_text(record_json)
    selection = pd.DataFrame([{
        "model_version": model_version, "split_salt": SPLIT_SALT, "validation_salt": pm.VALIDATION_SALT,
        "training_snapshots": training_snapshots, "selected_candidate": chosen["name"], "selected_family": chosen["family"],
        "selected_params_json": pm.canonical_json(chosen["params"]), "random_seed": pm.RANDOM_SEED,
        "spec_sha256": spec_sha, "code_revision": code_revision, "record_sha256": record_sha, "record_json": record_json,
    }])
    rows_to_spark(selection, (
        "model_version string, split_salt string, validation_salt string, training_snapshots string, "
        "selected_candidate string, selected_family string, selected_params_json string, random_seed bigint, "
        "spec_sha256 string, code_revision string, record_sha256 string, record_json string"
    )).write.format("delta").mode("append").saveAsTable(f"{gold}.model_selection")

    family_of = {c["name"]: c["family"] for c in pm.CANDIDATES}
    cand_rows = metrics[metrics["prediction"] != "baseline_prediction_eur"].assign(
        model_version=model_version, family=lambda d: d["prediction"].map(family_of),
        fit_seconds=lambda d: d["prediction"].map(lambda n: fits[n]["fit_seconds"]),
        predict_seconds=lambda d: d["prediction"].map(lambda n: fits[n]["predict_seconds"]),
        selected=lambda d: d["prediction"] == chosen["name"],
    )[["model_version", "prediction", "family", "evaluation_population", "city_group", "n", "mae_eur",
       "baseline_mae_eur", "improvement_eur", "improvement_pct", "fit_seconds", "predict_seconds", "selected"]]
    rows_to_spark(cand_rows.rename(columns={"prediction": "candidate"}), (
        "model_version string, candidate string, family string, evaluation_population string, city_group string, "
        "n bigint, mae_eur double, baseline_mae_eur double, improvement_eur double, improvement_pct double, "
        "fit_seconds double, predict_seconds double, selected boolean"
    )).write.format("delta").mode("append").saveAsTable(f"{gold}.model_candidate_metrics")
    summary.update(record_sha256=record_sha, selected=chosen, decision=decision, record=record)
    print(f"Locked {chosen['name']} for {model_version}; record sha256 {record_sha}")

# COMMAND ----------

if stage == "final":
    if spark.catalog.tableExists(f"{gold}.model_evaluation") and (
        spark.table(f"{gold}.model_evaluation").where(F.col("model_version") == model_version).limit(1).count()
    ):
        raise RuntimeError(f"{model_version} was already evaluated on the test rows; it is evaluated once only.")
    locked = spark.table(f"{gold}.model_selection").where(F.col("model_version") == model_version).collect()
    if len(locked) != 1:
        raise RuntimeError(f"Expected exactly one locked selection for {model_version}, found {len(locked)}.")
    locked = locked[0]
    if pm.sha256_text(locked["record_json"]) != locked["record_sha256"]:
        raise RuntimeError("Selection record does not match its hash.")
    if locked["spec_sha256"] != spec_sha:
        raise RuntimeError("Model specification in the code differs from the locked selection; do not evaluate.")
    chosen = json.loads(locked["record_json"])["selected_candidate"]
    summary.update(selection_record_sha256=locked["record_sha256"], selection_code_revision=locked["code_revision"],
                   selected=chosen)

    data = load_rows(["train", "test"])
    train, test = data[data["evaluation_split"] == "train"], data[data["evaluation_split"] == "test"].copy()
    summary["rows"] = counts_by(data, "evaluation_split")
    model, fit_s = pm.fit_model(chosen["family"], chosen["params"], train)

    # Persist the artifact before scoring the test rows.
    import joblib
    spark.sql(f"CREATE VOLUME IF NOT EXISTS {gold}.model_artifacts")
    artifact_dir = Path(f"/Volumes/{catalog}/airbnb_gold/model_artifacts/{model_version}")
    artifact = artifact_dir / "model.joblib"
    if artifact.exists():
        raise RuntimeError(f"{artifact} already exists; it is never overwritten.")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, artifact)
    (artifact_dir / "selection_record.json").write_text(locked["record_json"])
    artifact_sha = hashlib.sha256(artifact.read_bytes()).hexdigest()
    reloaded = joblib.load(artifact)

    stored_lookup = (spark.table(f"{gold}.baseline_lookup").where(F.col("baseline_version") == baseline_version)
                     .select(*LOOKUP_COLUMNS).toPandas())
    test = predict_baseline(test, stored_lookup)
    test["model_prediction_eur"], pred_s = pm.predict_eur(reloaded, test)
    threshold = fit_upper_price_threshold(data)  # training rows only
    metrics = mae_table(test, ["baseline_prediction_eur", "model_prediction_eur"], upper_price_threshold=threshold,
                        threshold_source="p99 of Milan+Florence training prices")
    pivot = metrics.pivot_table(index=["evaluation_population", "city_group", "n"], columns="prediction",
                                values="mae_eur").reset_index()
    pivot["improvement_eur"] = pivot["baseline_prediction_eur"] - pivot["model_prediction_eur"]
    pivot["improvement_pct"] = 100 * pivot["improvement_eur"] / pivot["baseline_prediction_eur"]
    display(pivot)

    evaluation = pivot.rename(columns={"baseline_prediction_eur": "baseline_mae_eur", "model_prediction_eur": "model_mae_eur"})
    evaluation = evaluation.assign(model_version=model_version, baseline_version=baseline_version, split_salt=SPLIT_SALT,
                                   selection_record_sha256=locked["record_sha256"], artifact_sha256=artifact_sha)
    evaluation = evaluation[["model_version", "baseline_version", "split_salt", "evaluation_population", "city_group", "n",
                             "baseline_mae_eur", "model_mae_eur", "improvement_eur", "improvement_pct",
                             "selection_record_sha256", "artifact_sha256"]]
    rows_to_spark(evaluation, (
        "model_version string, baseline_version string, split_salt string, evaluation_population string, "
        "city_group string, n bigint, baseline_mae_eur double, model_mae_eur double, improvement_eur double, "
        "improvement_pct double, selection_record_sha256 string, artifact_sha256 string"
    )).write.format("delta").mode("append").saveAsTable(f"{gold}.model_evaluation")

    # Reporting only: nothing below feeds back into the model.
    report = {"complexity": pm.model_complexity(reloaded, chosen["family"]),
              "property_type_other_or_missing_share_test": pm.property_other_share(reloaded, test)}
    if chosen["family"] == "ridge_log":
        report["coefficients"] = pm.ridge_coefficients(reloaded).round(4).to_dict(orient="records")
    tables = pm.failure_mode_tables(
        test, {"baseline": test["baseline_prediction_eur"], "model": test["model_prediction_eur"]}, pm.price_band_edges(train))
    report["failure_modes_test"] = {k: v.round(2).to_dict(orient="records") for k, v in tables.items()}

    artifacts = pd.DataFrame([{
        "model_version": model_version, "artifact_path": str(artifact), "artifact_sha256": artifact_sha,
        "selected_candidate": chosen["name"], "selected_family": chosen["family"],
        "selected_params_json": pm.canonical_json(chosen["params"]), "spec_sha256": spec_sha,
        "selection_record_sha256": locked["record_sha256"], "code_revision": code_revision,
        "training_snapshots": training_snapshots, "split_salt": SPLIT_SALT, "train_rows": int(len(train)),
        "sklearn_version": sklearn.__version__, "fit_seconds": fit_s, "mlflow_run_id": None,
    }])

    # MLflow tracking is secondary to the volume file + hash; a tracking failure is recorded, not fatal.
    try:
        import mlflow
        user = spark.sql("SELECT current_user() AS u").collect()[0]["u"]
        mlflow.set_experiment(f"/Users/{user}/airbnb_price_model")
        with mlflow.start_run(run_name=f"{model_version}-{chosen['name']}") as run:
            mlflow.log_params({"model_version": model_version, "candidate": chosen["name"], "family": chosen["family"],
                               **{f"param_{k}": v for k, v in chosen["params"].items()}, "spec_sha256": spec_sha,
                               "artifact_sha256": artifact_sha, "code_revision": code_revision})
            for r in evaluation.itertuples():
                tag = f"{r.evaluation_population}.{r.city_group}".replace("+", "_")
                mlflow.log_metrics({f"test_mae_model.{tag}": r.model_mae_eur, f"test_mae_baseline.{tag}": r.baseline_mae_eur})
            mlflow.log_artifact(str(artifact))
            mlflow.log_artifact(str(artifact_dir / "selection_record.json"))
        artifacts["mlflow_run_id"] = run.info.run_id
    except Exception as exc:  # noqa: BLE001
        summary["mlflow_error"] = repr(exc)
    rows_to_spark(artifacts, (
        "model_version string, artifact_path string, artifact_sha256 string, selected_candidate string, "
        "selected_family string, selected_params_json string, spec_sha256 string, selection_record_sha256 string, "
        "code_revision string, training_snapshots string, split_salt string, train_rows bigint, sklearn_version string, "
        "fit_seconds double, mlflow_run_id string"
    )).write.format("delta").mode("append").saveAsTable(f"{gold}.model_artifacts")
    summary.update(artifact=artifacts.iloc[0].to_dict(), fit_seconds=fit_s, predict_seconds=pred_s,
                   supplementary_threshold_eur=threshold, test_metrics=evaluation.to_dict(orient="records"), report=report)

# COMMAND ----------

dbutils.notebook.exit(json.dumps(summary, default=str))
