# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "6"
# ///
# MAGIC %md
# MAGIC # Verify a complete city run and record success
# MAGIC This task runs only after gold succeeds. Failed runs remain visible in Job
# MAGIC history; they do not get a successful-validation record.

# COMMAND ----------
import sys
import hashlib
import json
from pathlib import Path
from uuid import uuid4

from pyspark.sql import functions as F

root = next((p for p in [Path.cwd(), *Path.cwd().parents] if (p / "config/sources.json").is_file()), None)
if root is None:
    raise ValueError("Run from the project Git source.")
sys.path.insert(0, str(root))
from airbnb.validation import validate_layers
from airbnb.inputs import load_sources, resolve_snapshot

for key, default in (("catalog", "workspace"), ("city", "milan"), ("snapshot_date", "2026-09-19"), ("sources_config_path", ""), ("job_id", "manual"), ("job_run_id", "")):
    dbutils.widgets.text(key, default)
catalog = dbutils.widgets.get("catalog").strip()
city = dbutils.widgets.get("city").strip().lower()
snapshot_date = dbutils.widgets.get("snapshot_date").strip()
sources = load_sources(root, catalog, dbutils.widgets.get("sources_config_path"))
parameters = resolve_snapshot(sources, catalog, city, snapshot_date)
catalog, city, snapshot_date = parameters.catalog, parameters.city, parameters.snapshot_date
predicate = f"city = '{city}' AND snapshot_date = '{snapshot_date}'"
bronze = spark.table(f"{catalog}.airbnb_bronze.listings").where(f"_city = '{city}' AND _snapshot_date = '{snapshot_date}'")
silver = spark.table(f"{catalog}.airbnb_silver.listings").where(predicate)
manifest = spark.table(f"{catalog}.airbnb_bronze.ingestion_manifest").where(predicate)
gold = {name: spark.table(f"{catalog}.airbnb_gold.{name}").where(predicate) for name in ("city_metrics", "room_type_metrics", "neighbourhood_metrics", "model_features")}
counts = validate_layers(bronze, silver, manifest, gold)

# COMMAND ----------
job_id = dbutils.widgets.get("job_id")
run_id = dbutils.widgets.get("job_run_id") or f"manual-{uuid4()}"
record = spark.createDataFrame(
    [(job_id, run_id, city, snapshot_date, counts["bronze_rows"], counts["silver_rows"], counts["feature_rows"], counts["analytical_rows"])],
    "job_id string, job_run_id string, city string, snapshot_date string, bronze_rows long, silver_rows long, feature_rows long, analytical_rows long",
).withColumn("snapshot_date", F.to_date("snapshot_date")).withColumn("validated_at", F.current_timestamp())
record = record.withColumn(
    "sources_config_path", F.lit(dbutils.widgets.get("sources_config_path").strip() or "repo:config/sources.json")
).withColumn(
    "sources_config_sha256", F.lit(hashlib.sha256(json.dumps(sources, sort_keys=True).encode()).hexdigest())
)
audit_table = f"{catalog}.airbnb_gold.pipeline_validations"
record.write.format("delta").mode("append").option("mergeSchema", "true").saveAsTable(audit_table)
display(record)
print(f"Validation passed; evidence appended to {audit_table}. Save the Job run URL and its Git commit too.")
