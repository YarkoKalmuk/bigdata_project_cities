# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "6"
# ///
# MAGIC %md
# MAGIC # Create the Airbnb lakehouse namespaces
# MAGIC Run once on serverless compute. Select an existing catalog you can write to.
# MAGIC This creates empty schemas and a managed volume; it does not load any city.

# COMMAND ----------

import re

dbutils.widgets.text("catalog", "workspace")
catalog = dbutils.widgets.get("catalog").strip()
if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", catalog):
    raise ValueError("Use a catalog name containing letters, digits and underscores.")

for schema in ("airbnb_bronze", "airbnb_silver", "airbnb_gold"):
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS `{catalog}`.`{schema}`")
spark.sql(f"CREATE VOLUME IF NOT EXISTS `{catalog}`.airbnb_bronze.raw_files")
print(f"Upload original files under /Volumes/{catalog}/airbnb_bronze/raw_files/")
print("Setup complete. No data has been loaded or cleaned.")