"""Run with python3 -m unittest discover -s tests -v (PySpark + Java required)."""

import unittest

from pyspark.sql import SparkSession

from airbnb.silver import prepare_listings
from airbnb.gold import build_gold
from airbnb.validation import validate_layers


class SilverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spark = SparkSession.builder.master("local[1]").appName("airbnb-silver-tests").config("spark.ui.enabled", "false").getOrCreate()
        cls.spark.sparkContext.setLogLevel("ERROR")

    @classmethod
    def tearDownClass(cls):
        cls.spark.stop()

    def test_prices_quality_and_row_preservation(self):
        rows = [
            ("1", "$1,234.50", "Entire home/apt", "2", "365", "t"),
            ("2", "€85.00", "Private room", "bad", "999", "unexpected"),
            ("3", "1.234,56", "Shared room", "1", "0", "f"),
            ("4", None, "Private room", "1", None, None),
            ("5", "0", "Private room", "1", "0", "f"),
            ("6", "-5.00", "Private room", "1", "0", "f"),
            ("7", "999999.00", "A previously unseen room type", "1", "0", "f"),
        ]
        raw = self.spark.createDataFrame(rows, "id string, price string, room_type string, accommodates string, availability_365 string, host_is_superhost string")
        from pyspark.sql import functions as F
        raw = raw.withColumn("_city", F.lit("milan")).withColumn("_snapshot_date", F.lit("2026-09-19").cast("date"))
        result = prepare_listings(raw)
        actual = {row.listing_id: row.asDict() for row in result.collect()}
        self.assertEqual(len(actual), len(rows))
        self.assertEqual(str(actual[1]["price"]), "1234.50")
        self.assertEqual(actual[1]["raw_price"], "$1,234.50")
        self.assertTrue(actual[1]["host_is_superhost"])
        self.assertEqual(actual[1]["currency"], "EUR")
        self.assertTrue(actual[2]["eligible_for_training"])
        self.assertIsNone(actual[2]["accommodates"])
        self.assertIn("invalid_accommodates", actual[2]["quality_flags"])
        self.assertIn("availability_out_of_range", actual[2]["quality_flags"])
        self.assertIn("invalid_host_is_superhost", actual[2]["quality_flags"])
        for key in (3, 4, 5, 6):
            self.assertFalse(actual[key]["eligible_for_training"])
            self.assertTrue(actual[key]["exclusion_reasons"])
        self.assertIn("invalid_price_format", actual[3]["quality_flags"])
        self.assertIn("missing_price", actual[4]["quality_flags"])
        self.assertTrue(actual[7]["eligible_for_training"])
        self.assertEqual(actual[7]["room_type"], "A previously unseen room type")
        self.assertIsNone(actual[7]["bedrooms"])

    def test_required_columns_fail_clearly(self):
        with self.assertRaisesRegex(ValueError, "Bronze columns missing"):
            prepare_listings(self.spark.createDataFrame([("1",)], "id string"))

    def test_nonfinite_predictors_are_not_written_as_numbers(self):
        raw = self.spark.createDataFrame(
            [("1", "10", "Private room", "1", "NaN", "Infinity", "florence", "2026-09-19")],
            "id string, price string, room_type string, accommodates string, bedrooms string, latitude string, _city string, _snapshot_date string",
        )
        row = prepare_listings(raw).first()
        self.assertIsNone(row.bedrooms)
        self.assertIsNone(row.latitude)
        self.assertIn("invalid_bedrooms", row.quality_flags)
        self.assertIn("invalid_latitude", row.quality_flags)
        self.assertEqual(row.city, "florence")

    def test_eda_nulls_bathrooms_dates_and_location(self):
        raw = self.spark.createDataFrame(
            [("1", "$100.00", "Private room", "2", " None ", "Shared half-bath", "1000", "2026-09-09", "1", "45.4642", "9.1900", "milan", "2026-09-19")],
            "id string, price string, room_type string, accommodates string, host_verifications string, bathrooms_text string, minimum_nights string, last_review string, number_of_reviews string, latitude string, longitude string, _city string, _snapshot_date string",
        )
        row = prepare_listings(raw, {"milan": (45.4642, 9.1900)}).first()
        self.assertIsNone(row.host_verifications)
        self.assertEqual(row.raw_host_verifications, " None ")
        self.assertEqual(row.bathrooms_n, 0.5)
        self.assertTrue(row.bath_shared)
        self.assertEqual(row.minimum_nights, 365)
        self.assertEqual(row.raw_minimum_nights, "1000")
        self.assertTrue(row.long_stay)
        self.assertTrue(row.has_reviews)
        self.assertEqual(row.days_since_last_review, 10)
        self.assertAlmostEqual(row.dist_center_km, 0.0)

    def test_synthetic_city_runs_through_silver_and_gold(self):
        raw = self.spark.createDataFrame(
            [('1', '$100.00', 'Unknown room type', '2', '0', '0', 'synthetic_city', '2026-01-02')],
            'id string, price string, room_type string, accommodates string, latitude string, longitude string, _city string, _snapshot_date string',
        )
        silver = prepare_listings(raw, {'synthetic_city': (0, 0)})
        self.assertEqual(silver.first().dist_center_km, 0.0)
        gold = build_gold(silver)
        row = gold['city_metrics'].first()
        self.assertEqual(row.city, 'synthetic_city')
        self.assertEqual(row.listings, 1)
        self.assertEqual(gold['model_features'].first().room_type, 'Unknown room type')

    def test_eda_classification_gold_populations_and_feature_safety(self):
        rows = [(str(i), "100", "2", "1", "0", "5", "2", "1", "Centro") for i in range(1, 201)]
        rows += [
            ("201", "200", "2", "0", "365", "5", "2", "1", "Centro"),
            ("202", "5000", "1", "0", "365", "5", "2", "1", "Small"),
            ("203", "None", "1", "0", "0", "5", "2", "0", "Small"),
        ]
        raw = self.spark.createDataFrame(rows, "id string, price string, accommodates string, number_of_reviews_ltm string, availability_365 string, review_scores_rating string, calculated_host_listings_count string, number_of_reviews string, neighbourhood_cleansed string")
        from pyspark.sql import functions as F
        raw = (raw.withColumn("_city", F.lit("milan"))
               .withColumn("_snapshot_date", F.lit("2026-09-19").cast("date"))
               .withColumn("room_type", F.lit("Private room"))
               .withColumn("host_id", F.lit("10"))
               .withColumn("price_quote_raw", F.lit('{"price": 100}'))
               .withColumn("estimated_revenue_l365d", F.lit("10000")))
        silver = prepare_listings(raw)
        classified = {r.listing_id: r for r in silver.select("listing_id", "price_class", "eligible_for_training", "eligible_for_analysis").collect()}
        self.assertEqual(classified[201].price_class, "stale_high")
        self.assertTrue(classified[201].eligible_for_training)  # no test-label filtering
        self.assertFalse(classified[201].eligible_for_analysis)
        self.assertEqual(classified[202].price_class, "extreme_high")
        self.assertEqual(classified[203].price_class, "missing_price")
        tables = build_gold(silver)
        metrics = tables['city_metrics'].first()
        self.assertEqual(metrics.listings, 203)
        self.assertEqual(metrics.priced_listings, 200)
        self.assertEqual(metrics.median_price_eur, 100.0)
        self.assertEqual(metrics.hosts, 1)
        self.assertAlmostEqual(metrics.share_multi_listing_hosts, 1.0)
        self.assertAlmostEqual(metrics.share_blocked, 201 / 203)
        neighbourhoods = {r.neighbourhood_cleansed: r for r in tables['neighbourhood_metrics'].collect()}
        self.assertEqual(neighbourhoods['Centro'].median_price_eur, 100.0)
        self.assertIsNone(neighbourhoods['Small'].median_price_eur)
        self.assertAlmostEqual(tables['room_type_metrics'].first().room_type_mix, 1.0)
        features = tables['model_features']
        self.assertEqual(features.count(), 203)
        for column in features.columns:
            self.assertFalse(column.startswith('raw_'))
            self.assertNotIn('price_quote', column)
            self.assertNotIn(column, ('estimated_revenue_l365d', 'estimated_occupancy_l365d', 'city_price_p99', 'price_class', 'host_id'))
        manifest = self.spark.createDataFrame([(203,)], 'row_count long')
        counts = validate_layers(raw, silver, manifest, tables)
        self.assertEqual(counts['bronze_rows'], 203)
        self.assertEqual(counts['analytical_rows'], 200)
        bad_tables = dict(tables)
        bad_tables['model_features'] = features.withColumn('price_eur', F.col('price_eur') + 1)
        with self.assertRaisesRegex(ValueError, 'Model features differ'):
            validate_layers(raw, silver, manifest, bad_tables)
        with self.assertRaisesRegex(ValueError, 'manifest'):
            validate_layers(raw, silver, self.spark.createDataFrame([(202,)], 'row_count long'), tables)


if __name__ == "__main__":
    unittest.main()
