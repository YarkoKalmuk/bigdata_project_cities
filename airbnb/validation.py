"""Cross-layer checks shared by the Job's final task and local Spark tests."""
import math

from pyspark.sql import functions as F

from airbnb.gold import PREDICTORS


def validate_layers(bronze, silver, manifest, gold):
    """Validate frames already restricted to one city/date; return measured counts."""
    def require(condition, message):
        if not condition:
            raise ValueError(message)

    bronze_count = bronze.count()
    require(bronze_count > 0, "Bronze is empty.")
    require(silver.count() == bronze_count, "Silver row count differs from bronze.")
    audit = manifest.select("row_count").collect()
    require(len(audit) == 1 and audit[0].row_count == bronze_count, "Bronze manifest does not match source rows.")
    require(not silver.where(F.col("listing_id").isNull() | (F.col("listing_id") <= 0)).limit(1).count(), "Invalid silver listing IDs.")
    require(not silver.groupBy("listing_id").count().where("count > 1").limit(1).count(), "Duplicate silver keys.")
    require(not silver.where(F.col("price_class").isNull()).limit(1).count(), "Silver contains rows without EDA price classes.")
    ids = silver.select("listing_id")
    bronze_ids = bronze.select(F.expr("try_cast(id AS BIGINT)").alias("listing_id"))
    require(not ids.exceptAll(bronze_ids).limit(1).count() and not bronze_ids.exceptAll(ids).limit(1).count(), "Bronze/silver listing keys differ.")

    features = gold["model_features"]
    expected = {"city", "snapshot_date", "listing_id", "price_eur", "currency", "eligible_for_training", *PREDICTORS}
    require(set(features.columns) == expected, "Model feature schema differs from the explicit allowlist.")
    # Compare the complete public feature rows, not only counts: catches stale
    # values and preserves key multiplicity without accidentally hiding duplicates.
    ordered = sorted(expected)
    wanted = silver.select(*ordered)
    actual = features.select(*ordered)
    require(not actual.exceptAll(wanted).limit(1).count() and not wanted.exceptAll(actual).limit(1).count(), "Model features differ from silver.")
    city = gold["city_metrics"].collect()
    require(len(city) == 1 and city[0].listings == bronze_count, "City metrics count differs from silver.")
    priced = silver.where("eligible_for_analysis").count()
    require(city[0].priced_listings == priced, "City analytical-population count differs from silver.")
    rooms = gold["room_type_metrics"].agg(F.sum("listings").alias("listings"), F.sum("room_type_mix").alias("mix")).first()
    require(rooms.listings == bronze_count and rooms.mix is not None and math.isclose(rooms.mix, 1.0, abs_tol=1e-9), "Room-type counts or shares do not reconcile.")
    neighbourhoods = gold["neighbourhood_metrics"]
    require(neighbourhoods.agg(F.sum("listings").alias("n")).first().n == bronze_count, "Neighbourhood counts do not reconcile.")
    require(not neighbourhoods.where((F.col("priced_listings") < 20) & F.col("median_price_eur").isNotNull()).limit(1).count(), "A small neighbourhood exposes a suppressed median.")
    return {"bronze_rows": bronze_count, "silver_rows": bronze_count, "feature_rows": bronze_count, "analytical_rows": priced}
