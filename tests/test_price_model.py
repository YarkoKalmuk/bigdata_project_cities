"""Price-model tests on synthetic data. Needs scikit-learn; no Spark.

Run with: python -m unittest tests.test_price_model -v
"""

import io
import pickle
import unittest

import numpy as np
import pandas as pd

try:
    import sklearn  # noqa: F401
except ImportError:  # pragma: no cover
    raise unittest.SkipTest("scikit-learn is not installed")

from airbnb import price_model as pm
from airbnb.model import fit_baseline, predict_baseline


def synthetic_features(n_per_city=1500, seed=11):
    rng = np.random.default_rng(seed)
    frames = []
    for offset, city in enumerate(("milan", "florence")):
        n = n_per_city
        room = rng.choice(["Entire home/apt", "Private room", "Hotel room", "Shared room"], n, p=[0.7, 0.25, 0.04, 0.01])
        prop = rng.choice(["Entire rental unit", "Private room in rental unit", "Entire loft", f"Rare {city} type"],
                          n, p=[0.6, 0.3, 0.08, 0.02])
        acc = rng.integers(1, 9, n)
        dist = rng.gamma(2.0, 1.5, n)
        has_reviews = rng.random(n) > 0.2
        rating = np.where(has_reviews, rng.uniform(3.5, 5.0, n), np.nan)
        log_price = (3.6 + 0.18 * acc - 0.12 * np.log1p(dist) + 0.4 * (room == "Entire home/apt")
                     + 0.1 * np.nan_to_num(rating - 4.5) + rng.normal(0, 0.25, n))
        frame = pd.DataFrame({
            "city": city,
            "listing_id": np.arange(n, dtype="int64") + 1_000_000 * (offset + 1),
            "price_eur": np.expm1(log_price).round(2),
            "room_type": room,
            "property_type": prop,
            "accommodates": acc,
            "bedrooms": np.where(rng.random(n) < 0.05, np.nan, np.ceil(acc / 2)),
            "beds": np.where(rng.random(n) < 0.02, np.nan, acc.astype(float)),
            "bathrooms_n": rng.choice([1.0, 1.5, 2.0], n),
            "bath_shared": pd.Series(rng.random(n) < 0.2, dtype=object),
            "minimum_nights": rng.choice([1, 2, 3, 30], n),
            "long_stay": None,
            "dist_center_km": dist,
            "has_reviews": pd.Series(has_reviews, dtype=object),
            "review_scores_rating": rating,
            "review_scores_cleanliness": rating,
            "review_scores_location": rating,
            "log_host_listings_count": np.log1p(rng.integers(1, 30, n)),
            "host_is_superhost": pd.Series(np.where(rng.random(n) < 0.1, None, rng.random(n) < 0.3), dtype=object),
            "evaluation_split": "train",
        })
        frame["long_stay"] = (frame["minimum_nights"] >= 28).astype(object)
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


class AllowlistTests(unittest.TestCase):
    def test_no_forbidden_or_excluded_feature(self):
        for name in ("instant_bookable", "review_scores_value", "price_class", "eligible_for_analysis",
                     "city_price_p99", "city", "latitude", "longitude", "neighbourhood_cleansed", "price_eur"):
            self.assertNotIn(name, pm.FEATURES)

    def test_candidates_are_small_and_cover_both_families(self):
        families = {c["family"] for c in pm.CANDIDATES}
        self.assertEqual(families, {"ridge_log", "hgb_log"})
        self.assertLessEqual(len(pm.CANDIDATES), 10)
        self.assertEqual(len({c["name"] for c in pm.CANDIDATES}), len(pm.CANDIDATES))


class GrouperTests(unittest.TestCase):
    def test_rare_missing_and_unseen_levels(self):
        fit = pd.DataFrame({"p": ["a"] * 60 + ["b"] * 10 + [None] * 5, "flag": [True] * 50 + [False] * 25})
        grouper = pm.CategoryGrouper(min_count=50).fit(fit)
        self.assertEqual(grouper.kept_levels_["p"], ["a"])
        out = grouper.transform(pd.DataFrame({"p": ["a", "b", "zzz", None, "  "], "flag": [True, False, None, True, True]}))
        self.assertEqual(out["p"].tolist(), ["a", pm.OTHER, pm.OTHER, pm.MISSING, pm.MISSING])
        self.assertEqual(out["flag"].tolist(), ["true", pm.OTHER, pm.MISSING, "true", "true"])

    def test_numeric_prep_caps_at_fit_quantile_and_logs(self):
        fit = pd.DataFrame({"x": np.arange(1, 101, dtype=float), "d": np.arange(100, dtype=float)})
        prep = pm.NumericPrep(log1p=("d",), clip_quantile=0.99).fit(fit)
        out = prep.transform(pd.DataFrame({"x": [1e6, "bad"], "d": [0.0, np.inf]}))
        self.assertAlmostEqual(out["x"].iloc[0], np.quantile(np.arange(1, 101), 0.99))
        self.assertTrue(np.isnan(out["x"].iloc[1]))
        self.assertEqual(out["d"].iloc[0], 0.0)
        self.assertTrue(np.isnan(out["d"].iloc[1]))


class PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = pm.assign_validation_fold(synthetic_features())
        cls.fit_rows = cls.data[cls.data[pm.FOLD_COL] == "subtrain"]
        cls.eval_rows = cls.data[cls.data[pm.FOLD_COL] == "validation"]

    def test_both_families_beat_the_baseline(self):
        labelled = self.data.assign(_fold=np.where(self.data[pm.FOLD_COL] == "subtrain", "train", "validation"))
        lookup = fit_baseline(labelled, split_col="_fold")
        base = predict_baseline(self.eval_rows, lookup)["baseline_prediction_eur"].to_numpy()
        base_mae = pm.mae_by_group(self.eval_rows, base)
        for family, params in (("ridge_log", {"alpha": 1.0}), ("hgb_log", pm.CANDIDATES[4]["params"])):
            model, _ = pm.fit_model(family, params, self.fit_rows)
            pred, _ = pm.predict_eur(model, self.eval_rows)
            mae = pm.mae_by_group(self.eval_rows, pred)
            for group in base_mae:
                self.assertLess(mae[group], base_mae[group], (family, group))

    def test_fitted_state_comes_from_fit_rows_only(self):
        model, _ = pm.fit_model("ridge_log", {"alpha": 1.0}, self.fit_rows)
        before = pm.predict_eur(model, self.eval_rows)[0]
        # Scoring extra rows with extreme or unseen values must not change other rows' predictions.
        odd = self.eval_rows.head(3).assign(property_type="Castle", room_type="Igloo", accommodates=500,
                                            dist_center_km=np.nan, host_is_superhost=None)
        after = pm.predict_eur(model, pd.concat([self.eval_rows, odd]))[0]
        np.testing.assert_allclose(after[: len(before)], before)
        self.assertTrue(np.isfinite(after).all())
        transformers = model.regressor_.named_steps["prep"].named_transformers_
        counts = transformers["prop"].named_steps["group"].level_counts_["property_type"]
        self.assertEqual(sum(counts.values()), len(self.fit_rows))
        # Small but meaningful room types are not merged into OTHER.
        self.assertIn("Shared room", transformers["cat"].named_steps["group"].kept_levels_["room_type"])
        self.assertNotIn("Rare milan type", transformers["prop"].named_steps["group"].kept_levels_["property_type"])

    def test_all_missing_optional_columns_do_not_fail(self):
        model, _ = pm.fit_model("hgb_log", pm.CANDIDATES[4]["params"], self.fit_rows)
        blank = self.eval_rows.head(5).copy()
        for c in pm.FEATURES:
            if c not in ("room_type", "accommodates"):
                blank[c] = None
        pred, _ = pm.predict_eur(model, blank)
        self.assertTrue(np.isfinite(pred).all() and (pred > 0).all())

    def test_model_round_trips_through_pickle(self):
        model, _ = pm.fit_model("ridge_log", {"alpha": 10.0}, self.fit_rows)
        clone = pickle.load(io.BytesIO(pickle.dumps(model)))
        np.testing.assert_allclose(pm.predict_eur(clone, self.eval_rows)[0], pm.predict_eur(model, self.eval_rows)[0])

    def test_reports(self):
        model, _ = pm.fit_model("ridge_log", {"alpha": 1.0}, self.fit_rows)
        coefs = pm.ridge_coefficients(model)
        self.assertIn("price_effect_pct", coefs.columns)
        self.assertEqual(pm.model_complexity(model, "ridge_log")["coefficients"], len(coefs) + 1)
        pred, _ = pm.predict_eur(model, self.eval_rows)
        tables = pm.failure_mode_tables(self.eval_rows, {"model": pred}, pm.price_band_edges(self.fit_rows))
        self.assertEqual(tables["by_room_type"]["n"].sum(), len(self.eval_rows))
        share = pm.property_other_share(model, self.eval_rows)
        self.assertGreater(share["milan"], 0)  # the rare city-specific type is grouped


class FoldTests(unittest.TestCase):
    def test_deterministic_share_and_guards(self):
        data = synthetic_features(n_per_city=4000)
        a = pm.assign_validation_fold(data)
        b = pm.assign_validation_fold(data.sample(frac=1, random_state=3)).loc[a.index]
        self.assertTrue((a[pm.FOLD_COL] == b[pm.FOLD_COL]).all())
        share = (a[pm.FOLD_COL] == "validation").mean()
        self.assertAlmostEqual(share, pm.VALIDATION_SHARE, delta=0.02)
        with self.assertRaises(ValueError):
            pm.assign_validation_fold(data.assign(evaluation_split="test"))
        with self.assertRaises(ValueError):
            pm.assign_validation_fold(data, salt="airbnb-v1")


class SelectionRuleTests(unittest.TestCase):
    base = {"milan": 100.0, "florence": 100.0, "milan+florence": 100.0}

    def mae(self, ridge, hgb):
        out = {c["name"]: {g: 999.0 for g in self.base} for c in pm.CANDIDATES}
        out["ridge_alpha_1"] = dict(zip(self.base, ridge))
        out["hgb_leaves_15_iter_200"] = dict(zip(self.base, hgb))
        return out

    def test_simplest_family_wins_without_a_clear_gain(self):
        name, info = pm.select_candidate(self.mae((80, 85, 82), (79, 83, 80)), self.base)
        self.assertEqual(name, "ridge_alpha_1")
        self.assertEqual(info["qualifying_families"], ["ridge_log", "hgb_log"])

    def test_complex_family_needs_gain_in_every_city(self):
        self.assertEqual(pm.select_candidate(self.mae((80, 85, 82), (70, 75, 72)), self.base)[0], "hgb_leaves_15_iter_200")
        self.assertEqual(pm.select_candidate(self.mae((80, 85, 82), (60, 84, 70)), self.base)[0], "ridge_alpha_1")

    def test_family_must_beat_baseline_in_each_city(self):
        name, _ = pm.select_candidate(self.mae((80, 97, 85), (75, 80, 77)), self.base)
        self.assertEqual(name, "hgb_leaves_15_iter_200")
        name, info = pm.select_candidate(self.mae((80, 97, 85), (75, 99, 85)), self.base)
        self.assertIsNone(name)

    def test_spec_hash_is_stable(self):
        self.assertEqual(pm.sha256_text(pm.canonical_json(pm.model_spec())),
                         pm.sha256_text(pm.canonical_json(pm.model_spec())))


if __name__ == "__main__":
    unittest.main()
