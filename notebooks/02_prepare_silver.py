# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "6"
# ///
# MAGIC %md
# MAGIC # Type one city snapshot and expose quality problems
# MAGIC Run bronze first. Applies the EDA handoff rules, preserving every row and
# MAGIC raw value. Outlier classes are descriptive; no imputation is fitted here.

# COMMAND ----------

import sys
from pathlib import Path

from pyspark.sql import functions as F

root = next((p for p in [Path.cwd(), *Path.cwd().parents] if (p / "config/sources.json").is_file()), None)
if root is None:
    raise ValueError("Run inside the project's Databricks Git folder.")
sys.path.insert(0, str(root))
from airbnb.silver import prepare_listings
from airbnb.inputs import load_sources, resolve_snapshot

dbutils.widgets.text("catalog", "workspace")
dbutils.widgets.text("city", "milan")
dbutils.widgets.text("sources_config_path", "")
dbutils.widgets.text("snapshot_date", "2026-09-19")
catalog = dbutils.widgets.get("catalog").strip()
city = dbutils.widgets.get("city").strip().lower()
snapshot_date = dbutils.widgets.get("snapshot_date").strip()
sources = load_sources(root, catalog, dbutils.widgets.get("sources_config_path"))
parameters = resolve_snapshot(sources, catalog, city, snapshot_date)
catalog, city, snapshot_date = parameters.catalog, parameters.city, parameters.snapshot_date

predicate = f"_city = '{city}' AND _snapshot_date = '{snapshot_date}'"

# COMMAND ----------

bronze = spark.table(f"{catalog}.airbnb_bronze.listings").where(predicate)
source_count = bronze.count()
if not source_count:
    raise ValueError(f"No bronze rows for {city}/{snapshot_date}; ingest that city first.")
manifest = spark.table(f"{catalog}.airbnb_bronze.ingestion_manifest").where(
    (F.col("city") == city) & (F.col("snapshot_date") == snapshot_date)
).collect()
if len(manifest) != 1 or manifest[0]["row_count"] != source_count:
    raise ValueError("Bronze manifest is missing or inconsistent; complete notebook 01 first.")
centres = {city: parameters.centre} if parameters.centre is not None else {}
silver = prepare_listings(bronze, centres)
if silver.where(F.col("listing_id").isNull() | (F.col("listing_id") <= 0)).limit(1).count():
    raise ValueError("Listing IDs cannot form the silver key; inspect bronze before writing.")
if silver.groupBy("city", "snapshot_date", "listing_id").count().where("count > 1").limit(1).count():
    raise ValueError("Duplicate silver keys after ID casting; existing silver will not be replaced.")

# COMMAND ----------

target = f"{catalog}.airbnb_silver.listings"
silver.write.format("delta").mode("overwrite").option("mergeSchema", "true").option("replaceWhere", predicate).saveAsTable(target)
stored = spark.table(target).where(predicate)
if stored.count() != source_count:
    raise RuntimeError("Bronze/silver count mismatch.")
display(stored.groupBy("city", "snapshot_date", "eligible_for_training").count())
display(stored.groupBy("city", "snapshot_date", "price_class").count())
display(stored.select("city", F.explode("quality_flags").alias("quality_flag")).groupBy("city", "quality_flag").count())
print(f"Prepared {source_count:,} rows in {target}; no rows dropped.")
