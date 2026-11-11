# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "6"
# ///
# MAGIC %md
# MAGIC # Score every listing with a frozen price model (MODEL-06 / MODEL-07)
# MAGIC Requires notebooks 01-03 for each city, `06_baseline_eval` (persisted split and baseline
# MAGIC lookup) and `07_train_model` stage `final` (the frozen artifact). Logic lives in
# MAGIC `airbnb/scoring.py`. **Nothing is fitted here.**
# MAGIC
# MAGIC 1. Load the artifact for `model_version` from the volume; refuse to score unless its SHA-256,
# MAGIC    the `model_artifacts` / `model_selection` records, the MLflow copy, the feature contract,
# MAGIC    the hyperparameters and the scikit-learn version match the frozen record in the code.
# MAGIC 2. Check the frozen baseline lookup and persisted split by fingerprint.
# MAGIC 3. For each city in `cities`, score every `model_features` row (training cities get their
# MAGIC    persisted `train`/`test`/`excluded` label; any other configured city is `unseen`).
# MAGIC 4. Publish to `<catalog>.airbnb_gold.<output_table>` keyed by
# MAGIC    `(city, snapshot_date, listing_id, model_version)`: new rows are appended, an identical
# MAGIC    rerun is a no-op, and different content under an existing version stops the notebook.
# MAGIC 5. Reconcile row counts and, for training cities, reproduce the official test MAE.

# COMMAND ----------

import json
import re
import sys
import tempfile
import uuid
from datetime import date, datetime, timezone
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
from airbnb import scoring as sc
from airbnb.model import LOOKUP_COLUMNS

dbutils.widgets.text("catalog", "workspace")
dbutils.widgets.text("cities", "milan,florence")
dbutils.widgets.text("snapshot_date", "")
dbutils.widgets.text("model_version", pm.MODEL_VERSION)
dbutils.widgets.text("output_table", "predictions")
dbutils.widgets.text("code_revision", "")
dbutils.widgets.text("scoring_run_id", "")
catalog = dbutils.widgets.get("catalog").strip()
cities = [c.strip().lower() for c in dbutils.widgets.get("cities").split(",") if c.strip()]
snapshot_override = dbutils.widgets.get("snapshot_date").strip()
model_version = dbutils.widgets.get("model_version").strip()
output_table = dbutils.widgets.get("output_table").strip()
code_revision = dbutils.widgets.get("code_revision").strip()
scoring_run_id = dbutils.widgets.get("scoring_run_id").strip() or f"manual-{uuid.uuid4()}"
for name, value, pattern in (("catalog", catalog, r"[A-Za-z_][A-Za-z0-9_]*"),
                             ("output_table", output_table, r"[A-Za-z_][A-Za-z0-9_]*"),
                             ("model_version", model_version, r"[A-Za-z0-9_.-]+"),
                             ("scoring_run_id", scoring_run_id, r"[A-Za-z0-9_.:-]+")):
    if not re.fullmatch(pattern, value):
        raise ValueError(f"Invalid {name}: {value!r}")
if not re.fullmatch(r"[0-9a-f]{7,40}", code_revision):
    raise ValueError("code_revision (the Git commit being run) is required.")
if not cities or len(set(cities)) != len(cities):
    raise ValueError("cities must be a non-empty comma-separated list without repeats.")

sources = json.loads((root / "config/sources.json").read_text())
unknown = [c for c in cities if c not in sources]
if unknown:
    raise ValueError(f"Cities not in config/sources.json: {unknown}")
snapshots = {c: date.fromisoformat(sources[c]["snapshot_date"]).isoformat() for c in cities}
if snapshot_override:
    if len(cities) != 1 or date.fromisoformat(snapshot_override).isoformat() != snapshots[cities[0]]:
        raise ValueError("snapshot_date must be the configured snapshot of the single city being scored.")

frozen = sc.frozen_model(model_version)
gold = f"{catalog}.airbnb_gold"
table = f"{gold}.{output_table}"
KEYS = list(sc.KEYS)
scored_at = datetime.now(timezone.utc).replace(microsecond=0)
summary = {
    "catalog": catalog, "cities": cities, "snapshots": snapshots, "model_version": model_version,
    "scoring_version": sc.SCORING_VERSION, "prediction_schema_version": sc.PREDICTION_SCHEMA_VERSION,
    "output_table": table, "code_revision": code_revision, "scoring_run_id": scoring_run_id,
    "scored_at": scored_at.isoformat(), "sklearn": sklearn.__version__, "numpy": np.__version__,
    "pandas": pd.__version__, "python": sys.version.split()[0],
}
print(json.dumps(summary, indent=1))


def table_version(name):
    return int(spark.sql(f"DESCRIBE HISTORY {name} LIMIT 1").collect()[0]["version"])


def scope_sql(snaps):
    return " OR ".join(f"(city = '{c}' AND snapshot_date = '{d}')" for c, d in snaps.items())


# COMMAND ----------

# 1. Frozen artifact: file hash, registry rows, MLflow copy, contract.
records = [r.asDict() for r in spark.table(f"{gold}.model_artifacts").where(F.col("model_version") == model_version).collect()]
if len(records) != 1:
    raise sc.FrozenModelError(f"Expected one model_artifacts row for {model_version}, found {len(records)}.")
sc.check_artifact_record(records[0], frozen)
artifact_path = frozen["artifact_path"].format(catalog=catalog)
if records[0]["artifact_path"] != artifact_path:
    raise sc.FrozenModelError(f"model_artifacts path {records[0]['artifact_path']} != {artifact_path}")
artifact_bytes = Path(artifact_path).read_bytes()
if len(artifact_bytes) != frozen["artifact_bytes"]:
    raise sc.FrozenModelError(f"artifact has {len(artifact_bytes)} bytes, frozen record says {frozen['artifact_bytes']}")
model = sc.load_artifact(artifact_bytes, frozen)  # checks SHA-256 before unpickling
sc.check_model_contract(model, frozen, sklearn.__version__)

selection = [r.asDict() for r in spark.table(f"{gold}.model_selection").where(F.col("model_version") == model_version).collect()]
if len(selection) != 1 or pm.sha256_text(selection[0]["record_json"]) != frozen["selection_record_sha256"] \
        or selection[0]["record_sha256"] != frozen["selection_record_sha256"] or selection[0]["spec_sha256"] != frozen["spec_sha256"]:
    raise sc.FrozenModelError("model_selection does not hold exactly the frozen, hash-consistent selection record.")
record_copy = Path(artifact_path).with_name("selection_record.json").read_bytes()
if sc.sha256_bytes(record_copy) != frozen["selection_record_sha256"]:
    raise sc.FrozenModelError("selection_record.json next to the artifact does not match the frozen hash.")
if json.loads(selection[0]["record_json"])["selected_candidate"]["name"] != frozen["selected_candidate"]:
    raise sc.FrozenModelError("locked selection names a different candidate.")

import mlflow
with tempfile.TemporaryDirectory() as tmp:
    mlflow_copy = Path(mlflow.artifacts.download_artifacts(run_id=frozen["mlflow_run_id"], artifact_path="model.joblib", dst_path=tmp))
    mlflow_sha = sc.sha256_bytes(mlflow_copy.read_bytes())
if mlflow_sha != frozen["artifact_sha256"]:
    raise sc.FrozenModelError(f"MLflow run {frozen['mlflow_run_id']} holds a different model.joblib ({mlflow_sha}).")
summary["artifact"] = {
    "path": artifact_path, "sha256": sc.sha256_bytes(artifact_bytes), "bytes": len(artifact_bytes),
    "mlflow_run_id": frozen["mlflow_run_id"], "mlflow_copy_sha256": mlflow_sha,
    "selection_record_sha256": frozen["selection_record_sha256"], "spec_sha256": frozen["spec_sha256"],
    "selected_candidate": frozen["selected_candidate"], "contract": "features, hyperparameters, spec and sklearn match",
}
print(json.dumps(summary["artifact"], indent=1))

# COMMAND ----------

# 2. Frozen reference data: baseline lookup and the full persisted training split.
lookup_frame = spark.table(f"{gold}.baseline_lookup").where(F.col("baseline_version") == frozen["baseline_version"])
expected_snaps = ";".join(f"{c}={d}" for c, d in frozen["training_snapshots"].items())
if [tuple(r) for r in lookup_frame.select("split_salt", "training_snapshots").distinct().collect()] != [(frozen["split_salt"], expected_snaps)]:
    raise sc.FrozenModelError("baseline lookup was fitted on a different split or snapshot.")
lookup = lookup_frame.select(*LOOKUP_COLUMNS).toPandas()
split_all = (spark.table(f"{gold}.model_split")
             .where((F.col("split_salt") == frozen["split_salt"]) & F.expr(scope_sql(frozen["training_snapshots"])))
             .select(*KEYS, "evaluation_split").toPandas())
sc.check_reference_data(frozen, lookup, split_all)
split_counts = {c: {s: int(n) for s, n in g["evaluation_split"].fillna("excluded").value_counts().items()}
                for c, g in split_all.groupby("city")}
if split_counts != frozen["split_counts"]:
    raise sc.FrozenModelError(f"persisted split counts changed: {split_counts}")
input_versions = {t: table_version(f"{gold}.{t}") for t in ("model_features", "model_split", "baseline_lookup",
                                                          "model_artifacts", "model_selection", "model_evaluation")}
output_version_before = table_version(table) if spark.catalog.tableExists(table) else None
summary.update(baseline_lookup_fingerprint=sc.lookup_fingerprint(lookup), split_fingerprint=sc.split_fingerprint(split_all),
               split_counts=split_counts, input_versions=input_versions, output_version_before=output_version_before)

# COMMAND ----------

# 3-4. Score and publish one city at a time.
schema = sc.spark_schema_ddl()


def publish(preds):
    frame = spark.createDataFrame(preds.astype(object).where(preds.notna(), None).values.tolist(), schema)
    if not spark.catalog.tableExists(table):
        frame.write.format("delta").mode("error").saveAsTable(table)
        return "created"
    existing_schema = [(f.name, f.dataType.simpleString()) for f in spark.table(table).schema]
    expected = list(sc.PREDICTION_SCHEMA)
    if existing_schema != expected:
        raise sc.FrozenModelError(f"{table} has schema {existing_schema}, expected {sc.PREDICTION_SCHEMA_VERSION} {expected}")
    city, snap = preds["city"].iloc[0], preds["snapshot_date"].iloc[0].isoformat()
    existing = (spark.table(table).where((F.col("model_version") == model_version) & (F.col("city") == city)
                                         & (F.col("snapshot_date") == snap)).toPandas())
    decision = sc.write_decision(existing, preds)
    if decision == "append":
        frame.write.format("delta").mode("append").saveAsTable(table)
    return decision


features_by_city, preds_by_city = {}, {}
feature_version = input_versions["model_features"]
for city in cities:
    features = (spark.table(f"{gold}.model_features")
                .where((F.col("city") == city) & (F.col("snapshot_date") == snapshots[city]))
                .select(*KEYS, "price_eur", *frozen["features"]).toPandas())
    if features.empty:
        raise ValueError(f"model_features has no rows for {city} {snapshots[city]}; run notebooks 01-03 first.")
    is_training = frozen["training_snapshots"].get(city) == snapshots[city]
    split = split_all[split_all["city"] == city] if is_training else None
    features_by_city[city] = features
    preds_by_city[city] = sc.score_listings(features, model, frozen, lookup, split, scoring_run_id=scoring_run_id,
                                            scored_at=scored_at, source_feature_table_version=feature_version)
all_features = pd.concat(features_by_city.values(), ignore_index=True)
scored_frame = pd.concat(preds_by_city.values(), ignore_index=True)
covers_training = set(frozen["training_snapshots"].items()) <= set(snapshots.items())


def check_frame(frame, label):
    recon = sc.reconcile(frame, all_features)
    if recon["missing_from_predictions"] or recon["extra_in_predictions"] or recon["duplicate_keys"] or recon["baseline_null"]:
        raise RuntimeError(f"{label}: reconciliation failed: {recon}")
    out = {"reconciliation": recon}
    if covers_training:
        metrics = sc.official_test_metrics(frame, frozen)
        out["official_test_metrics"] = metrics
        out["max_abs_diff_vs_frozen_mae"] = sc.check_official_metrics(metrics, frozen)
    return out


# Nothing is published unless the in-memory predictions reproduce the official test MAE.
summary["pre_write_checks"] = check_frame(scored_frame, "in-memory")
writes = {city: publish(preds) for city, preds in preds_by_city.items()}
summary["writes"] = writes
print(f"writes: {writes}")

# COMMAND ----------

# 5. Reconcile what is stored (not the in-memory frame).
stored = spark.table(table).where((F.col("model_version") == model_version) & F.expr(scope_sql(snapshots))).toPandas()
post = check_frame(stored, "stored")
summary["reconciliation"] = post["reconciliation"]
summary["rows_by_city"] = sc.counts(stored, ["city"])
summary["by_split"] = sc.counts(stored, ["city", "evaluation_split"])
summary["by_status"] = sc.counts(stored, ["city", "evaluation_split", "prediction_status"])
summary["by_fallback"] = sc.counts(stored, ["city", "baseline_fallback_level"])
summary["by_scoring_exclusion"] = sc.counts(stored, ["city", "scoring_exclusion_reason"])
summary["by_evaluation_exclusion"] = sc.counts(stored, ["city", "evaluation_exclusion_reason"])
summary["stored_run_ids"] = sc.counts(stored, ["scoring_run_id"])
summary["model_null"] = int(stored["model_prediction_eur"].isna().sum())

if covers_training:
    metrics = post["official_test_metrics"]
    summary["official_test_metrics"] = metrics
    summary["max_abs_diff_vs_frozen_mae"] = post["max_abs_diff_vs_frozen_mae"]
    evaluation = (spark.table(f"{gold}.model_evaluation")
                  .where((F.col("model_version") == model_version) & (F.col("evaluation_population") == "test_all_valid_positive_price"))
                  .select("city_group", "n", "model_mae_eur", "baseline_mae_eur").toPandas())
    summary["max_abs_diff_vs_model_evaluation_table"] = float(max(
        max(abs(metrics["model"][r.city_group] - r.model_mae_eur), abs(metrics["baseline"][r.city_group] - r.baseline_mae_eur))
        for r in evaluation.itertuples()))
    if summary["max_abs_diff_vs_model_evaluation_table"] > 1e-9 or any(metrics["n"][r.city_group] != r.n for r in evaluation.itertuples()):
        raise RuntimeError("Stored test predictions do not reproduce airbnb_gold.model_evaluation.")
    display(pd.DataFrame(metrics).reset_index().rename(columns={"index": "city_group"}))

summary["cities_in_table"] = sorted(r["city"] for r in spark.table(table).select("city").distinct().collect())
summary["model_versions_in_table"] = sorted(r["model_version"] for r in spark.table(table).select("model_version").distinct().collect())
summary["output_version_after"] = table_version(table)
print(json.dumps({k: summary[k] for k in ("writes", "reconciliation", "by_split", "by_status", "by_fallback")}, indent=1))

# COMMAND ----------

dbutils.notebook.exit(json.dumps(summary, default=str))
