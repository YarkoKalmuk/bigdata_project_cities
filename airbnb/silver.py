"""Conservative, row-preserving silver preparation; no learned cleaning rules."""

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
    "review_scores_rating": "double",
    "latitude": "double",
    "longitude": "double",
}
TEXT_FIELDS = ("room_type", "property_type", "neighbourhood_cleansed")
BOOLEAN_FIELDS = ("host_is_superhost", "instant_bookable")


def prepare_listings(raw):
    """Preserve every input row and raw value, add types and explicit quality flags."""
    required = {"id", "price", "room_type", "accommodates", "_city", "_snapshot_date"}
    missing = required - set(raw.columns)
    if missing:
        raise ValueError(f"Bronze columns missing: {sorted(missing)}")

    source_columns = [c for c in raw.columns if not c.startswith("_")]
    metadata = [c for c in raw.columns if c.startswith("_")]
    silver = raw.select(
        *[F.col(c).alias(f"raw_{c}") for c in source_columns],
        *[F.col(c) for c in metadata],
        F.col("_city").alias("city"),
        F.col("_snapshot_date").cast("date").alias("snapshot_date"),
    )

    def text(name):
        if name not in source_columns:
            return F.lit(None).cast("string")
        value = F.trim(F.col(f"raw_{name}"))
        return F.when(value != "", value)

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
    return (
        silver.withColumn("exclusion_reasons", F.filter(excluded, lambda x: x.isNotNull()))
        .withColumn("eligible_for_training", F.size("exclusion_reasons") == 0)
        .withColumn("currency", F.lit("EUR"))
        .drop("_price_number")
    )
