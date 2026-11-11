# Databricks notebook source
# MAGIC %md
# MAGIC # Exploratory analysis — Milan (A) and Florence (B)
# MAGIC
# MAGIC **Owner:** Matseliukh Maksym · **Data:** Inside Airbnb detailed `listings.csv.gz`, snapshot **2026-09-19** for both cities (CC BY 4.0) · **Currency:** EUR
# MAGIC
# MAGIC Venice (city C) is deliberately **not** loaded or explored here; it stays unseen until the Week 1 freeze.
# MAGIC
# MAGIC ## Summary
# MAGIC
# MAGIC ### What we now know
# MAGIC 1. **Grain:** one row = one listing (`id`) as seen by the scraper on the snapshot. `id` is unique and never missing in both cities. Milan has **25,338** listings, Florence **13,571**. The scrape ran over two days (`last_scraped` 2026-09-20/21), one day after the nominal snapshot date.
# MAGIC 2. **Target:** `price` is a string like `$1,234.50` — the symbol is `$` but the value is **EUR** (the embedded quote says `"currency": "EUR"`). It must be parsed by stripping `$` and `,`.
# MAGIC 3. **Price is missing for 14.5 % (Milan) and 10.5 % (Florence) of listings, and not at random.** 95 % (Milan) / 73 % (Florence) of listings with `availability_365 = 0` have no price, against ~4 % of the rest; missingness also rises for listings with no review in the last 12 months. Missing price = mostly **inactive / blocked listings**, not a parsing error. They are excluded from training and evaluation but kept in silver with a reason.
# MAGIC 4. **Price is heavily right-skewed.** Median 164 € (Milan) and 198 € (Florence), p99 ≈ 1,100–1,200 €, max 88,100 € (Milan). We model `log(price)` and classify outliers instead of silently dropping them (section 5).
# MAGIC 5. **Two kinds of `price` exist.** 11 % of Milan and 5 % of Florence listings are *monthly-priced*: their `price` is the monthly total spread over the nights of a ~30-night quote, so it is roughly half of a normal nightly price (median 93 € vs 170 € in Milan). This flag (derivable from `minimum_nights >= 28` without touching the price) is a genuine predictor and must be a model feature.
# MAGIC 6. **14 columns are 100 % empty in this snapshot in both cities** (e.g. `host_since`, `host_response_rate`, `bathrooms`, `neighbourhood_group_cleansed`, `instant_bookable`, `calendar_updated`). They cannot be used; `bathrooms` must be parsed from `bathrooms_text`. One of them, `host_verifications`, is not literally empty but holds the string `"None"` — Spark reads it as a value, so the pipeline must map textual null markers to null.
# MAGIC 7. **Review scores are missing exactly when `number_of_reviews = 0`** (structural, 14.5 % Milan, 9.4 % Florence). Impute with a flag, not with the mean alone.
# MAGIC 8. **Leakage:** `price_quote_price_per_night` equals `price` for 100 % of rows; `price_quote_total_price` = nightly price × nights; `price_quote_raw` contains the price as text; `estimated_revenue_l365d` = `estimated_occupancy_l365d` × `price` (ratio 1.000 ± 0.001). These four must never be features (section 7).
# MAGIC 9. **Neighbourhoods are not comparable across cities:** Milan has 87 `neighbourhood_cleansed` values, Florence only 5 (70 % of Florence listings are in *Centro Storico*). A neighbourhood feature learned on A/B will not transfer to a new city — location should also be encoded as distance to the city centre from `latitude`/`longitude`.
# MAGIC 10. **Florence is ~20 % more expensive than Milan** at the median, and the gap holds within room type (entire home 209 € vs 169 €). A model must know the city (or a city-level price level) — a key risk for city C.
# MAGIC
# MAGIC ### What we still do not know
# MAGIC - Whether `price` reflects what guests actually pay (it is one quote on one date range; seasonality and cleaning fees are not captured).
# MAGIC - Why exactly the high outliers (> 2,000 €/night) exist: most have no reviews in 12 months and are probably placeholder/blocking prices, but some are real luxury villas. We flag rather than prove.
# MAGIC - Whether the 14 empty host/bathroom columns are permanently gone or only empty in this scrape (they may be populated in Venice's snapshot — the pipeline must tolerate both).
# MAGIC - Whether the price level and neighbourhood structure of the new city will look like Milan or Florence (by design — city C is unseen).
# MAGIC
# MAGIC ### Contents
# MAGIC 1. Parameters and loading · 2. Dataset description · 3. Column profile and missingness · 4. Price and availability distributions · 5. Outliers · 6. Cleaning rules for the pipeline · 7. Leakage review · 8. Transfer risks · 9. Proposed gold metric definitions

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Parameters and loading
# MAGIC The notebook reads the **original** compressed files from a Unity Catalog volume, so it does not depend on any pipeline table and can be re-run on its own.
# MAGIC Expected layout (same as the bronze ingestion): `/Volumes/<catalog>/<schema>/<volume>/<city>/<snapshot_date>/listings.csv.gz`.
# MAGIC If a file is missing, the notebook tries to download it from Inside Airbnb into the volume (works when serverless has internet access; otherwise upload the file manually).

# COMMAND ----------

import math
import urllib.request
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from pyspark.sql import Window
from pyspark.sql import functions as F

dbutils.widgets.text("catalog", "workspace")
dbutils.widgets.text("schema", "airbnb_bronze")
dbutils.widgets.text("volume", "raw_files")
catalog = dbutils.widgets.get("catalog").strip()
schema = dbutils.widgets.get("schema").strip()
volume = dbutils.widgets.get("volume").strip()

# Training cities only. Venice is intentionally absent.
CITIES = {
    "milan": {
        "snapshot_date": "2026-09-19",
        "url": "https://data.insideairbnb.com/italy/lombardy/milan/2026-09-19/data/listings.csv.gz",
    },
    "florence": {
        "snapshot_date": "2026-09-19",
        "url": "https://data.insideairbnb.com/italy/toscana/florence/2026-09-19/data/listings.csv.gz",
    },
}
SNAPSHOT_REF = "2026-09-19"

spark.sql(f"CREATE SCHEMA IF NOT EXISTS `{catalog}`.`{schema}`")
spark.sql(f"CREATE VOLUME IF NOT EXISTS `{catalog}`.`{schema}`.`{volume}`")


def raw_path(city: str) -> str:
    return f"/Volumes/{catalog}/{schema}/{volume}/{city}/{CITIES[city]['snapshot_date']}/listings.csv.gz"


for city, meta in CITIES.items():
    path = Path(raw_path(city))
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        print(f"Downloading {city} from {meta['url']}")
        urllib.request.urlretrieve(meta["url"], str(path))
    print(f"{city}: {path} ({path.stat().st_size / 1e6:.1f} MB)")

# COMMAND ----------

# Detailed listings contain multi-line descriptions and doubled quotes.
# Everything is read as string first: typing is part of what we profile.
frames = []
for city in CITIES:
    df_city = (
        spark.read.format("csv")
        .option("header", "true")
        .option("inferSchema", "false")
        .option("multiLine", "true")
        .option("quote", '"')
        .option("escape", '"')
        .option("mode", "FAILFAST")
        .load(raw_path(city))
        .withColumn("city", F.lit(city))
        .withColumn("snapshot_date", F.lit(CITIES[city]["snapshot_date"]).cast("date"))
    )
    frames.append(df_city)

raw = frames[0].unionByName(frames[1], allowMissingColumns=True)
source_columns = [c for c in raw.columns if c not in ("city", "snapshot_date")]
print(f"{len(source_columns)} source columns")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Typed working view
# MAGIC Minimal typing used only for this analysis (empty string → null, numbers cast, `price` parsed). The pipeline's silver layer should implement the same rules (section 6).

# COMMAND ----------


def num(col):
    """Cast a source string to double; empty strings and junk become null."""
    return F.expr(f"try_cast(nullif(trim(`{col}`), '') AS DOUBLE)")


def money(col):
    return F.expr(f"try_cast(regexp_replace(nullif(trim(`{col}`), ''), '[$,]', '') AS DOUBLE)")


# Empty strings and textual null markers → null for every source column, so missingness is
# measured consistently. 'None' matters: host_verifications holds the literal string "None"
# in every row (pandas hides this by default, Spark does not).
NULL_MARKERS = ["", "None", "N/A", "null"]
listings = raw.select(
    *[F.when(F.trim(F.col(c)).isin(NULL_MARKERS), None).otherwise(F.col(c)).alias(c) for c in source_columns],
    "city",
    "snapshot_date",
)

numeric_cols = [
    "accommodates", "bedrooms", "beds", "minimum_nights", "maximum_nights",
    "availability_30", "availability_60", "availability_90", "availability_365", "availability_eoy",
    "number_of_reviews", "number_of_reviews_ltm", "number_of_reviews_l30d", "number_of_reviews_ly",
    "review_scores_rating", "review_scores_accuracy", "review_scores_cleanliness", "review_scores_checkin",
    "review_scores_communication", "review_scores_location", "review_scores_value", "reviews_per_month",
    "host_listings_count", "calculated_host_listings_count", "latitude", "longitude",
    "estimated_occupancy_l365d", "estimated_revenue_l365d",
    "price_quote_total_price", "price_quote_price_per_night",
    "hosts_time_as_host_years", "hosts_time_as_user_years",
]
typed = listings
for c in numeric_cols:
    if c in listings.columns:
        typed = typed.withColumn(c, num(c))
typed = (
    typed.withColumn("price_eur", money("price"))
    .withColumn("bathrooms_n", F.expr(
        "CASE WHEN lower(bathrooms_text) LIKE '%half-bath%' THEN 0.5 "
        "ELSE try_cast(regexp_extract(bathrooms_text, '([0-9]+(\\\\.[0-9]+)?)', 1) AS DOUBLE) END"))
    .withColumn("bath_shared", F.lower("bathrooms_text").contains("shared"))
    .withColumn("is_monthly_priced", F.col("price_quote_raw").contains('"is_monthly_priced": true'))
    .withColumn("last_review_d", F.to_date("last_review"))
    .withColumn("days_since_last_review", F.datediff(F.col("snapshot_date"), F.col("last_review_d")))
    .withColumn("price_missing", F.col("price_eur").isNull())
)
typed.createOrReplaceTempView("eda_listings")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Dataset description
# MAGIC - **Grain:** one row per listing per snapshot. Natural key `(city, snapshot_date, id)`.
# MAGIC - **Snapshot date:** 2026-09-19 for both cities (Inside Airbnb "get the data" page). `last_scraped` shows the crawl itself ran on 20–21 September.

# COMMAND ----------

display(spark.sql("""
SELECT city,
       snapshot_date,
       count(*)                                   AS listings,
       count(DISTINCT id)                         AS distinct_ids,
       sum(CASE WHEN id IS NULL THEN 1 ELSE 0 END) AS missing_ids,
       count(DISTINCT host_id)                    AS hosts,
       count(DISTINCT neighbourhood_cleansed)     AS neighbourhoods,
       min(last_scraped)                          AS first_scraped,
       max(last_scraped)                          AS last_scraped,
       sum(CASE WHEN price_missing THEN 0 ELSE 1 END) AS listings_with_price
FROM eda_listings GROUP BY city, snapshot_date ORDER BY city
"""))

# COMMAND ----------

display(spark.sql("""
SELECT city, room_type, count(*) AS listings,
       round(100 * count(*) / sum(count(*)) OVER (PARTITION BY city), 1) AS pct
FROM eda_listings GROUP BY city, room_type ORDER BY city, listings DESC
"""))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Column profile and missingness
# MAGIC ### 3.1 Missing-value rate of every source column, per city

# COMMAND ----------

null_rates = typed.groupBy("city").agg(
    *[F.avg(F.col(c).isNull().cast("int")).alias(c) for c in source_columns]
).toPandas().set_index("city").T
null_rates.columns.name = None
null_rates = null_rates.sort_values("milan", ascending=False)
null_rates["category"] = pd.cut(
    null_rates[["milan", "florence"]].max(axis=1),
    bins=[-0.001, 0, 0.05, 0.5, 0.999, 1.0],
    labels=["complete", "< 5 %", "5–50 %", "50–99.9 %", "100 % empty"],
)
display(spark.createDataFrame(null_rates.reset_index().rename(columns={"index": "column"})))

# COMMAND ----------

empty_everywhere = null_rates.index[(null_rates["milan"] == 1) & (null_rates["florence"] == 1)].tolist()
print(f"{len(empty_everywhere)} columns are 100% empty in both cities:")
print(", ".join(empty_everywhere))

# COMMAND ----------

# MAGIC %md
# MAGIC ### 3.2 Profile of the columns we intend to use
# MAGIC Source type is always string; the table shows the target type after parsing, missing rate and range.

# COMMAND ----------

used = {
    "price_eur": "double (target, parsed from price)",
    "room_type": "string (4 categories)",
    "accommodates": "int",
    "bedrooms": "int",
    "beds": "int",
    "bathrooms_n": "double (parsed from bathrooms_text)",
    "minimum_nights": "int",
    "availability_30": "int (days 0–30)",
    "availability_365": "int (days 0–365)",
    "number_of_reviews": "int",
    "number_of_reviews_ltm": "int",
    "review_scores_rating": "double (0–5)",
    "review_scores_location": "double (0–5)",
    "host_listings_count": "int",
    "latitude": "double",
    "longitude": "double",
}
rows = []
for c, t in used.items():
    stats = typed.groupBy("city").agg(
        F.avg(F.col(c).isNull().cast("int")).alias("null_rate"),
        *(
            [F.min(c).alias("min"), F.expr(f"percentile_approx({c}, 0.5)").alias("median"), F.max(c).alias("max")]
            if not t.startswith("string")
            else [F.lit(None).alias("min"), F.lit(None).alias("median"), F.lit(None).alias("max")]
        ),
    ).collect()
    for r in stats:
        rows.append((c, t, r["city"], round(r["null_rate"], 4), *(None if v is None else str(v) for v in (r["min"], r["median"], r["max"]))))
display(spark.createDataFrame(rows, "column string, target_type string, city string, null_rate double, min string, median string, max string"))

# COMMAND ----------

# MAGIC %md
# MAGIC ### 3.3 Missingness *pattern* of the target
# MAGIC Is `price` missing at random? We compare the missing-price rate across groups that describe whether a listing is actually active.

# COMMAND ----------

display(spark.sql("""
SELECT city, 'availability_365 = 0' AS segment_rule,
       CASE WHEN availability_365 = 0 THEN 'yes' ELSE 'no' END AS segment,
       count(*) AS listings, round(avg(CAST(price_missing AS INT)), 3) AS price_missing_rate
FROM eda_listings GROUP BY 1, 2, 3
UNION ALL
SELECT city, 'no review in last 12 months',
       CASE WHEN number_of_reviews_ltm = 0 THEN 'yes' ELSE 'no' END,
       count(*), round(avg(CAST(price_missing AS INT)), 3)
FROM eda_listings GROUP BY 1, 2, 3
UNION ALL
SELECT city, 'has_availability',
       coalesce(has_availability, 'null'),
       count(*), round(avg(CAST(price_missing AS INT)), 3)
FROM eda_listings GROUP BY 1, 2, 3
UNION ALL
SELECT city, 'minimum_nights >= 28',
       CASE WHEN minimum_nights >= 28 THEN 'yes' ELSE 'no' END,
       count(*), round(avg(CAST(price_missing AS INT)), 3)
FROM eda_listings GROUP BY 1, 2, 3
ORDER BY city, segment_rule, segment
"""))

# COMMAND ----------

# MAGIC %md
# MAGIC **Reading:** listings with no availability for a year almost never have a price (the scraper cannot get a quote for a blocked calendar). Missing price is therefore **MNAR** — it is tied to inactivity. Consequences:
# MAGIC - rows without price are excluded from training/evaluation (no target), **not imputed**;
# MAGIC - they are still real listings and must stay in silver and in the city-overview counts, with `exclusion_reason = 'missing_price'`;
# MAGIC - the model is only valid for *active* listings; this is stated on the dashboard.
# MAGIC
# MAGIC ### 3.4 Missingness pattern of review scores

# COMMAND ----------

display(spark.sql("""
SELECT city,
       CASE WHEN number_of_reviews = 0 THEN 'no reviews' ELSE 'has reviews' END AS reviews,
       count(*) AS listings,
       round(avg(CAST(review_scores_rating IS NULL AS INT)), 3) AS rating_null_rate,
       round(avg(CAST(review_scores_location IS NULL AS INT)), 3) AS location_score_null_rate,
       round(avg(CAST(reviews_per_month IS NULL AS INT)), 3) AS reviews_per_month_null_rate
FROM eda_listings GROUP BY 1, 2 ORDER BY 1, 2
"""))

# COMMAND ----------

# MAGIC %md
# MAGIC Review scores are null **if and only if** the listing has no reviews — a structural pattern, not data loss. Imputation rule: `has_reviews` flag + fill scores with the training median, `reviews_per_month` with 0.
# MAGIC
# MAGIC Other small gaps: `beds` (1.5–2 %), `minimum_nights`/`maximum_nights` (0.6 % Milan, 2.8 % Florence), `bathrooms_text` (< 0.03 %), `description` (0.1 %) → impute with the training median per `room_type`.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Distributions of price and availability
# MAGIC ### 4.1 Price

# COMMAND ----------

display(spark.sql("""
SELECT city, count(price_eur) AS priced_listings,
       round(min(price_eur), 2) AS min,
       round(percentile_approx(price_eur, 0.01), 1) AS p01,
       round(percentile_approx(price_eur, 0.05), 1) AS p05,
       round(percentile_approx(price_eur, 0.25), 1) AS p25,
       round(percentile_approx(price_eur, 0.50), 1) AS median,
       round(percentile_approx(price_eur, 0.75), 1) AS p75,
       round(percentile_approx(price_eur, 0.95), 1) AS p95,
       round(percentile_approx(price_eur, 0.99), 1) AS p99,
       round(max(price_eur), 0) AS max,
       round(avg(price_eur), 1) AS mean
FROM eda_listings GROUP BY city ORDER BY city
"""))

# COMMAND ----------

# Histogram of log10(price) computed in Spark; only the binned counts go to the driver.
bins = typed.where("price_eur > 0").select(
    "city", F.floor(F.log10("price_eur") * 20).alias("bin")
).groupBy("city", "bin").count().toPandas()
fig, axes = plt.subplots(1, 2, figsize=(13, 4))
for city, color in (("milan", "#2a6fdb"), ("florence", "#e07b39")):
    b = bins[bins.city == city].sort_values("bin")
    axes[0].plot(10 ** (b["bin"] / 20), b["count"], label=city, color=color)
axes[0].set_xscale("log")
axes[0].set_xlabel("price per night, EUR (log scale)")
axes[0].set_ylabel("listings")
axes[0].set_title("Price is log-normal-ish with a long right tail")
axes[0].legend()

by_room = typed.where("price_eur IS NOT NULL").groupBy("city", "room_type").agg(
    F.expr("percentile_approx(price_eur, 0.5)").alias("median_price"), F.count("*").alias("n")
).toPandas().pivot(index="room_type", columns="city", values="median_price")
by_room[["milan", "florence"]].plot.barh(ax=axes[1], color=["#2a6fdb", "#e07b39"])
axes[1].set_xlabel("median price, EUR")
axes[1].set_title("Florence is pricier than Milan in every room type")
plt.tight_layout()
plt.show()

# COMMAND ----------

# MAGIC %md
# MAGIC ### 4.2 Price vs. size (accommodates) — the baseline's grid

# COMMAND ----------

display(spark.sql("""
SELECT city, room_type, least(accommodates, 8) AS accommodates_capped,
       count(price_eur) AS n, round(percentile_approx(price_eur, 0.5), 0) AS median_price
FROM eda_listings WHERE price_eur IS NOT NULL
GROUP BY 1, 2, 3 ORDER BY 1, 2, 3
"""))

# COMMAND ----------

# MAGIC %md
# MAGIC Median price rises roughly linearly with guests for entire homes; cells with `Hotel room`/`Shared room` or `accommodates > 8` have very few listings, so the baseline needs a fallback (room-type median, then city median) for unseen or tiny cells.
# MAGIC
# MAGIC ### 4.3 Monthly-priced listings

# COMMAND ----------

display(spark.sql("""
SELECT city, is_monthly_priced,
       CASE WHEN minimum_nights >= 28 THEN 'min_nights >= 28' ELSE 'min_nights < 28' END AS stay_rule,
       count(*) AS listings, count(price_eur) AS priced,
       round(percentile_approx(price_eur, 0.5), 1) AS median_price
FROM eda_listings GROUP BY 1, 2, 3 ORDER BY 1, 2, 3
"""))

# COMMAND ----------

# MAGIC %md
# MAGIC For monthly-priced listings, Inside Airbnb requests a ~30-night quote and divides the monthly total by the nights, so `price` is a discounted long-stay rate (≈ 45 % lower). The flag lives in `price_quote_raw` (a leaking column), so the pipeline derives the **non-leaking proxy** `long_stay = minimum_nights >= 28`, which agrees with the flag for 99.7 % (Milan) and 99.5 % (Florence) of priced listings. Note also: long-stay listings *without* a monthly quote never have a price.
# MAGIC
# MAGIC ### 4.4 Availability

# COMMAND ----------

av = typed.select("city", "availability_365", "availability_30").toPandas()
fig, axes = plt.subplots(1, 2, figsize=(13, 4))
for city, color in (("milan", "#2a6fdb"), ("florence", "#e07b39")):
    s = av[av.city == city]
    axes[0].hist(s["availability_365"].dropna(), bins=37, alpha=0.55, label=city, color=color)
    axes[1].hist(s["availability_30"].dropna(), bins=31, alpha=0.55, label=city, color=color)
axes[0].set_title("availability_365: spikes at 0 (blocked) and 365 (always open)")
axes[0].set_xlabel("days available in next 365")
axes[1].set_title("availability_30: Florence is more booked in the next month")
axes[1].set_xlabel("days available in next 30")
for a in axes:
    a.legend()
plt.tight_layout()
plt.show()

display(spark.sql("""
SELECT city,
       round(avg(CAST(availability_365 = 0 AS INT)), 3)   AS share_avail365_zero,
       round(avg(CAST(availability_365 >= 360 AS INT)), 3) AS share_avail365_full,
       percentile_approx(availability_365, 0.5)            AS median_avail365,
       percentile_approx(availability_30, 0.5)             AS median_avail30
FROM eda_listings GROUP BY city ORDER BY city
"""))

# COMMAND ----------

# MAGIC %md
# MAGIC `availability_X` counts days **not booked and not blocked** — it mixes demand (booked) and host choice (blocked). Low availability does not mean "popular". For metrics we report it as *share of open days*, not as occupancy.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Outliers and how we classify them
# MAGIC We classify each priced listing into exactly one class, in this order. Thresholds are computed on the data of each city, so the same rule works for a new city.
# MAGIC
# MAGIC | class | rule | interpretation | treatment |
# MAGIC |---|---|---|---|
# MAGIC | `missing_price` | price null | inactive / blocked listing | exclude from model, keep in counts |
# MAGIC | `invalid_price` | price ≤ 0 or not parseable | data error | exclude |
# MAGIC | `extreme_high` | price > 3 × p99 of the city (≈ 3,300–3,600 €) **or** price per guest > 1,000 € | placeholder / anti-booking price, rarely real | exclude from training and from MAE, report separately |
# MAGIC | `stale_high` | price > p99 of the city and no review in the last 12 months | probably not a real market price | exclude from training, keep for scoring |
# MAGIC | `high_tail` | price > p99 of the city, recently reviewed | genuine luxury listing | keep (log-target handles it) |
# MAGIC | `low_tail` | price < 20 € | plausible shared rooms / long stays | keep |
# MAGIC | `normal` | everything else | | keep |

# COMMAND ----------

pct = typed.groupBy("city").agg(F.expr("percentile_approx(price_eur, 0.99)").alias("p99"))
classified = (
    typed.join(pct, "city")
    .withColumn("price_per_guest", F.col("price_eur") / F.greatest(F.col("accommodates"), F.lit(1)))
    .withColumn(
        "price_class",
        F.when(F.col("price") .isNull(), "missing_price")
        .when(F.col("price_eur").isNull() | (F.col("price_eur") <= 0), "invalid_price")
        .when((F.col("price_eur") > 3 * F.col("p99")) | (F.col("price_per_guest") > 1000), "extreme_high")
        .when((F.col("price_eur") > F.col("p99")) & (F.coalesce("number_of_reviews_ltm", F.lit(0)) == 0), "stale_high")
        .when(F.col("price_eur") > F.col("p99"), "high_tail")
        .when(F.col("price_eur") < 20, "low_tail")
        .otherwise("normal"),
    )
)
classified.createOrReplaceTempView("eda_classified")
display(spark.sql("""
SELECT city, price_class, count(*) AS listings,
       round(100 * count(*) / sum(count(*)) OVER (PARTITION BY city), 2) AS pct,
       round(percentile_approx(price_eur, 0.5), 0) AS median_price,
       round(avg(availability_365), 0) AS avg_avail365,
       round(avg(number_of_reviews_ltm), 1) AS avg_reviews_ltm
FROM eda_classified GROUP BY 1, 2 ORDER BY 1, listings DESC
"""))

# COMMAND ----------

# MAGIC %md
# MAGIC Examples of the most extreme prices (check by eye: low reviews, odd size/price combinations):

# COMMAND ----------

display(spark.sql("""
SELECT city, id, room_type, accommodates, bedrooms, price_eur, round(price_per_guest, 0) AS price_per_guest,
       minimum_nights, availability_365, number_of_reviews, number_of_reviews_ltm, price_class
FROM eda_classified WHERE price_class IN ('extreme_high', 'stale_high')
ORDER BY price_eur DESC LIMIT 25
"""))

# COMMAND ----------

# MAGIC %md
# MAGIC Other numeric outliers relevant to features:
# MAGIC - `minimum_nights` up to 1,000+ (long-term rentals) → cap at 365 and use the `long_stay` flag;
# MAGIC - `host_listings_count` up to 2,300 in Milan (property managers) → use `log1p`;
# MAGIC - `accommodates` 1–16 is plausible; `bedrooms` / `beds` = 0 occur for studios.

# COMMAND ----------

display(spark.sql("""
SELECT city,
       max(minimum_nights) AS max_min_nights,
       round(avg(CAST(minimum_nights > 365 AS INT)), 4) AS share_min_nights_gt_365,
       max(host_listings_count) AS max_host_listings,
       round(avg(CAST(host_listings_count >= 10 AS INT)), 3) AS share_professional_hosts,
       max(accommodates) AS max_accommodates,
       max(bedrooms) AS max_bedrooms
FROM eda_listings GROUP BY city ORDER BY city
"""))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. Cleaning and transformations the pipeline must apply
# MAGIC
# MAGIC | # | rule | reason (evidence in this notebook) |
# MAGIC |---|---|---|
# MAGIC | 1 | Read CSV with `multiLine`, `escape='"'`, all strings, FAILFAST | descriptions contain newlines and quotes; silent row loss would bias counts |
# MAGIC | 2 | Trim strings; `''`, `'None'`, `'N/A'` → null | consistent missingness (section 3); `host_verifications` is the literal string `None` in every row |
# MAGIC | 3 | Key `(city, snapshot_date, id)`; assert unique, non-null | grain check (section 2) |
# MAGIC | 4 | `price_eur = try_cast(regexp_replace(price, '[$,]', ''))` | `$` symbol but EUR values; thousand separators |
# MAGIC | 5 | `exclusion_reason` = `missing_price` / `invalid_price` / `extreme_high` / `stale_high`; never delete rows in silver | MNAR missingness and outlier classes (sections 3.3, 5) |
# MAGIC | 6 | Cast numerics with `try_cast` (not `cast`) | new snapshots may contain unexpected strings; the pipeline must not crash |
# MAGIC | 7 | Parse `bathrooms_n` and `bath_shared` from `bathrooms_text` (`"Half-bath"` → 0.5) | `bathrooms` column is 100 % empty |
# MAGIC | 8 | Booleans `t`/`f` → boolean | `has_availability`, `host_is_superhost`, etc. |
# MAGIC | 9 | Dates → date; derive `days_since_last_review` relative to `snapshot_date` | recency without leaking future info |
# MAGIC | 10 | `has_reviews` flag; review scores imputed with the **training** median; `reviews_per_month` → 0 | structural missingness (3.4) |
# MAGIC | 11 | `long_stay = minimum_nights >= 28`; cap `minimum_nights` at 365 | monthly-priced listings (4.3) and extreme values (5) |
# MAGIC | 12 | `dist_center_km` = haversine from city centre (configured per city) | neighbourhoods are not comparable across cities (8) |
# MAGIC | 13 | Do not depend on columns that are 100 % empty; select by name, tolerate missing/extra columns | 14 empty columns; schema may differ in a new city |
# MAGIC | 14 | Drop leakage columns before the feature table | section 7 |

# COMMAND ----------

# MAGIC %md
# MAGIC ## 7. Leakage review
# MAGIC A feature leaks if it is computed from the price or is only known after the price is set and observed. We **test** suspicious columns instead of guessing.

# COMMAND ----------

display(spark.sql("""
SELECT city,
       count(*) AS rows_with_both,
       round(avg(CAST(abs(price_quote_price_per_night - price_eur) < 0.01 AS INT)), 4) AS share_quote_ppn_equals_price,
       round(corr(price_quote_price_per_night, price_eur), 4) AS corr_quote_ppn,
       round(percentile_approx(try_divide(estimated_revenue_l365d, estimated_occupancy_l365d * price_eur), 0.5), 4) AS median_revenue_over_occ_x_price,
       round(percentile_approx(try_divide(estimated_revenue_l365d, estimated_occupancy_l365d * price_eur), 0.01), 4) AS p01_ratio,
       round(percentile_approx(try_divide(estimated_revenue_l365d, estimated_occupancy_l365d * price_eur), 0.99), 4) AS p99_ratio,
       round(avg(CAST(instr(price_quote_raw, CAST(price_eur AS STRING)) > 0 OR instr(price_quote_raw, format_number(price_eur, 2)) > 0 AS INT)), 3) AS share_raw_contains_price
FROM eda_listings
WHERE price_eur IS NOT NULL AND price_quote_price_per_night IS NOT NULL
GROUP BY city ORDER BY city
"""))

# COMMAND ----------

# Screen every numeric column: a near-perfect rank correlation with price is a red flag.
screen_cols = [c for c in numeric_cols if c not in ("latitude", "longitude")]
pdf = typed.where("price_eur IS NOT NULL").select("city", "price_eur", *screen_cols).toPandas()
corr_rows = []
for city in CITIES:
    s = pdf[pdf.city == city]
    for c in screen_cols:
        if s[c].notna().sum() > 100:
            corr_rows.append((city, c, round(float(s["price_eur"].corr(s[c], method="spearman")), 3)))
corr_df = pd.DataFrame(corr_rows, columns=["city", "column", "spearman_with_price"]).pivot(
    index="column", columns="city", values="spearman_with_price"
).sort_values("milan", key=lambda x: -x.abs())
display(spark.createDataFrame(corr_df.reset_index()))

# COMMAND ----------

# MAGIC %md
# MAGIC ### Leakage verdict
# MAGIC
# MAGIC | column(s) | verdict | why |
# MAGIC |---|---|---|
# MAGIC | `price_quote_price_per_night` | **leak — exclude** | equals `price` for 100 % of rows (it *is* the target) |
# MAGIC | `price_quote_total_price` | **leak — exclude** | price × number of quoted nights |
# MAGIC | `price_quote_raw` | **leak — exclude** | JSON with the price, subtotals and line items as text |
# MAGIC | `price_quote_checkin_date`, `price_quote_checkout_date` | exclude | describe how the price was obtained, not the listing; the nights length reveals monthly pricing |
# MAGIC | `estimated_revenue_l365d` | **leak — exclude** | = `estimated_occupancy_l365d` × `price` (ratio 1.000) |
# MAGIC | `estimated_occupancy_l365d` | exclude (target-side) | Inside Airbnb's model of bookings, partly driven by price and reviews; an outcome of the price, not a cause |
# MAGIC | `availability_*` | use with care | partly a consequence of price (cheap listings get booked); acceptable as a "host activity" signal, but not as a top feature without discussion |
# MAGIC | `reviews_per_month`, `number_of_reviews_*` | allowed | listing history, observed before the snapshot price |
# MAGIC | `id`, `listing_url`, `scrape_id`, `host_id`, URLs, `name`, `description` (raw), `license` | exclude | identifiers / free text: memorise listings instead of generalising (raw `id` would leak via train/test duplicates of the same host) |
# MAGIC | `calculated_host_listings_count*`, `host_listings_count` | allowed | portfolio size of the host; known independently of price |
# MAGIC | `neighbourhood_cleansed` | allowed but city-specific | does not transfer to a new city (section 8) |

# COMMAND ----------

# MAGIC %md
# MAGIC ## 8. Transfer risks to an unseen city (written before seeing city C)

# COMMAND ----------

display(spark.sql("""
WITH n AS (
  SELECT city, neighbourhood_cleansed, count(*) AS listings,
         round(percentile_approx(price_eur, 0.5), 0) AS median_price
  FROM eda_listings GROUP BY city, neighbourhood_cleansed
)
SELECT city, neighbourhood_cleansed, listings, median_price,
       round(100 * listings / sum(listings) OVER (PARTITION BY city), 1) AS pct_of_city
FROM n
QUALIFY row_number() OVER (PARTITION BY city ORDER BY listings DESC) <= 10
ORDER BY city, listings DESC
"""))

# COMMAND ----------

# MAGIC %md
# MAGIC 1. **Neighbourhood granularity differs** (87 vs 5 areas) → one-hot neighbourhood features cannot be reused; prefer distance to centre + a city-level price index.
# MAGIC 2. **Price level differs by city** (+20 % Florence vs Milan). A model with a `city` one-hot has no value for a new city → it needs a fallback (e.g. treat as "unknown city" ⇒ average level) and will be biased by the new city's level.
# MAGIC 3. **Monthly-pricing share differs** (11 % vs 5 %) — composition shifts change the MAE even with a perfect model.
# MAGIC 4. **Empty columns could be populated** (or populated ones could be empty) in another snapshot → the pipeline must select columns by name and tolerate absence.
# MAGIC 5. **Room-type mix**: hotel and shared rooms are < 1 % → baseline cells may be unseen in the new city.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 9. Proposed gold metric definitions (for the dashboard and Genie)
# MAGIC
# MAGIC | metric | definition | population |
# MAGIC |---|---|---|
# MAGIC | `listings` | count of distinct `id` | all listings in the snapshot |
# MAGIC | `priced_listings` | listings with `exclusion_reason IS NULL` | modelling population |
# MAGIC | `median_price_eur` | median of `price_eur` | priced listings, excluding `extreme_high` |
# MAGIC | `open_days_share_365` | avg(`availability_365`) / 365 | all listings; label "share of days open", **not** occupancy |
# MAGIC | `share_blocked` | share with `availability_365 = 0` | all listings |
# MAGIC | `avg_review_score` | avg(`review_scores_rating`) | listings with ≥ 1 review |
# MAGIC | `hosts` | count distinct `host_id` | all listings |
# MAGIC | `share_multi_listing_hosts` | listings whose host has `calculated_host_listings_count ≥ 2` / listings | all listings |
# MAGIC | `room_type_mix` | share of listings by `room_type` | all listings |
# MAGIC | `neighbourhood_median_price` | median price by `neighbourhood_cleansed`, only where ≥ 20 priced listings | priced listings |
# MAGIC
# MAGIC Proposed tables: `gold.city_metrics` (one row per city × snapshot), `gold.neighbourhood_metrics` (city × neighbourhood), `gold.room_type_metrics` (city × room type × accommodates bucket), plus the model's `gold.predictions`.
# MAGIC
# MAGIC The query below is the reference implementation of `city_metrics` on the raw files, so dashboard numbers can be reconciled against it.

# COMMAND ----------

display(spark.sql("""
SELECT c.city, c.snapshot_date,
       count(*)                                                      AS listings,
       sum(CASE WHEN price_class NOT IN ('missing_price','invalid_price','extreme_high','stale_high') THEN 1 ELSE 0 END) AS priced_listings,
       round(percentile_approx(CASE WHEN price_class NOT IN ('missing_price','invalid_price','extreme_high') THEN price_eur END, 0.5), 1) AS median_price_eur,
       round(avg(availability_365) / 365, 3)                         AS open_days_share_365,
       round(avg(CAST(availability_365 = 0 AS INT)), 3)              AS share_blocked,
       round(avg(review_scores_rating), 2)                           AS avg_review_score,
       count(DISTINCT host_id)                                       AS hosts,
       round(avg(CAST(calculated_host_listings_count >= 2 AS INT)), 3) AS share_multi_listing_hosts,
       round(avg(CAST(room_type = 'Entire home/apt' AS INT)), 3)     AS share_entire_home
FROM eda_classified c GROUP BY c.city, c.snapshot_date ORDER BY c.city
"""))
