# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "6"
# ///
# MAGIC %md
# MAGIC # Publish metrics and model inputs for one city snapshot
# MAGIC Run the updated silver notebook for both A/B cities first. Metrics follow
# MAGIC docs/gold_contract.md. Predictions are produced by Nazar's model, not here.

# COMMAND ----------

import sys
from pathlib import Path

from pyspark.sql import functions as F

root = next((p for p in [Path.cwd(), *Path.cwd().parents] if (p / "config/sources.json").is_file()), None)
if root is None:
    raise ValueError("Run inside the project's Databricks Git folder.")
sys.path.insert(0, str(root))
from airbnb.gold import build_gold
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

# COMMAND ----------

predicate = f"city = '{city}' AND snapshot_date = '{snapshot_date}'"
silver = spark.table(f"{catalog}.airbnb_silver.listings").where(predicate)
if not {"price_class", "eligible_for_analysis", "dist_center_km"}.issubset(silver.columns):
    raise ValueError("Rerun the EDA-updated notebook 02 before building gold.")
count = silver.count()
if not count or silver.where(F.col("price_class").isNull()).limit(1).count():
    raise ValueError("Silver is empty or predates EDA rules; rerun notebook 02 for this city.")
if silver.groupBy("listing_id").count().where("count > 1").limit(1).count():
    raise ValueError("Silver listing key is not unique.")
outputs = build_gold(silver)
if outputs["model_features"].count() != count:
    raise RuntimeError("Model features lost silver rows.")
for name, frame in outputs.items():
    target = f"{catalog}.airbnb_gold.{name}"
    frame.write.format("delta").mode("overwrite").option("replaceWhere", predicate).saveAsTable(target)
    print(f"Published {target} for {city}/{snapshot_date}")
display(spark.table(f"{catalog}.airbnb_gold.city_metrics").orderBy("city", "snapshot_date"))
