# Gold predictions run evidence (MODEL-06 / MODEL-07)

Owner: Mykolaichuk Nazar. Recorded 2026-11-11 (UTC). Every number below was read from Databricks run
output or SQL on the stored tables. Venice was not downloaded, configured, queried or scored.

## Code and environment

| Item | Value |
|---|---|
| Scoring code | `nazar/model-baseline` @ `329d3f114cfc1148db2761207154456409515573` (tree `5c78cd632d8d1961c848fb36613eb10010953ae2`) |
| Executed copy | exact `git archive` of that commit imported to `/Users/<owner>/airbnb_model_329d3f1/` (with `SOURCE_COMMIT`) |
| Files | `airbnb/scoring.py`, `notebooks/08_score_predictions.py`, `tests/test_scoring.py` |
| Model code | `airbnb/price_model.py` and `airbnb/model.py` unchanged since `3f79eb9` (selection) and `d1c2bd6` (training) |
| Environment | Databricks serverless environment 6: Python 3.12.3, scikit-learn 1.7.2, numpy 2.3.4, pandas 2.3.3 |

Nothing is fitted during scoring. The notebook loads the artifact, predicts, and writes.

## Table `<catalog>.airbnb_gold.predictions` (schema `predictions-v1`)

Key `(city, snapshot_date, listing_id, model_version)`; one row per `model_features` listing per model version.

| Column | Type | Meaning |
|---|---|---|
| `city`, `snapshot_date`, `listing_id` | string, date, bigint | Silver key |
| `model_version` | string | Frozen model (`price-v1`) |
| `scoring_version` / `prediction_schema_version` | string | `score-v1` / `predictions-v1` |
| `model_artifact_sha256`, `mlflow_run_id` | string | Artifact identity |
| `baseline_version`, `split_salt` | string | `airbnb-v1` / `airbnb-v1` |
| `evaluation_split` | string | `train`, `test` (persisted split), `excluded` (training city, not eligible), `unseen` (city the model never saw) |
| `actual_price_eur` | double | Valid positive `price_eur`, else null |
| `baseline_prediction_eur`, `baseline_fallback_level` | double, string | Frozen pooled lookup; level `room_type_x_accommodates`, `room_type` or `overall` |
| `model_prediction_eur` | double | Frozen model prediction in EUR; null only when `not_scored` |
| `absolute_error_eur`, `signed_residual_eur` | double | Model error; `signed_residual_eur = model_prediction_eur − actual_price_eur` (negative = under-prediction). Null without a valid actual |
| `baseline_absolute_error_eur`, `baseline_signed_residual_eur` | double | Same for the baseline |
| `prediction_status` | string | `scored_with_actual`, `scored_no_actual`, `not_scored` |
| `evaluation_exclusion_reason` | string | Null when errors exist; else `no_valid_actual_price`, `not_in_evaluation_split` or `model_not_scored` |
| `scoring_exclusion_reason` | string | Null when scored; else `non_finite_model_prediction` or `non_positive_model_prediction` |
| `scoring_run_id`, `scored_at` | string, timestamp | Databricks job run and UTC time of the write that created the rows |
| `source_feature_table_version` | bigint | `model_features` Delta version read |

## Frozen model checks (all passed in each run before any row was scored)

| Check | Result |
|---|---|
| Volume file `/Volumes/workspace/airbnb_gold/model_artifacts/price-v1/model.joblib` | 1,484,150 B, SHA-256 `c0416cde7f652342ce5217a936a6aa0a60d2476cc059c7e970b0c8001640fb2c` (also recomputed locally from a download) |
| MLflow run `a08250c6bcb5415c9591c6427e3d6bf7` copy of `model.joblib` | same SHA-256 |
| `airbnb_gold.model_artifacts` row | hash, spec, selection-record hash, candidate, family, scikit-learn version and MLflow ID all equal to `scoring.FROZEN_MODELS["price-v1"]` |
| `airbnb_gold.model_selection` row and `selection_record.json` | SHA-256 `9122ca565f036895a0b41fff61f1ac39bfa5066ea0a4ef8195bb8c0402af49db` for both |
| Code spec (features, preprocessing, candidates, rule) | `spec_sha256` `acd5e6e0e6a0badec0d34b4d2266c6485bba6135c679d92169db8a419992ea99` = locked |
| Artifact contract | fitted on exactly the 16 price-v1 features in order; `HistGradientBoostingRegressor` params equal the locked `hgb_leaves_31_iter_400`, `random_state` 20261111 |
| Baseline lookup `airbnb-v1` | 44 rows, fingerprint `0ca4b685a4b85babccc0810105eb35c074b34808f28d1a54d4012149b987b65c`, fitted on split `airbnb-v1`, snapshots `milan=2026-09-19;florence=2026-09-19` |
| Persisted split `airbnb-v1` | 38,909 rows, fingerprint `d4625414b6181cecf5de7548b376d77377b500b5e758f0a49236a356ae00a880`, counts unchanged |

Fingerprints are SHA-256 over sorted lines. The same values come from SQL:

```sql
SELECT sha2(concat_ws('\n', array_sort(collect_list(concat_ws('|', city, cast(snapshot_date AS string),
       cast(listing_id AS string), coalesce(evaluation_split, ''))))), 256)
FROM workspace.airbnb_gold.model_split WHERE split_salt = 'airbnb-v1';

SELECT sha2(concat_ws('\n', array_sort(collect_list(concat_ws('|', baseline_level, coalesce(room_type, ''),
       coalesce(cast(accommodates AS string), ''), cast(cast(round(median_price_eur * 1000000) AS bigint) AS string),
       cast(n_train AS string))))), 256)
FROM workspace.airbnb_gold.baseline_lookup WHERE baseline_version = 'airbnb-v1';
```

## Runs

| Run | Job run | Task run | Parameters | Start–end (UTC) | Result |
|---|---|---|---|---|---|
| 1 first scoring | 772231092119601 | 796954295181797 | `cities=milan,florence` | 17:15:20–17:16:40 | SUCCESS: `milan` created table, `florence` appended |
| 2 identical rerun | 439004645258706 | 619578019160463 | `cities=milan,florence` | 17:17:01–17:17:52 | SUCCESS: both `unchanged` |
| 3 single-city entry point | 850810674321113 | 858187179953820 | `cities=florence`, `snapshot_date=2026-09-19` | 17:18:15–17:18:59 | SUCCESS: `unchanged` |

All runs: `catalog=workspace`, `model_version=price-v1`, `output_table=predictions`, `code_revision=329d3f1`,
`scoring_run_id={{job.run_id}}`. Each run checked the official test MAE on the in-memory predictions
**before** writing, and again on the stored rows after writing.

## Table versions

| Table | Delta version read |
|---|---|
| `airbnb_gold.model_features` | 2 (`source_feature_table_version` in every row) |
| `airbnb_gold.model_split` | 0 |
| `airbnb_gold.baseline_lookup` | 0 |
| `airbnb_gold.model_artifacts` / `model_selection` / `model_evaluation` | 0 / 0 / 0 |
| `airbnb_gold.predictions` (output) | none → **1** after run 1 (v0 CTAS 25,338 Milan rows, v1 append 13,571 Florence rows); still **1** after runs 2 and 3 |

## Reconciliation (stored table, independent SQL)

| Check | Result |
|---|---|
| Rows | 38,909 = 25,338 Milan + 13,571 Florence = `model_features` rows for the two snapshots |
| Distinct `(city, snapshot_date, listing_id, model_version)` | 38,909 (0 duplicates) |
| Listings missing from / extra in predictions | 0 / 0 |
| Null baseline prediction / null model prediction | 0 / 0 |
| `evaluation_split` ≠ persisted split (null → `excluded`) | 0 |
| `actual_price_eur` ≠ positive `model_features.price_eur` | 0 |
| `signed_residual_eur` ≠ `model_prediction_eur - actual_price_eur` | 0 |
| Rows for any city other than Milan/Florence | 0 |
| Model versions in table | `price-v1` only |

### Counts

| City | Split | Status | Rows | Errors |
|---|---|---|---:|---|
| Milan | train | `scored_with_actual` | 17,255 | present (in-sample) |
| Milan | test | `scored_with_actual` | 4,399 | present (held out) |
| Milan | excluded | `scored_no_actual` | 3,684 | null; `evaluation_exclusion_reason = no_valid_actual_price` |
| Florence | train | `scored_with_actual` | 9,684 | present (in-sample) |
| Florence | test | `scored_with_actual` | 2,464 | present (held out) |
| Florence | excluded | `scored_no_actual` | 1,423 | null; `no_valid_actual_price` |

| City | `room_type_x_accommodates` | `room_type` | `overall` |
|---|---:|---:|---:|
| Milan | 25,335 | 3 | 0 |
| Florence | 13,570 | 1 | 0 |

`scoring_exclusion_reason` is null for all 38,909 rows (no `not_scored` row). The fallback counts are
the same as in the baseline run ([model_baseline_run.md](model_baseline_run.md)).

## Official metric reproduction (stored test rows)

| Group | n | Model MAE | Baseline MAE | Mean signed residual |
|---|---:|---:|---:|---:|
| Milan | 4,399 | 75.72109460621044 | 94.37535348942943 | −35.50 |
| Florence | 2,464 | 76.17608368869547 | 97.41181412337663 | −12.46 |
| Milan + Florence | 6,863 | 75.88444781898083 | 95.46552382340084 | −27.23 |

Largest absolute difference from the frozen record and from `airbnb_gold.model_evaluation`: **0.0**
for model and baseline. The test population is unchanged (same 6,863 rows). Negative mean residuals
mean the model under-predicts on average, as in [model_selection.md](model_selection.md).

## Idempotency

Run 2 and run 3 found rows for `price-v1` and the same city/snapshot, compared every content column
with the new predictions (everything except `scoring_run_id`, `scored_at`,
`source_feature_table_version`), found them identical and wrote nothing. The table stayed at Delta
version 1 and every stored row still carries `scoring_run_id = 772231092119601`. Different content
under an existing `model_version`/city/snapshot stops the notebook (unit-tested; see below).

## Portability (MODEL-07)

`notebooks/08_score_predictions.py` takes `catalog`, `cities`, `snapshot_date`, `model_version`,
`output_table`, `code_revision` and `scoring_run_id`. Cities must be in `config/sources.json`. A city at
its training snapshot gets its persisted split label; any other configured city is `unseen` and every
row with a valid price is evaluated. On real data this was checked for Milan + Florence and for
Florence alone; the `unseen` path was checked only on synthetic rows with unseen room types,
property types, boolean values and missing numerics (`tests/test_scoring.py`), as required before
the freeze.

## Tests

Linux container (Python 3.12.15, OpenJDK 21, PySpark 4.0.1, scikit-learn 1.7.2, numpy 2.3.4,
pandas 2.3.3, joblib 1.5.2), `SPARK_LOCAL_IP=127.0.0.1 python -m unittest discover -s tests -v` on
`329d3f1`: **87 run, 87 passed, 0 failed, 0 skipped** (bronze 3, silver 5, model 35, price model 14,
scoring 30). Windows (Python 3.12.14, same library versions): `tests.test_scoring tests.test_price_model
tests.test_model` → 79 run, 79 passed.

The scoring tests cover artifact load and prediction equivalence, hash/record/spec/feature/
hyperparameter/scikit-learn mismatch rejection, one row per listing, unpriced rows kept with null
errors, residual direction, all three fallback levels, unknown categories in an unseen city,
unscorable rows kept with a reason, duplicate-key rejection, split guards, official-metric checks,
no fitting during scoring (fit methods patched to fail), idempotent write decisions, conflict
rejection and version/city isolation.

## Limitations

- **Bit-exact only in the same environment.** A local dry run on Windows x86 with the same library
  versions matched 29,275 rows exactly, 9,620 to < 1e-9 EUR, and differed by 1.1–2.2 EUR on 14 Florence
  rows (1 test row), moving Florence test MAE by 0.0006 EUR. The likely cause is last-bit floating-point
  differences between x86 and the aarch64 serverless runtime that move a few rows across a tree split;
  this was not traced further. Official numbers and the gold table come from Databricks serverless
  environment 6, which reproduces them exactly. Score future cities there.
- `train` rows carry in-sample errors. Held-out metrics must filter `evaluation_split = 'test'`
  (Milan/Florence) or `'unseen'` (a new city). Dashboard and Genie instructions must say so.
- Two scoring runs started at the same time for the same city could both append; runs are
  sequential by convention.
- Each city is a separate Delta write. If a run fails after one city, rerun it: written cities are
  `unchanged`, missing ones are appended.
- Teammates have no Unity Catalog privileges on `airbnb_gold` yet (see the freeze-candidate manifest).
