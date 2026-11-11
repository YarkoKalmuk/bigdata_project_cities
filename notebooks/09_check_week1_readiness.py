# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "6"
# ///
# MAGIC %md
# MAGIC # Read-only A/B integration readiness check
# MAGIC Run in the workspace holding Nazar's price-v1 artifact and reference tables.
# MAGIC Reads A/B metadata, artifact bytes and stored predictions. Does not train,
# MAGIC score, write tables, grant permissions, tag Git or access a new city.

# COMMAND ----------
import json
import sys
from pathlib import Path

from databricks.sdk import WorkspaceClient
from pyspark.sql import functions as F

root = next((p for p in [Path.cwd(), *Path.cwd().parents] if (p / "config/sources.json").is_file()), None)
if root is None:
    raise ValueError("Open the integrated project Git folder.")
sys.path.insert(0, str(root))
from airbnb.inputs import identifier
from airbnb import price_model as pm
from airbnb import scoring as sc
from airbnb.model import LOOKUP_COLUMNS

dbutils.widgets.text("catalog", "workspace")
dbutils.widgets.text("job_id", "")
catalog = identifier(dbutils.widgets.get("catalog"), "catalog")
job_id = dbutils.widgets.get("job_id").strip()
client = WorkspaceClient()
report = {"workspace_host": client.config.host, "catalog": catalog, "job_id": job_id or None}
if job_id:
    if not job_id.isdigit():
        raise ValueError("job_id must be numeric, or blank to skip the Job lookup.")
    job = client.jobs.get(job_id=int(job_id))
    report["job_name"] = job.settings.name
    report["job_git_source"] = job.settings.git_source.as_dict() if job.settings.git_source else None
print(json.dumps(report, indent=2))

# COMMAND ----------
frozen = sc.frozen_model("price-v1")
gold = f"{catalog}.airbnb_gold"
scope = " OR ".join(f"(city = '{city}' AND snapshot_date = '{snapshot}')" for city, snapshot in frozen["training_snapshots"].items())
report["tables"] = {}
for name in ("model_features", "model_split", "baseline_lookup", "model_artifacts", "model_evaluation", "predictions"):
    table = f"{gold}.{name}"
    report["tables"][name] = {"version": int(spark.sql(f"DESCRIBE HISTORY {table} LIMIT 1").first()["version"])}
features = spark.table(f"{gold}.model_features").where(scope).select(*sc.KEYS).toPandas()
predictions = spark.table(f"{gold}.predictions").where(scope).where(F.col("model_version") == "price-v1").toPandas()
reconciliation = sc.reconcile(predictions, features)
if any(reconciliation[key] for key in ("duplicate_keys", "missing_from_predictions", "extra_in_predictions", "baseline_null")):
    raise RuntimeError(f"Prediction reconciliation failed: {reconciliation}")
# Recompute errors from stored values rather than trusting stored error columns.
predictions["absolute_error_eur"] = (predictions["model_prediction_eur"] - predictions["actual_price_eur"]).abs()
predictions["baseline_absolute_error_eur"] = (predictions["baseline_prediction_eur"] - predictions["actual_price_eur"]).abs()
metrics = sc.official_test_metrics(predictions, frozen)
sc.check_official_metrics(metrics, frozen)
split = (spark.table(f"{gold}.model_split").where(scope)
         .where(F.col("split_salt") == frozen["split_salt"]).select(*sc.KEYS, "evaluation_split").toPandas())
lookup = (spark.table(f"{gold}.baseline_lookup").where(F.col("baseline_version") == frozen["baseline_version"])
          .select(*LOOKUP_COLUMNS).toPandas())
sc.check_reference_data(frozen, lookup, split)
records = spark.table(f"{gold}.model_artifacts").where(F.col("model_version") == "price-v1").collect()
if len(records) != 1:
    raise RuntimeError("Expected exactly one price-v1 artifact record.")
sc.check_artifact_record(records[0].asDict(), frozen)
artifact = Path(frozen["artifact_path"].format(catalog=catalog)).read_bytes()
if len(artifact) != frozen["artifact_bytes"] or sc.sha256_bytes(artifact) != frozen["artifact_sha256"]:
    raise RuntimeError("Stored model artifact does not match price-v1.")
if pm.sha256_text(pm.canonical_json(pm.model_spec())) != frozen["spec_sha256"]:
    raise RuntimeError("Integrated model specification differs from price-v1.")
report.update(
    reconciliation=reconciliation, official_test_metrics=metrics,
    split_fingerprint=sc.split_fingerprint(split), baseline_fingerprint=sc.lookup_fingerprint(lookup),
    artifact_sha256=sc.sha256_bytes(artifact),
    status="A/B reference-data checks passed; freeze is still a separate milestone",
)
print(json.dumps(report, indent=2))
dbutils.notebook.exit(json.dumps(report))
