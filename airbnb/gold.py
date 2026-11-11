"""EDA-defined dashboard metrics and an explicit model input contract."""
from pyspark.sql import functions as F


# No raw columns, price quotes, revenue/occupancy estimates, identifiers as
# predictors, or target-derived outlier classes enter this allowlist.
PREDICTORS = (
    "room_type", "property_type", "accommodates", "bedrooms", "beds",
    "bathrooms_n", "bath_shared", "minimum_nights", "long_stay", "dist_center_km",
    "has_reviews", "review_scores_rating", "review_scores_accuracy",
    "review_scores_cleanliness", "review_scores_checkin", "review_scores_communication",
    "review_scores_location", "review_scores_value", "log_host_listings_count",
    "host_is_superhost", "instant_bookable",
)


def build_gold(silver):
    """Build one city's/snapshot's gold outputs without dropping source listings."""
    keys = ["city", "snapshot_date"]
    # Match the EDA's city median population: positive prices except extreme_high,
    # including stale_high. Modelling-population counts exclude stale_high too.
    median_price = F.when(
        ~F.col("price_class").isin("missing_price", "invalid_price", "extreme_high"), F.col("price_eur")
    )
    valid_availability = F.when(F.col("availability_365").between(0, 365), F.col("availability_365"))

    def aggregates(price_value):
        return [
            F.countDistinct("listing_id").alias("listings"),
            F.sum(F.col("eligible_for_analysis").cast("long")).alias("priced_listings"),
            F.percentile_approx(price_value, 0.5, 10000).alias("median_price_eur"),
            (F.avg(valid_availability) / 365).alias("open_days_share_365"),
            F.count(valid_availability).alias("availability_observations"),
            F.avg(F.when(valid_availability.isNotNull(), (valid_availability == 0).cast("double"))).alias("share_blocked"),
            F.avg(F.when(F.col("has_reviews"), F.col("review_scores_rating"))).alias("avg_review_score"),
            F.countDistinct("host_id").alias("hosts"),
            F.avg(F.when(F.col("calculated_host_listings_count").isNotNull(), (F.col("calculated_host_listings_count") >= 2).cast("double"))).alias("share_multi_listing_hosts"),
        ]

    city = silver.groupBy(*keys).agg(*aggregates(median_price))
    room = silver.groupBy(*keys, "room_type").agg(*aggregates(median_price))
    room = room.join(city.select(*keys, F.col("listings").alias("city_listings")), keys).withColumn(
        "room_type_mix", F.col("listings") / F.col("city_listings")
    ).drop("city_listings")
    neighbourhood = silver.groupBy(*keys, "neighbourhood_cleansed").agg(
        *aggregates(F.when(F.col("eligible_for_analysis"), F.col("price_eur")))
    ).withColumn(
        "median_price_eur", F.when(F.col("priced_listings") >= 20, F.col("median_price_eur"))
    ).withColumn("meets_price_sample_minimum", F.col("priced_listings") >= 20)
    features = silver.select(
        "city", "snapshot_date", "listing_id", "price_eur", "currency",
        "eligible_for_training", *PREDICTORS,
    )
    return {
        "city_metrics": city,
        "room_type_metrics": room,
        "neighbourhood_metrics": neighbourhood,
        "model_features": features,
    }
