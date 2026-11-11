"""Split, baseline and MAE tests on synthetic data. No Spark required.

Run with: python -m unittest tests.test_model -v
"""

import math
import unittest

import numpy as np
import pandas as pd

from airbnb.model import (
    LEVEL_CELL,
    LEVEL_OVERALL,
    LEVEL_ROOM,
    HEADLINE_POPULATION,
    assign_split,
    fit_baseline,
    fit_upper_price_threshold,
    mae_table,
    predict_baseline,
    split_hash_unit,
    split_summary,
)


def synthetic_listings(n_per_city=6000, seed=7):
    rng = np.random.default_rng(seed)
    frames = []
    for offset, city in enumerate(("milan", "florence")):
        ids = np.arange(n_per_city, dtype="int64") + 10_000_000 * (offset + 1)
        frames.append(pd.DataFrame({
            "city": city,
            "snapshot_date": "2026-09-19",
            "listing_id": ids,
            "room_type": rng.choice(["Entire home/apt", "Private room", "Hotel room"], n_per_city),
            "accommodates": rng.integers(1, 9, n_per_city),
            "price_eur": rng.uniform(30, 400, n_per_city).round(2),
            "eligible_for_training": rng.random(n_per_city) > 0.1,
        }))
    return pd.concat(frames, ignore_index=True)


def split_rows(rows):
    """Small hand-built frame with an explicit split."""
    return pd.DataFrame(rows, columns=["city", "room_type", "accommodates", "price_eur", "evaluation_split"])


class SplitTests(unittest.TestCase):
    def setUp(self):
        self.df = synthetic_listings()

    def test_deterministic(self):
        first = assign_split(self.df)
        second = assign_split(self.df)
        pd.testing.assert_series_equal(first["evaluation_split"], second["evaluation_split"])

    def test_independent_of_row_order(self):
        base = assign_split(self.df).set_index(["city", "listing_id"])["evaluation_split"]
        shuffled = assign_split(self.df.sample(frac=1, random_state=3)).set_index(["city", "listing_id"])["evaluation_split"]
        pd.testing.assert_series_equal(base.sort_index(), shuffled.sort_index())

    def test_independent_of_other_rows_and_id_type(self):
        full = assign_split(self.df).set_index(["city", "listing_id"])["evaluation_split"]
        subset = self.df.iloc[:500].copy()
        subset["listing_id"] = subset["listing_id"].astype(str)
        part = assign_split(subset)
        part["listing_id"] = part["listing_id"].astype("int64")
        part = part.set_index(["city", "listing_id"])["evaluation_split"]
        pd.testing.assert_series_equal(full.loc[part.index], part)

    def test_approximately_20_percent_test_per_city(self):
        summary = split_summary(assign_split(self.df)).set_index("city")
        for city in ("milan", "florence"):
            self.assertGreater(summary.loc[city, "train"] + summary.loc[city, "test"], 5000)
            self.assertAlmostEqual(summary.loc[city, "test_share"], 0.20, delta=0.015)

    def test_split_does_not_read_prices(self):
        changed = self.df.copy()
        changed["price_eur"] = changed["price_eur"][::-1].to_numpy() * 10
        pd.testing.assert_series_equal(
            assign_split(self.df)["evaluation_split"], assign_split(changed)["evaluation_split"]
        )

    def test_different_salts_differ(self):
        a = assign_split(self.df, salt="airbnb-v1")["evaluation_split"]
        b = assign_split(self.df, salt="airbnb-v2")["evaluation_split"]
        self.assertGreater((a != b).sum(), 0)

    def test_same_id_in_two_cities_hashes_differently(self):
        self.assertNotEqual(split_hash_unit("milan", 1), split_hash_unit("florence", 1))
        self.assertEqual(split_hash_unit("Milan ", "1"), split_hash_unit("milan", 1.0))

    def test_ineligible_rows_kept_with_reason_and_no_split(self):
        df = self.df.copy()
        df["eligible_for_training"] = df["eligible_for_training"].astype("object")
        df.loc[0, "eligible_for_training"] = None
        out = assign_split(df)
        self.assertEqual(len(out), len(df))
        pd.testing.assert_frame_equal(out[df.columns], df)
        ineligible = df["eligible_for_training"] != True  # noqa: E712 - includes None
        self.assertTrue(out.loc[ineligible, "evaluation_split"].isna().all())
        self.assertTrue(out.loc[ineligible, "split_exclusion_reason"].notna().all())
        self.assertTrue(out.loc[~ineligible, "split_exclusion_reason"].isna().all())
        self.assertTrue(out.loc[~ineligible, "evaluation_split"].isin(["train", "test"]).all())
        self.assertEqual(out.loc[0, "split_exclusion_reason"], "eligibility_unknown")

    def test_silver_reasons_are_exposed_when_present(self):
        df = pd.DataFrame({
            "city": ["milan", "milan"], "listing_id": [1, 2], "eligible_for_training": [False, True],
            "exclusion_reasons": [["missing_or_invalid_price"], []],
        })
        out = assign_split(df)
        self.assertEqual(out.loc[0, "split_exclusion_reason"], "missing_or_invalid_price")
        self.assertIsNone(out.loc[1, "split_exclusion_reason"])

    def test_input_not_modified(self):
        before = self.df.copy()
        assign_split(self.df)
        pd.testing.assert_frame_equal(self.df, before)

    def test_duplicate_keys_rejected(self):
        df = self.df.iloc[:3].copy()
        df.loc[2, "listing_id"] = df.loc[1, "listing_id"]
        with self.assertRaisesRegex(ValueError, "share a \\(city, listing_id\\) key"):
            assign_split(df)

    def test_duplicate_key_with_different_id_type_rejected(self):
        df = pd.DataFrame({"city": ["milan", "Milan"], "listing_id": ["5", 5], "eligible_for_training": [True, True]})
        with self.assertRaisesRegex(ValueError, "share a"):
            assign_split(df)

    def test_missing_key_values_rejected(self):
        for column in ("city", "listing_id"):
            df = self.df.iloc[:3].copy()
            df[column] = df[column].astype("object")
            df.loc[1, column] = None
            with self.assertRaisesRegex(ValueError, "must be non-null"):
                assign_split(df)

    def test_missing_columns_rejected(self):
        with self.assertRaisesRegex(ValueError, "missing required columns"):
            assign_split(self.df.drop(columns=["eligible_for_training"]))

    def test_invalid_parameters_rejected(self):
        with self.assertRaises(ValueError):
            assign_split(self.df, test_share=1.0)
        with self.assertRaises(ValueError):
            assign_split(self.df, salt="")


class BaselineTests(unittest.TestCase):
    def setUp(self):
        self.df = split_rows([
            ("milan", "Entire home/apt", 2, 100.0, "train"),
            ("milan", "Entire home/apt", 2, 120.0, "train"),
            ("florence", "Entire home/apt", 2, 140.0, "train"),
            ("florence", "Entire home/apt", 4, 200.0, "train"),
            ("milan", "Private room", 1, 50.0, "train"),
            ("florence", "Private room", 1, 70.0, "train"),
            ("milan", "Entire home/apt", 2, 9999.0, "test"),
            ("florence", "Private room", 1, 1.0, "test"),
            ("milan", "Shared room", 1, 5000.0, None),
        ])

    def lookup_value(self, lookup, level, room=None, acc=None):
        rows = lookup[lookup["baseline_level"] == level]
        if room is not None:
            rows = rows[rows["room_type"] == room]
        if acc is not None:
            rows = rows[rows["accommodates"] == acc]
        self.assertEqual(len(rows), 1)
        return rows.iloc[0]

    def test_pooled_training_medians(self):
        lookup = fit_baseline(self.df)
        self.assertEqual(self.lookup_value(lookup, LEVEL_CELL, "Entire home/apt", 2)["median_price_eur"], 120.0)
        self.assertEqual(self.lookup_value(lookup, LEVEL_CELL, "Entire home/apt", 2)["n_train"], 3)
        self.assertEqual(self.lookup_value(lookup, LEVEL_ROOM, "Entire home/apt")["median_price_eur"], 130.0)
        self.assertEqual(self.lookup_value(lookup, LEVEL_ROOM, "Private room")["median_price_eur"], 60.0)
        self.assertEqual(self.lookup_value(lookup, LEVEL_OVERALL)["median_price_eur"], 110.0)
        self.assertEqual(self.lookup_value(lookup, LEVEL_OVERALL)["n_train"], 6)
        self.assertFalse((lookup["room_type"] == "Shared room").any())

    def test_test_prices_cannot_change_lookup(self):
        changed = self.df.copy()
        changed.loc[changed["evaluation_split"] != "train", "price_eur"] = [1e6, 0.5, -3.0]
        pd.testing.assert_frame_equal(fit_baseline(self.df), fit_baseline(changed))

    def test_no_training_rows_rejected(self):
        with self.assertRaisesRegex(ValueError, "no training rows"):
            fit_baseline(self.df.assign(evaluation_split="test"))

    def test_invalid_training_prices_ignored(self):
        extra = split_rows([("milan", "Private room", 1, None, "train"), ("milan", "Private room", 1, -10.0, "train")])
        lookup = fit_baseline(pd.concat([self.df, extra], ignore_index=True))
        pd.testing.assert_frame_equal(lookup, fit_baseline(self.df))

    def test_all_three_fallback_levels_and_unseen_values(self):
        lookup = fit_baseline(self.df)
        score = split_rows([
            ("milan", "Entire home/apt", 2, None, "test"),    # seen cell
            ("milan", "Entire home/apt", 7, None, "test"),    # unseen accommodates
            ("milan", "Private room", 3, None, "test"),       # unseen combination
            ("milan", "Unseen type", 2, None, "test"),        # unseen room type
            ("milan", None, 2, None, "test"),                 # missing room type
            ("milan", "  ", 2, None, "test"),                 # blank room type
            ("milan", "Entire home/apt", None, None, "test"), # missing accommodates
            ("milan", "Entire home/apt", 0, None, "test"),    # invalid accommodates
            ("milan", "Entire home/apt", 2.5, None, "test"),  # non-integer accommodates
        ])
        out = predict_baseline(score, lookup)
        self.assertEqual(out["baseline_level"].tolist(), [
            LEVEL_CELL, LEVEL_ROOM, LEVEL_ROOM, LEVEL_OVERALL, LEVEL_OVERALL, LEVEL_OVERALL,
            LEVEL_ROOM, LEVEL_ROOM, LEVEL_ROOM,
        ])
        self.assertEqual(out["baseline_prediction_eur"].tolist(), [
            120.0, 130.0, 60.0, 110.0, 110.0, 110.0, 130.0, 130.0, 130.0,
        ])
        self.assertTrue(out["baseline_prediction_eur"].notna().all())

    def test_missing_category_rows_in_training_feed_only_valid_levels(self):
        extra = split_rows([
            ("milan", None, 2, 1000.0, "train"),
            ("milan", "Private room", None, 1000.0, "train"),
        ])
        lookup = fit_baseline(pd.concat([self.df, extra], ignore_index=True))
        self.assertEqual(self.lookup_value(lookup, LEVEL_CELL, "Private room", 1)["median_price_eur"], 60.0)
        self.assertEqual(self.lookup_value(lookup, LEVEL_ROOM, "Private room")["median_price_eur"], 70.0)
        self.assertEqual(self.lookup_value(lookup, LEVEL_OVERALL)["n_train"], 8)
        self.assertEqual(lookup["room_type"].isna().sum(), 1)  # only the overall row

    def test_lookup_is_serialisable_and_round_trips(self):
        lookup = fit_baseline(self.df)
        self.assertEqual(list(lookup.columns), ["baseline_level", "room_type", "accommodates", "median_price_eur", "n_train"])
        self.assertEqual(str(lookup["accommodates"].dtype), "Int64")
        self.assertEqual(str(lookup["median_price_eur"].dtype), "float64")
        restored = pd.DataFrame(lookup.astype(object).where(lookup.notna(), None).to_dict("records"))
        out_a = predict_baseline(self.df, lookup)
        out_b = predict_baseline(self.df, restored)
        pd.testing.assert_series_equal(out_a["baseline_prediction_eur"], out_b["baseline_prediction_eur"])

    def test_precision_preserved(self):
        df = split_rows([
            ("milan", "Private room", 1, 33.33, "train"),
            ("milan", "Private room", 1, 66.67, "train"),
        ])
        lookup = fit_baseline(df)
        self.assertAlmostEqual(self.lookup_value(lookup, LEVEL_CELL, "Private room", 1)["median_price_eur"], 50.0, places=10)
        df = split_rows([("milan", "Private room", 1, 33.37, "train")])
        self.assertEqual(fit_baseline(df)["median_price_eur"].iloc[0], 33.37)

    def test_inputs_not_modified(self):
        before = self.df.copy()
        lookup = fit_baseline(self.df)
        lookup_before = lookup.copy()
        out = predict_baseline(self.df, lookup)
        pd.testing.assert_frame_equal(self.df, before)
        pd.testing.assert_frame_equal(lookup, lookup_before)
        self.assertNotIn("baseline_prediction_eur", self.df.columns)
        self.assertEqual(len(out), len(self.df))

    def test_lookup_without_overall_rejected(self):
        lookup = fit_baseline(self.df)
        with self.assertRaisesRegex(ValueError, "overall"):
            predict_baseline(self.df, lookup[lookup["baseline_level"] != LEVEL_OVERALL])


class MaeTests(unittest.TestCase):
    def setUp(self):
        # Hand-calculated: Milan errors 10, 30 -> 20; Florence errors 5, 15, 40 -> 20;
        # combined (10+30+5+15+40)/5 = 20. Model errors: Milan 0, 10 -> 5;
        # Florence 5, 5, 20 -> 10; combined 40/5 = 8.
        self.df = pd.DataFrame({
            "city": ["milan", "milan", "florence", "florence", "florence", "milan", "milan", "florence", "milan"],
            "evaluation_split": ["test", "test", "test", "test", "test", "train", "test", "test", None],
            "price_eur": [100.0, 200.0, 50.0, 150.0, 400.0, 1000.0, None, 0.0, 80.0],
            "baseline": [110.0, 170.0, 55.0, 135.0, 360.0, 0.0, 99.0, 99.0, np.nan],
            "model": [100.0, 190.0, 45.0, 155.0, 380.0, 0.0, 99.0, 99.0, np.nan],
        })

    def result(self, table, group, prediction, population=HEADLINE_POPULATION):
        row = table[(table["city_group"] == group) & (table["prediction"] == prediction)
                    & (table["evaluation_population"] == population)]
        self.assertEqual(len(row), 1)
        return row.iloc[0]

    def test_hand_calculated_mae(self):
        table = mae_table(self.df, ["baseline", "model"])
        expected = {
            ("milan", "baseline"): (2, 20.0), ("florence", "baseline"): (3, 20.0), ("milan+florence", "baseline"): (5, 20.0),
            ("milan", "model"): (2, 5.0), ("florence", "model"): (3, 10.0), ("milan+florence", "model"): (5, 8.0),
        }
        for (group, prediction), (n, mae) in expected.items():
            row = self.result(table, group, prediction)
            self.assertEqual(row["n"], n)
            self.assertAlmostEqual(row["mae_eur"], mae)
        self.assertEqual(set(table["evaluation_population"]), {HEADLINE_POPULATION})

    def test_identical_rows_for_all_predictions(self):
        table = mae_table(self.df, ["baseline", "model"])
        counts = table.pivot(index="city_group", columns="prediction", values="n")
        self.assertTrue((counts["baseline"] == counts["model"]).all())

    def test_invalid_prices_excluded_and_counted(self):
        table = mae_table(self.df, "baseline")
        self.assertEqual(self.result(table, "milan", "baseline")["n_excluded_invalid_actual"], 1)
        self.assertEqual(self.result(table, "florence", "baseline")["n_excluded_invalid_actual"], 1)
        self.assertEqual(self.result(table, "milan+florence", "baseline")["n_excluded_invalid_actual"], 2)

    def test_training_rows_never_scored(self):
        changed = self.df.copy()
        changed.loc[changed["evaluation_split"] == "train", "baseline"] = 1e9
        pd.testing.assert_frame_equal(mae_table(self.df, "baseline"), mae_table(changed, "baseline"))

    def test_missing_prediction_on_headline_row_raises(self):
        df = self.df.copy()
        df.loc[0, "model"] = np.nan
        with self.assertRaisesRegex(ValueError, "no valid 'model' prediction"):
            mae_table(df, ["baseline", "model"])

    def test_threshold_is_supplementary_only(self):
        headline = mae_table(self.df, ["baseline", "model"])
        with_threshold = mae_table(self.df, ["baseline", "model"], upper_price_threshold=300.0,
                                   threshold_source="test fixture")
        pd.testing.assert_frame_equal(
            with_threshold[with_threshold["evaluation_population"] == HEADLINE_POPULATION].reset_index(drop=True),
            headline,
        )
        supplementary = with_threshold[with_threshold["evaluation_population"] != HEADLINE_POPULATION]
        florence = supplementary[(supplementary["city_group"] == "florence") & (supplementary["prediction"] == "baseline")].iloc[0]
        self.assertEqual(florence["n"], 2)
        self.assertAlmostEqual(florence["mae_eur"], 10.0)
        self.assertIn("supplementary", florence["population_description"])

    def test_threshold_requires_source(self):
        with self.assertRaisesRegex(ValueError, "threshold_source"):
            mae_table(self.df, "baseline", upper_price_threshold=300.0)

    def test_threshold_fitted_on_training_rows_only(self):
        df = pd.DataFrame({
            "evaluation_split": ["train"] * 101 + ["test"] * 3,
            "price_eur": list(range(1, 102)) + [1e6, 1e7, 1e8],
        })
        self.assertAlmostEqual(fit_upper_price_threshold(df, quantile=0.99), 100.0)
        changed = df.copy()
        changed.loc[changed["evaluation_split"] == "test", "price_eur"] = 1.0
        self.assertEqual(fit_upper_price_threshold(df), fit_upper_price_threshold(changed))

    def test_empty_city_reports_zero_rows(self):
        table = mae_table(self.df[self.df["city"] == "milan"], "baseline")
        row = self.result(table, "florence", "baseline")
        self.assertEqual(row["n"], 0)
        self.assertTrue(math.isnan(row["mae_eur"]))


class EndToEndTests(unittest.TestCase):
    def test_split_then_baseline_then_mae(self):
        df = synthetic_listings(n_per_city=1000)
        split = assign_split(df)
        lookup = fit_baseline(split)
        self.assertEqual(int(lookup.loc[lookup["baseline_level"] == LEVEL_OVERALL, "n_train"].iloc[0]),
                         int((split["evaluation_split"] == "train").sum()))
        scored = predict_baseline(split, lookup)
        self.assertTrue(scored["baseline_prediction_eur"].notna().all())
        table = mae_table(scored, "baseline_prediction_eur")
        combined = table[table["city_group"] == "milan+florence"].iloc[0]
        self.assertEqual(combined["n"], int((split["evaluation_split"] == "test").sum()))
        self.assertTrue(math.isfinite(combined["mae_eur"]))


if __name__ == "__main__":
    unittest.main()
