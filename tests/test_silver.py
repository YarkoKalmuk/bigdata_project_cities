"""Run with python3 -m unittest discover -s tests -v (PySpark + Java required)."""

import unittest

from pyspark.sql import SparkSession

from airbnb.silver import prepare_listings


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


if __name__ == "__main__":
    unittest.main()
