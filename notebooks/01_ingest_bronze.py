# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "6"
# ///
# MAGIC %md
# MAGIC # Ingest one training-city snapshot into bronze
# MAGIC Read the setup guide before running. Original files remain in the managed
# MAGIC volume. All source CSV columns stay strings; cleaning belongs in silver.
# MAGIC Run this same notebook separately for Milan and Florence.

# COMMAND ----------

import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from pyspark.sql import functions as F

dbutils.widgets.text("catalog", "workspace")
dbutils.widgets.dropdown("city", "milan", ["milan", "florence"])
dbutils.widgets.text("snapshot_date", "2026-09-19")

dbutils.widgets.text(
    "source_path",
    "/Volumes/workspace/airbnb_bronze/raw_files/milan/2026-09-19/listings.csv.gz"
)

dbutils.widgets.text("source_url", "")

catalog = dbutils.widgets.get("catalog").strip()
city = dbutils.widgets.get("city").strip().lower()
snapshot_date = dbutils.widgets.get("snapshot_date").strip()
source_path = dbutils.widgets.get("source_path").strip()
source_url = "https://data.insideairbnb.com/italy/lombardy/milan/2026-09-19/data/listings.csv.gz"

if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", catalog):
    raise ValueError("Invalid catalog identifier.")
root = next(
    (p for p in [Path.cwd(), *Path.cwd().parents] if (p / "config/sources.json").is_file()),
    None,
)
if root is None:
    raise ValueError("Run this notebook inside the project's Databricks Git folder.")
sources = json.loads((root / "config/sources.json").read_text())
if city not in sources:
    raise ValueError("Week 1 ingestion is restricted to Milan and Florence.")
configured_url = sources[city].get("source_url")
source_url = source_url or configured_url or ""
if configured_url and source_url != configured_url:
    raise ValueError("source_url differs from config/sources.json; reconcile provenance before loading.")
if date.fromisoformat(snapshot_date).isoformat() != snapshot_date:
    raise ValueError("snapshot_date must be YYYY-MM-DD.")
expected_prefix = (
    f"/Volumes/{catalog}/airbnb_bronze/raw_files/{city}/{snapshot_date}/"
)
if source_path != expected_prefix + "listings.csv.gz":
    raise ValueError(f"Upload the original file and set source_path to {expected_prefix}listings.csv.gz")
url = urlparse(source_url)
if (
    url.scheme != "https"
    or url.hostname != "data.insideairbnb.com"
    or not url.path.endswith(f"/{snapshot_date}/data/listings.csv.gz")
    or f"/{city}/" not in url.path
    or url.query
    or url.fragment
):
    raise ValueError("Copy the matching city's dated detailed listings.csv.gz link from Inside Airbnb.")
if snapshot_date != sources[city]["snapshot_date"]:
    raise ValueError("Update config/sources.json and README.md to the verified snapshot date first.")

# COMMAND ----------

# Multi-line descriptions and doubled CSV quotes are common in detailed listings.
# FAILFAST avoids silently discarding malformed CSV records.
raw = (
    spark.read.format("csv")
    .option("header", "true")
    .option("inferSchema", "false")
    .option("multiLine", "true")
    .option("quote", '"')
    .option("escape", '"')
    .option("mode", "FAILFAST")
    .load(source_path)
)
required = {"id", "price", "room_type", "accommodates"}
missing = required - set(raw.columns)
if missing:
    raise ValueError(f"Not a supported detailed listings file; missing columns: {sorted(missing)}")
metadata = {"_city", "_snapshot_date", "_source_path", "_source_url", "_ingested_at"}
if metadata.intersection(raw.columns):
    raise ValueError("Source columns conflict with ingestion metadata.")

row_count = raw.count()
if row_count == 0:
    raise ValueError("Source contains no listings; existing bronze data will not be replaced.")
id_stats = raw.agg(
    F.countDistinct("id").alias("distinct_ids"),
    F.sum(F.when(F.col("id").isNull() | (F.trim("id") == ""), 1).otherwise(0)).alias("missing_ids"),
).first()
if id_stats["missing_ids"] or id_stats["distinct_ids"] != row_count:
    raise ValueError("Source has missing or duplicate listing IDs; inspect the original file before loading.")

bronze = (
    raw.withColumn("_city", F.lit(city))
    .withColumn("_snapshot_date", F.lit(snapshot_date).cast("date"))
    .withColumn("_source_path", F.lit(source_path))
    .withColumn("_source_url", F.lit(source_url))
    .withColumn("_ingested_at", F.current_timestamp())
)

# COMMAND ----------

table = f"{catalog}.airbnb_bronze.listings"
predicate = f"_city = '{city}' AND _snapshot_date = '{snapshot_date}'"
# replaceWhere replaces only this snapshot, retaining the other city and dates.
# Deliberately reject schema drift rather than silently dropping new source columns.
(
    bronze.write.format("delta")
    .mode("overwrite")
    .option("replaceWhere", predicate)
    .saveAsTable(table)
)
stored = spark.table(table).where(predicate)
stored_count = stored.count()
if stored_count != row_count:
    raise RuntimeError(f"Row-count mismatch: source={row_count}, bronze={stored_count}")

# COMMAND ----------

# This manifest describes the current successful load of each snapshot.
# Delta table history retains prior writes; a repeat run updates this manifest row.
manifest = f"{catalog}.airbnb_bronze.ingestion_manifest"
spark.sql(f"""
CREATE TABLE IF NOT EXISTS {manifest} (
    city STRING, snapshot_date DATE, source_path STRING, source_url STRING,
    row_count BIGINT, source_column_count INT, loaded_at TIMESTAMP
) USING DELTA
""")
audit = (
    spark.createDataFrame(
        [(city, snapshot_date, source_path, source_url, row_count, len(raw.columns))],
        "city string, snapshot_date string, source_path string, source_url string, row_count long, source_column_count int",
    )
    .withColumn("snapshot_date", F.to_date("snapshot_date"))
    .withColumn("loaded_at", F.current_timestamp())
)
view = "airbnb_current_ingestion"
audit.createOrReplaceTempView(view)
spark.sql(f"""
MERGE INTO {manifest} AS target
USING {view} AS source
ON target.city = source.city AND target.snapshot_date = source.snapshot_date
WHEN MATCHED THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *
""")
print(f"Loaded {stored_count:,} {city} listings into {table} for {snapshot_date}.")
display(spark.table(manifest).orderBy("city", "snapshot_date"))