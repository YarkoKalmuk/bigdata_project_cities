"""Scoring tests (MODEL-06 / MODEL-07) on synthetic data. Needs scikit-learn and joblib; no Spark.

Run with: python -m unittest tests.test_scoring -v
"""

import copy
import hashlib
import io
import pickle
import unittest
from datetime import date, datetime, timezone
from unittest import mock

import numpy as np
import pandas as pd

try:
    import joblib
    import sklearn
except ImportError:  # pragma: no cover
    raise unittest.SkipTest("scikit-learn/joblib is not installed")

from airbnb import price_model as pm
from airbnb import scoring as sc
from airbnb.model import assign_split, fit_baseline
from tests.test_price_model import synthetic_features

SNAPSHOT = "2026-01-01"
FAST_PARAMS = {"l2_regularization": 1.0, "learning_rate": 0.1, "max_iter": 30, "max_leaf_nodes": 15, "min_samples_leaf": 20}
RUN_AT = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)


def make_features(n_per_city=600, seed=5):
    data = synthetic_features(n_per_city=n_per_city, seed=seed).drop(columns=["evaluation_split"])
    data["snapshot_date"] = date.fromisoformat(SNAPSHOT)
    rng = np.random.default_rng(seed)
    unpriced = rng.random(len(data)) < 0.15
    data.loc[unpriced, "price_eur"] = np.nan
    data["eligible_for_training"] = ~unpriced
    return data


class Fixture:
    """A small fitted artifact, its frozen record, split and baseline lookup."""

    def __init__(self):
        self.features = make_features()
        split = assign_split(self.features[["city", "snapshot_date", "listing_id", "eligible_for_training"]])
        self.split = split[["city", "snapshot_date", "listing_id", "evaluation_split"]]
        labelled = self.features.merge(self.split, on=["city", "snapshot_date", "listing_id"])
        self.lookup = fit_baseline(labelled)
        train = labelled[labelled["evaluation_split"] == "train"]
        self.model, _ = pm.fit_model("hgb_log", FAST_PARAMS, train)
        self.artifact = io.BytesIO()
        joblib.dump(self.model, self.artifact)
        self.artifact = self.artifact.getvalue()
        frozen = copy.deepcopy(sc.FROZEN_MODELS["price-v1"])
        frozen.update(
            model_version="test-v1", artifact_sha256=hashlib.sha256(self.artifact).hexdigest(),
            selected_params=dict(FAST_PARAMS), sklearn_version=sklearn.__version__,
            training_snapshots={"milan": SNAPSHOT, "florence": SNAPSHOT},
            baseline_lookup_rows=len(self.lookup), baseline_lookup_fingerprint=sc.lookup_fingerprint(self.lookup),
            split_fingerprint=sc.split_fingerprint(self.split),
        )
        self.frozen = frozen

    def score(self, features=None, split="default", model=None, run_id="run-1", at=RUN_AT):
        return sc.score_listings(
            self.features if features is None else features, self.model if model is None else model, self.frozen,
            self.lookup, self.split if isinstance(split, str) else split, scoring_run_id=run_id, scored_at=at,
            source_feature_table_version=7,
        )


FIX = None


def setUpModule():
    global FIX
    FIX = Fixture()


class FrozenRegistryTests(unittest.TestCase):
    def test_price_v1_spec_matches_current_code(self):
        frozen = sc.frozen_model("price-v1")
        self.assertEqual(frozen["spec_sha256"], pm.sha256_text(pm.canonical_json(pm.model_spec())))
        self.assertEqual(frozen["features"], list(pm.FEATURES))
        locked = next(c for c in pm.CANDIDATES if c["name"] == frozen["selected_candidate"])
        self.assertEqual(locked["params"], frozen["selected_params"])
        self.assertEqual(locked["family"], frozen["selected_family"])

    def test_unknown_model_version_is_refused(self):
        with self.assertRaises(sc.FrozenModelError):
            sc.frozen_model("price-v2")

    def test_official_numbers_are_internally_consistent(self):
        frozen = sc.frozen_model("price-v1")
        n = frozen["official_test_n"]
        self.assertEqual(n["milan"] + n["florence"], n["milan+florence"])
        for city in ("milan", "florence"):
            counts = frozen["split_counts"][city]
            self.assertEqual(counts["test"], n[city])


class ArtifactTests(unittest.TestCase):
    def test_load_reproduces_predictions(self):
        loaded = sc.load_artifact(FIX.artifact, FIX.frozen)
        np.testing.assert_array_equal(loaded.predict(pm.model_inputs(FIX.features)), FIX.model.predict(pm.model_inputs(FIX.features)))
        a = FIX.score(model=loaded)
        b = FIX.score()
        pd.testing.assert_frame_equal(a, b)

    def test_hash_mismatch_is_refused(self):
        with self.assertRaises(sc.FrozenModelError):
            sc.load_artifact(FIX.artifact + b"x", FIX.frozen)

    def test_artifact_record_mismatch_is_refused(self):
        record = {k: FIX.frozen[k] for k in ("artifact_sha256", "spec_sha256", "selection_record_sha256", "selected_candidate",
                                             "selected_family", "sklearn_version", "mlflow_run_id")}
        sc.check_artifact_record(record, FIX.frozen)
        with self.assertRaises(sc.FrozenModelError):
            sc.check_artifact_record({**record, "spec_sha256": "0" * 64}, FIX.frozen)


class ContractTests(unittest.TestCase):
    def test_matching_contract_passes(self):
        sc.check_model_contract(FIX.model, FIX.frozen, sklearn.__version__)

    def test_spec_mismatch_is_refused(self):
        with self.assertRaises(sc.FrozenModelError):
            sc.check_model_contract(FIX.model, {**FIX.frozen, "spec_sha256": "f" * 64})

    def test_feature_list_mismatch_is_refused(self):
        with self.assertRaises(sc.FrozenModelError):
            sc.check_model_contract(FIX.model, {**FIX.frozen, "features": list(pm.FEATURES)[:-1]})

    def test_hyperparameter_and_version_mismatch_is_refused(self):
        with self.assertRaises(sc.FrozenModelError):
            sc.check_model_contract(FIX.model, {**FIX.frozen, "selected_params": {**FAST_PARAMS, "max_iter": 31}})
        with self.assertRaises(sc.FrozenModelError):
            sc.check_model_contract(FIX.model, FIX.frozen, sklearn_version="0.0.1")

    def test_artifact_fitted_on_other_columns_is_refused(self):
        other = pm.build_model("hgb_log", FAST_PARAMS)
        train = FIX.features[FIX.features["price_eur"].notna()]
        other.fit(train[list(pm.FEATURES)].assign(extra=1.0), train["price_eur"].to_numpy())
        with self.assertRaises(sc.FrozenModelError):
            sc.check_model_contract(other, FIX.frozen)

    def test_missing_feature_column_is_refused(self):
        with self.assertRaises(sc.FrozenModelError):
            FIX.score(features=FIX.features.drop(columns=["dist_center_km"]))

    def test_reference_data_must_be_frozen(self):
        sc.check_reference_data(FIX.frozen, FIX.lookup, FIX.split)
        changed = FIX.lookup.copy()
        changed.loc[0, "median_price_eur"] += 0.01
        with self.assertRaises(sc.FrozenModelError):
            sc.check_reference_data(FIX.frozen, changed)
        moved = FIX.split.copy()
        moved.loc[moved.index[0], "evaluation_split"] = "test" if moved["evaluation_split"].iloc[0] == "train" else "train"
        with self.assertRaises(sc.FrozenModelError):
            sc.check_reference_data(FIX.frozen, FIX.lookup, moved)

    def test_fingerprint_text_format_matches_sql(self):
        split = pd.DataFrame({"city": ["milan", "florence"], "snapshot_date": [date(2026, 9, 19)] * 2,
                              "listing_id": [10, 2], "evaluation_split": ["test", None]})
        text = "florence|2026-09-19|2|\nmilan|2026-09-19|10|test"
        self.assertEqual(sc.split_fingerprint(split), hashlib.sha256(text.encode()).hexdigest())
        lookup = pd.DataFrame({"baseline_level": ["overall", "room_type"], "room_type": [None, "Private room"],
                               "accommodates": pd.array([None, None], dtype="Int64"),
                               "median_price_eur": [175.0, 148.79500000000002], "n_train": [10, 4]})
        text = "overall|||175000000|10\nroom_type|Private room||148795000|4"
        self.assertEqual(sc.lookup_fingerprint(lookup), hashlib.sha256(text.encode()).hexdigest())


class ScoringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = FIX.score()

    def test_schema_and_one_row_per_listing(self):
        self.assertEqual(list(self.out.columns), list(sc.PREDICTION_COLUMNS))
        self.assertEqual(len(self.out), len(FIX.features))
        self.assertFalse(self.out.duplicated(list(sc.TABLE_KEYS)).any())
        rec = sc.reconcile(self.out, FIX.features)
        self.assertEqual((rec["missing_from_predictions"], rec["extra_in_predictions"], rec["duplicate_keys"], rec["baseline_null"]),
                         (0, 0, 0, 0))

    def test_unpriced_rows_are_kept_with_null_errors(self):
        unpriced = self.out[self.out["actual_price_eur"].isna()]
        self.assertEqual(len(unpriced), int(FIX.features["price_eur"].isna().sum()))
        self.assertTrue((unpriced["evaluation_split"] == sc.SPLIT_EXCLUDED).all())
        self.assertTrue((unpriced["prediction_status"] == sc.STATUS_NO_ACTUAL).all())
        self.assertTrue((unpriced["evaluation_exclusion_reason"] == sc.EVAL_NO_ACTUAL).all())
        self.assertTrue(unpriced["model_prediction_eur"].notna().all() and unpriced["baseline_prediction_eur"].notna().all())
        for col in ("absolute_error_eur", "signed_residual_eur", "baseline_absolute_error_eur", "baseline_signed_residual_eur"):
            self.assertTrue(unpriced[col].isna().all(), col)

    def test_split_labels_follow_the_persisted_split(self):
        merged = self.out.merge(FIX.split, on=list(sc.KEYS), suffixes=("", "_persisted"))
        persisted = merged["evaluation_split_persisted"].fillna(sc.SPLIT_EXCLUDED)
        self.assertTrue((merged["evaluation_split"] == persisted).all())
        priced = self.out[self.out["evaluation_split"].isin(["train", "test"])]
        self.assertTrue((priced["prediction_status"] == sc.STATUS_WITH_ACTUAL).all())
        self.assertTrue(priced["evaluation_exclusion_reason"].isna().all())

    def test_residual_direction(self):
        rows = self.out[self.out["prediction_status"] == sc.STATUS_WITH_ACTUAL]
        np.testing.assert_allclose(rows["signed_residual_eur"], rows["model_prediction_eur"] - rows["actual_price_eur"])
        np.testing.assert_allclose(rows["absolute_error_eur"], rows["signed_residual_eur"].abs())
        np.testing.assert_allclose(rows["baseline_signed_residual_eur"], rows["baseline_prediction_eur"] - rows["actual_price_eur"])
        under = rows["model_prediction_eur"] < rows["actual_price_eur"]
        self.assertTrue(under.any() and (~under).any())
        self.assertTrue((rows.loc[under, "signed_residual_eur"] < 0).all())

    def test_baseline_fallback_levels_are_recorded(self):
        probe = FIX.features.head(3).copy()
        probe["listing_id"] = [9_000_001, 9_000_002, 9_000_003]
        probe["city"] = "testville"
        probe["room_type"] = ["Entire home/apt", "Entire home/apt", "Igloo"]
        probe["accommodates"] = [2, 99, 2]
        out = FIX.score(features=probe, split=None)
        self.assertEqual(out["baseline_fallback_level"].tolist(), ["room_type_x_accommodates", "room_type", "overall"])
        overall = FIX.lookup.loc[FIX.lookup["baseline_level"] == "overall", "median_price_eur"].iloc[0]
        self.assertEqual(out["baseline_prediction_eur"].iloc[2], overall)
        self.assertTrue(self.out["baseline_fallback_level"].notna().all())

    def test_unknown_categories_in_an_unseen_city(self):
        new = make_features(n_per_city=50, seed=99)
        new = new[new["city"] == "milan"].assign(city="testville")
        new["property_type"] = "Treehouse"
        new.loc[new.index[:10], "room_type"] = "Igloo"
        new.loc[new.index[10:20], "host_is_superhost"] = "maybe"
        new.loc[new.index[20:25], ["dist_center_km", "bedrooms", "review_scores_rating"]] = np.nan
        out = FIX.score(features=new, split=None)
        self.assertEqual(len(out), len(new))
        self.assertTrue((out["evaluation_split"] == sc.SPLIT_UNSEEN).all())
        self.assertTrue(out["model_prediction_eur"].notna().all() and np.isfinite(out["model_prediction_eur"]).all())
        priced = out["actual_price_eur"].notna()
        self.assertTrue((out.loc[priced, "prediction_status"] == sc.STATUS_WITH_ACTUAL).all())
        self.assertTrue((out.loc[~priced, "prediction_status"] == sc.STATUS_NO_ACTUAL).all())

    def test_unscorable_rows_are_kept_with_a_reason(self):
        class Broken:
            def predict(self, X):
                values = FIX.model.predict(X)
                values[0], values[1] = np.nan, -5.0
                return values

        out = FIX.score(model=Broken())
        self.assertEqual(len(out), len(FIX.features))
        self.assertEqual(out["scoring_exclusion_reason"].iloc[0], sc.SCORE_NON_FINITE)
        self.assertEqual(out["scoring_exclusion_reason"].iloc[1], sc.SCORE_NON_POSITIVE)
        self.assertTrue(out["model_prediction_eur"].iloc[:2].isna().all())
        self.assertTrue((out["prediction_status"].iloc[:2] == sc.STATUS_NOT_SCORED).all())
        self.assertTrue(out["absolute_error_eur"].iloc[:2].isna().all())
        self.assertTrue(out["baseline_prediction_eur"].iloc[:2].notna().all())
        self.assertTrue(out["scoring_exclusion_reason"].iloc[2:].isna().all())

    def test_duplicate_input_keys_are_refused(self):
        with self.assertRaises(ValueError):
            FIX.score(features=pd.concat([FIX.features, FIX.features.head(1)]))

    def test_split_guards(self):
        with self.assertRaises(sc.FrozenModelError):
            FIX.score(split=None)  # training city without the persisted split
        with self.assertRaises(sc.FrozenModelError):
            FIX.score(split=FIX.split.iloc[1:])  # a listing lost its split row
        with self.assertRaises(sc.FrozenModelError):
            FIX.score(features=FIX.features.assign(snapshot_date=date(2026, 2, 1)), split=None)  # other snapshot

    def test_official_metrics_check(self):
        metrics = sc.official_test_metrics(self.out, FIX.frozen)
        frozen = {**FIX.frozen, "official_test_n": metrics["n"],
                  "official_test_mae": {"model": metrics["model"], "baseline": metrics["baseline"]}}
        self.assertEqual(sc.check_official_metrics(metrics, frozen), 0.0)
        test = self.out[self.out["evaluation_split"] == "test"]
        self.assertAlmostEqual(metrics["model"]["milan"], test.loc[test["city"] == "milan", "absolute_error_eur"].mean())
        with self.assertRaises(sc.FrozenModelError):
            sc.check_official_metrics(metrics, {**frozen, "official_test_n": {**metrics["n"], "milan": 1}})
        shifted = {"model": {k: v + 0.01 for k, v in metrics["model"].items()}, "baseline": metrics["baseline"]}
        with self.assertRaises(sc.FrozenModelError):
            sc.check_official_metrics(metrics, {**frozen, "official_test_mae": shifted})


class NoRetrainingTests(unittest.TestCase):
    def test_scoring_never_fits(self):
        before = pickle.dumps(FIX.model)
        with mock.patch.object(pm, "fit_model", side_effect=AssertionError("fit_model called")), \
                mock.patch("sklearn.compose.TransformedTargetRegressor.fit", side_effect=AssertionError("fit called")), \
                mock.patch("sklearn.pipeline.Pipeline.fit", side_effect=AssertionError("fit called")):
            together = FIX.score()
            milan = FIX.score(features=FIX.features[FIX.features["city"] == "milan"],
                              split=FIX.split[FIX.split["city"] == "milan"])
        self.assertEqual(pickle.dumps(FIX.model), before)
        cols = ["listing_id", "model_prediction_eur", "baseline_prediction_eur", "evaluation_split"]
        pd.testing.assert_frame_equal(
            together[together["city"] == "milan"][cols].reset_index(drop=True), milan[cols].reset_index(drop=True))


class WriteDecisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.new = FIX.score()

    def test_first_write_appends(self):
        self.assertEqual(sc.write_decision(None, self.new), "append")
        self.assertEqual(sc.write_decision(self.new.iloc[0:0], self.new), "append")

    def test_identical_rerun_is_a_noop(self):
        rerun = FIX.score(run_id="run-2", at=datetime(2026, 12, 1, tzinfo=timezone.utc))
        shuffled = self.new.sample(frac=1, random_state=1)
        self.assertEqual(sc.write_decision(shuffled, rerun), "unchanged")

    def test_conflicting_content_is_refused(self):
        changed = self.new.copy()
        changed.loc[changed.index[0], "model_prediction_eur"] += 1e-6
        with self.assertRaises(sc.FrozenModelError):
            sc.write_decision(self.new, changed)
        relabelled = self.new.assign(scoring_version="score-v2")
        with self.assertRaises(sc.FrozenModelError):
            sc.write_decision(self.new, relabelled)
        with self.assertRaises(sc.FrozenModelError):
            sc.write_decision(self.new.iloc[1:], self.new)  # a partial earlier write is not silently completed

    def test_other_versions_and_cities_are_isolated(self):
        other_version = self.new.assign(model_version="price-v0", model_prediction_eur=1.0)
        self.assertEqual(sc.write_decision(other_version, self.new), "append")
        milan = self.new[self.new["city"] == "milan"]
        florence = self.new[self.new["city"] == "florence"]
        self.assertEqual(sc.write_decision(milan, florence), "append")
        self.assertEqual(sc.write_decision(pd.concat([milan, other_version]), milan), "unchanged")

    def test_duplicate_keys_are_refused(self):
        with self.assertRaises(ValueError):
            sc.write_decision(None, pd.concat([self.new, self.new.head(1)]))
        with self.assertRaises(sc.FrozenModelError):
            sc.write_decision(pd.concat([self.new, self.new.head(1)]), self.new)


if __name__ == "__main__":
    unittest.main()
