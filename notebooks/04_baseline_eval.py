# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "6"
# ///
# MAGIC %md
# MAGIC # Persist the train/test split and evaluate the required baseline (Milan + Florence)
# MAGIC Run notebook 03 for both training cities first. Logic lives in `airbnb/model.py`;
# MAGIC decisions are documented in `docs/model_feature_review.md`.
# MAGIC
# MAGIC 1. Read `<catalog>.airbnb_gold.model_features` for the configured training snapshots.
# MAGIC 2. Assign the hash split (fixed salt) and persist it to `airbnb_gold.model_split`.
# MAGIC 3. Re-read the persisted split, fit the pooled baseline on training rows only and
# MAGIC    persist it to `airbnb_gold.baseline_lookup`.
# MAGIC 4. Show held-out baseline MAE for Milan, Florence and both.
# MAGIC
# MAGIC Writes are write-once per version: a rerun with identical content is a no-op, and
# MAGIC different content under an existing version stops the notebook instead of overwriting it.

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
from airbnb.model import (
    LOOKUP_COLUMNS, SPLIT_SALT, SPLIT_TEST_SHARE, TRAINING_CITIES,
    assign_split, fit_baseline, mae_table, predict_baseline, split_summary,
)

dbutils.widgets.text("catalog", "workspace")
dbutils.widgets.text("baseline_version", "baseline-v1")
catalog = dbutils.widgets.get("catalog").strip()
baseline_version = dbutils.widgets.get("baseline_version").strip()
if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", catalog):
    raise ValueError("Invalid catalog identifier.")
if not re.fullmatch(r"[A-Za-z0-9_.-]+", baseline_version):
    raise ValueError("Invalid baseline_version.")

sources = json.loads((root / "config/sources.json").read_text())
missing = [c for c in TRAINING_CITIES if c not in sources]
if missing:
    raise ValueError(f"Training cities missing from config/sources.json: {missing}")
snapshots = {c: date.fromisoformat(sources[c]["snapshot_date"]).isoformat() for c in TRAINING_CITIES}
scope = " OR ".join(f"(city = '{c}' AND snapshot_date = '{d}')" for c, d in snapshots.items())
training_snapshots = ";".join(f"{c}={d}" for c, d in snapshots.items())
gold = f"{catalog}.airbnb_gold"
print(f"Training snapshots: {training_snapshots}; split salt: {SPLIT_SALT}; baseline: {baseline_version}")

# COMMAND ----------


def publish_once(frame, table, predicate):
    """Write ``frame`` unless ``predicate`` already selects rows; then require identical content."""
    if not spark.catalog.tableExists(table):
        frame.write.format("delta").mode("errorifexists").saveAsTable(table)
        return "created"
    existing = spark.table(table).where(predicate)
    if not existing.limit(1).count():
        frame.write.format("delta").mode("append").saveAsTable(table)
        return "appended"
    existing = existing.select(*frame.columns)
    if existing.exceptAll(frame).limit(1).count() or frame.exceptAll(existing).limit(1).count():
        raise RuntimeError(
            f"{table} already holds different rows for [{predicate}]. "
            "Do not overwrite a persisted version: choose a new version and record why."
        )
    return "unchanged"


# COMMAND ----------

KEYS = ["city", "snapshot_date", "listing_id"]
features = spark.table(f"{gold}.model_features").where(scope)
required = {*KEYS, "price_eur", "eligible_for_training", "room_type", "accommodates"}
if not required.issubset(features.columns):
    raise ValueError(f"model_features lacks {sorted(required - set(features.columns))}; rerun notebook 03.")
counts = {r["city"]: r["count"] for r in features.groupBy("city").count().collect()}
if any(not counts.get(c) for c in TRAINING_CITIES):
    raise ValueError(f"model_features has no rows for some training city: {counts}")
print(f"model_features rows: {counts}")

# The split reads keys and the structural eligibility flag only, never prices.
key_frame = features.select(*KEYS, "eligible_for_training").toPandas()
split = assign_split(key_frame, test_share=SPLIT_TEST_SHARE, salt=SPLIT_SALT)
split["split_salt"] = SPLIT_SALT
split["split_test_share"] = float(SPLIT_TEST_SHARE)
split_columns = [*KEYS, "evaluation_split", "split_exclusion_reason", "split_salt", "split_test_share"]
split_frame = spark.createDataFrame(
    split[split_columns].astype(object).where(split[split_columns].notna(), None).values.tolist(),
    "city string, snapshot_date date, listing_id bigint, evaluation_split string, "
    "split_exclusion_reason string, split_salt string, split_test_share double",
)
status = publish_once(split_frame, f"{gold}.model_split", f"split_salt = '{SPLIT_SALT}' AND ({scope})")
print(f"{gold}.model_split: {status}")

# COMMAND ----------

# Use the persisted split, not the in-memory one, so every later model reads the same rows.
persisted = spark.table(f"{gold}.model_split").where(f"split_salt = '{SPLIT_SALT}' AND ({scope})")
rows = (
    features.select(*KEYS, "price_eur", "room_type", "accommodates")
    .join(persisted.select(*KEYS, "evaluation_split", "split_exclusion_reason"), KEYS, "left")
)
data = rows.toPandas()
if len(data) != sum(counts.values()) or data["evaluation_split"].isna().sum() != split["evaluation_split"].isna().sum():
    raise RuntimeError("Persisted split does not cover model_features exactly.")
display(split_summary(data))

# COMMAND ----------

lookup = fit_baseline(data)  # uses evaluation_split == 'train' rows only
lookup.insert(0, "training_snapshots", training_snapshots)
lookup.insert(0, "split_salt", SPLIT_SALT)
lookup.insert(0, "baseline_version", baseline_version)
lookup_frame = spark.createDataFrame(
    lookup.astype(object).where(lookup.notna(), None).values.tolist(),
    "baseline_version string, split_salt string, training_snapshots string, baseline_level string, "
    "room_type string, accommodates int, median_price_eur double, n_train bigint",
)
status = publish_once(lookup_frame, f"{gold}.baseline_lookup", f"baseline_version = '{baseline_version}'")
print(f"{gold}.baseline_lookup: {status}")

stored = spark.table(f"{gold}.baseline_lookup").where(F.col("baseline_version") == baseline_version)
if stored.select("split_salt", "training_snapshots").distinct().collect() != [(SPLIT_SALT, training_snapshots)]:
    raise RuntimeError("baseline_version was fitted on a different split or snapshot; choose a new version.")
stored_lookup = stored.select(*LOOKUP_COLUMNS).toPandas()

# COMMAND ----------

scored = predict_baseline(data, stored_lookup)
display(
    scored[scored["evaluation_split"] == "test"]
    .groupby(["city", "baseline_level"]).size().rename("test_rows").reset_index()
)
metrics = mae_table(scored, "baseline_prediction_eur")
metrics.insert(0, "baseline_version", baseline_version)
metrics.insert(1, "split_salt", SPLIT_SALT)
display(metrics)
