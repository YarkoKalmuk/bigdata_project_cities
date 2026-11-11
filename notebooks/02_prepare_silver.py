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

import json
import re
import sys
from datetime import date
from pathlib import Path

from pyspark.sql import functions as F

root = next((p for p in [Path.cwd(), *Path.cwd().parents] if (p / "config/sources.json").is_file()), None)
if root is None:
    raise ValueError("Run inside the project's Databricks Git folder.")
sys.path.insert(0, str(root))
from airbnb.silver import prepare_listings

dbutils.widgets.text("catalog", "workspace")
dbutils.widgets.dropdown("city", "milan", ["milan", "florence"])
dbutils.widgets.text("snapshot_date", "2026-09-19")
catalog = dbutils.widgets.get("catalog").strip()
city = dbutils.widgets.get("city").strip().lower()
snapshot_date = dbutils.widgets.get("snapshot_date").strip()
if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", catalog):
    raise ValueError("Invalid catalog identifier.")
sources = json.loads((root / "config/sources.json").read_text())
if city not in sources:
    raise ValueError("Week 1 inputs are Milan and Florence only.")
if date.fromisoformat(snapshot_date).isoformat() != snapshot_date or snapshot_date != sources[city]["snapshot_date"]:
    raise ValueError("Use the snapshot date recorded in config/sources.json.")
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
centres = {name: (source["centre_latitude"], source["centre_longitude"]) for name, source in sources.items()}
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