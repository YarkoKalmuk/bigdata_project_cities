"""Row-preserving silver rules from Maksym's A/B EDA handoff."""

from pyspark.sql import functions as F


NUMERIC_TYPES = {
    "host_id": "bigint",
    "accommodates": "int",
    "bedrooms": "double",
    "beds": "double",
    "bathrooms": "double",
    "minimum_nights": "int",
    "maximum_nights": "int",
    "availability_365": "int",
    "number_of_reviews": "int",
    "number_of_reviews_ltm": "int",
    "host_listings_count": "int",
    "calculated_host_listings_count": "int",
    "review_scores_rating": "double",
    "latitude": "double",
    "longitude": "double",
}
NUMERIC_TYPES.update({name: "int" for name in (
    "availability_30", "availability_60", "availability_90", "availability_eoy",
    "number_of_reviews_l30d", "number_of_reviews_ly",
)})
NUMERIC_TYPES.update({name: "double" for name in (
    "review_scores_accuracy", "review_scores_cleanliness", "review_scores_checkin",
    "review_scores_communication", "review_scores_location", "review_scores_value", "reviews_per_month",
)})
TEXT_FIELDS = ("room_type", "property_type", "neighbourhood_cleansed")
BOOLEAN_FIELDS = ("host_is_superhost", "instant_bookable")
DATE_FIELDS = ("host_since", "first_review", "last_review", "last_scraped", "calendar_last_scraped")
NULL_MARKERS = ("", "None", "N/A", "null")


def prepare_listings(raw, centres=None):
    """Preserve every input row and raw value, add types and explicit quality flags."""
    required = {"id", "price", "room_type", "accommodates", "_city", "_snapshot_date"}
    missing = required - set(raw.columns)
    if missing:
        raise ValueError(f"Bronze columns missing: {sorted(missing)}")

    source_columns = [c for c in raw.columns if not c.startswith("_")]
    metadata = [c for c in raw.columns if c.startswith("_")]
    def normalise(value):
        value = F.trim(value)
        return F.when(~value.isin(*NULL_MARKERS), value)

    silver = raw.select(
        *[F.col(c).alias(f"raw_{c}") for c in source_columns],
        *[normalise(F.col(c)).alias(c) for c in source_columns],
        *[F.col(c) for c in metadata],
        F.col("_city").alias("city"),
        F.col("_snapshot_date").cast("date").alias("snapshot_date"),
    )

    def text(name):
        if name not in source_columns:
            return F.lit(None).cast("string")
        return normalise(F.col(f"raw_{name}"))

    silver = silver.withColumn("listing_id", F.expr("try_cast(trim(raw_id) AS BIGINT)"))
    flags = [
        F.when(F.col("listing_id").isNull() | (F.col("listing_id") <= 0), "invalid_listing_id")
    ]

    # Inside Airbnb commonly uses a dollar-shaped formatting symbol even for EUR
    # cities. Currency comes from the selected region; no FX conversion occurs.
    # Accept only an explicit decimal-dot / comma-thousands grammar. Ambiguous
    # values such as 1.234,56 stay invalid rather than being silently misread.
    price_text = F.regexp_replace(text("price"), r"^[\$€]\s*", "")
    price_pattern = r"^-?(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)(?:\.[0-9]{1,2})?$"
    silver = silver.withColumn(
        "_price_number",
        F.when(price_text.rlike(price_pattern), F.regexp_replace(price_text, ",", "")),
    ).withColumn("price", F.expr("try_cast(_price_number AS DECIMAL(18,2))"))
    flags.extend([
        F.when(text("price").isNull(), "missing_price"),
        F.when(text("price").isNotNull() & F.col("price").isNull(), "invalid_price_format"),
        F.when(F.col("price") <= 0, "nonpositive_price"),
    ])

    for name, dtype in NUMERIC_TYPES.items():
        silver = silver.withColumn(name, text(name))
        silver = silver.withColumn(name, F.expr(f"try_cast(`{name}` AS {dtype})"))
        invalid = F.col(name).isNull()
        if dtype == "double":
            invalid = invalid | F.isnan(name) | (F.abs(F.col(name)) == float("inf"))
            silver = silver.withColumn(name, F.when(~invalid, F.col(name)))
        flags.append(F.when(text(name).isNotNull() & invalid, f"invalid_{name}"))

    for name in TEXT_FIELDS:
        silver = silver.withColumn(name, text(name))
    for name in BOOLEAN_FIELDS:
        value = F.lower(text(name))
        silver = silver.withColumn(
            name,
            F.when(value.isin("t", "true"), F.lit(True))
            .when(value.isin("f", "false"), F.lit(False)),
        )
        flags.append(F.when(text(name).isNotNull() & F.col(name).isNull(), f"invalid_{name}"))

    for name in DATE_FIELDS:
        silver = silver.withColumn(name, text(name))
        silver = silver.withColumn(name, F.expr(f"try_cast(`{name}` AS DATE)"))
        flags.append(F.when(text(name).isNotNull() & F.col(name).isNull(), f"invalid_{name}"))

    bathroom_text = F.lower(text("bathrooms_text"))
    silver = silver.withColumn("_bath_number", F.regexp_extract(bathroom_text, r"([0-9]+(?:\.[0-9]+)?)", 1))
    silver = silver.withColumn(
        "bathrooms_n",
        F.when(bathroom_text.contains("half-bath"), F.lit(0.5))
        .otherwise(F.expr("try_cast(_bath_number AS DOUBLE)")),
    ).withColumn("bath_shared", F.when(bathroom_text.isNotNull(), bathroom_text.contains("shared")))
    flags.append(F.when(bathroom_text.isNotNull() & F.col("bathrooms_n").isNull(), "invalid_bathrooms_text"))
    silver = (
        silver.withColumn("minimum_nights", F.when(F.col("minimum_nights").isNotNull(), F.least("minimum_nights", F.lit(365))))
        .withColumn("long_stay", F.col("minimum_nights") >= 28)
        .withColumn("has_reviews", F.col("number_of_reviews") > 0)
        .withColumn("days_since_last_review", F.datediff("snapshot_date", "last_review"))
        .withColumn("log_host_listings_count", F.when(F.col("host_listings_count") >= 0, F.log1p("host_listings_count")))
    )
    flags.append(F.when(F.col("days_since_last_review") < 0, "review_after_snapshot"))

    centre_lat = F.lit(None).cast("double")
    centre_lon = F.lit(None).cast("double")
    for name, coordinates in (centres or {}).items():
        centre_lat = F.when(F.col("city") == name, F.lit(coordinates[0])).otherwise(centre_lat)
        centre_lon = F.when(F.col("city") == name, F.lit(coordinates[1])).otherwise(centre_lon)
    lat = F.radians(F.col("latitude"))
    lat_c = F.radians(centre_lat)
    lon_delta = F.radians(F.col("longitude") - centre_lon)
    haversine = F.pow(F.sin((lat - lat_c) / 2), 2) + F.cos(lat) * F.cos(lat_c) * F.pow(F.sin(lon_delta / 2), 2)
    valid_coordinates = F.col("latitude").between(-90, 90) & F.col("longitude").between(-180, 180) & centre_lat.isNotNull()
    silver = silver.withColumn("dist_center_km", F.when(valid_coordinates, 6371.0088 * 2 * F.asin(F.sqrt(F.least(F.lit(1.0), F.greatest(F.lit(0.0), haversine))))))
    flags.append(F.when(centre_lat.isNull(), "missing_city_centre"))

    flags.extend([
        F.when(F.col("room_type").isNull(), "missing_room_type"),
        F.when(F.col("accommodates").isNull(), "missing_or_invalid_accommodates"),
        F.when(F.col("accommodates") <= 0, "nonpositive_accommodates"),
        F.when(~F.col("availability_365").between(0, 365), "availability_out_of_range"),
        F.when(~F.col("latitude").between(-90, 90), "latitude_out_of_range"),
        F.when(~F.col("longitude").between(-180, 180), "longitude_out_of_range"),
    ])
    silver = silver.withColumn("quality_flags", F.filter(F.array(*flags), lambda x: x.isNotNull()))
    # Predictor quality is visible but not a target-based exclusion. The model
    # owner decides how to handle missing predictors using training data only.
    excluded = F.array(
        F.when(F.col("listing_id").isNull() | (F.col("listing_id") <= 0), "invalid_listing_id"),
        F.when(F.col("price").isNull(), "missing_or_invalid_price"),
        F.when(F.col("price") <= 0, "nonpositive_price"),
    )
    silver = (
        silver.withColumn("exclusion_reasons", F.filter(excluded, lambda x: x.isNotNull()))
        .withColumn("eligible_for_training", F.size("exclusion_reasons") == 0)
        .withColumn("currency", F.lit("EUR"))
        .withColumn("price_eur", F.col("price").cast("double"))
        .drop("_price_number", "_bath_number")
    )
    # Snapshot-wide percentiles are descriptive only. Never use these thresholds
    # to tune a model or to filter the headline held-out test population.
    percentiles = silver.groupBy("city", "snapshot_date").agg(
        F.percentile_approx(F.when(F.col("price_eur") > 0, F.col("price_eur")), 0.99, 10000).alias("city_price_p99")
    )
    silver = silver.join(percentiles, ["city", "snapshot_date"], "left")
    per_guest = F.when(F.col("accommodates") > 0, F.col("price_eur") / F.col("accommodates"))
    price_class = (
        F.when(text("price").isNull(), "missing_price")
        .when(F.col("price_eur").isNull() | (F.col("price_eur") <= 0), "invalid_price")
        .when((F.col("price_eur") > 3 * F.col("city_price_p99")) | (per_guest > 1000), "extreme_high")
        .when((F.col("price_eur") > F.col("city_price_p99")) & (F.col("number_of_reviews_ltm") == 0), "stale_high")
        .when(F.col("price_eur") > F.col("city_price_p99"), "high_tail")
        .when(F.col("price_eur") < 20, "low_tail")
        .otherwise("normal")
    )
    return (
        silver.withColumn("price_class", price_class)
        .withColumn("exclusion_reason", F.when(F.col("price_class").isin("missing_price", "invalid_price", "extreme_high", "stale_high"), F.col("price_class")))
        .withColumn("eligible_for_analysis", F.col("exclusion_reason").isNull())
    )
