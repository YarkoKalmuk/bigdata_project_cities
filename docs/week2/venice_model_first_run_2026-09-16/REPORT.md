# Venice: first unchanged frozen-model scoring (CITYC-03)

**Result: SUCCESS on the first and only submission. Stopped before any fix or model change.**

Owner: Mykolaichuk Nazar. Recorded 2026-11-11 (UTC). Every number below comes from the
Databricks run output or from server-side SQL on the stored tables. Statement IDs are in
[sql_statements.jsonl](sql_statements.jsonl).

| | Venice (unseen city, first run) | Milan + Florence (frozen held-out test) |
|---|---:|---:|
| Evaluated listings | 8,144 | 6,863 |
| Frozen baseline MAE (EUR) | **142.46** | 95.47 |
| Frozen `price-v1` model MAE (EUR) | **106.07** | 75.88 |
| Model improvement over baseline | 36.39 EUR (25.5 %) | 19.58 EUR (20.5 %) |
| Model MAE / mean actual price | 35.2 % | 32.8 % |
| Mean signed residual (model − actual) | −77.09 | −27.23 |
| Underprediction rate | 66.6 % | 44.0 % |

Venice model MAE is **+30.18 EUR (+39.8 %)** worse than the frozen A/B test MAE. The model
still beats the frozen A/B baseline on Venice. Its relative improvement is larger than on A/B
(25.5 % vs 20.5 %), and it beats the baseline on 73.8 % of listings.

## 1. Freeze verification (before scoring)

| Item | Verified value |
|---|---|
| Freeze tag | `M1-freeze` (annotated tag object `ab035707b6ac6470f45fccb79ee9ebb3f5e037dc`) |
| Freeze commit | `7f76cbe6936e76fa3a7685ac90b40c1ce1c253df` |
| Executable files | All 21 files in `docs/week1_freeze_verification.json` `code_sha256` are byte-identical at the tag, at ETL Job source `f408ac0` and at this branch's base (`origin/main` `bb5b857`) |
| Model / scoring / schema | `price-v1` / `score-v1` / `predictions-v1` |
| Artifact | `/Volumes/workspace/airbnb_gold/model_artifacts/price-v1/model.joblib`, 1,484,150 B, SHA-256 `c0416cde7f652342ce5217a936a6aa0a60d2476cc059c7e970b0c8001640fb2c` |
| MLflow run | `a08250c6bcb5415c9591c6427e3d6bf7`; its `model.joblib` copy has the same SHA-256 |
| Selection record | SHA-256 `9122ca565f036895a0b41fff61f1ac39bfa5066ea0a4ef8195bb8c0402af49db` (table row and file) |
| Feature specification | `spec_sha256` `acd5e6e0e6a0badec0d34b4d2266c6485bba6135c679d92169db8a419992ea99`; 16 features; `hgb_leaves_31_iter_400`, `random_state` 20261111, scikit-learn 1.7.2 |
| A/B split `airbnb-v1` | 38,909 rows, fingerprint `d4625414b6181cecf5de7548b376d77377b500b5e758f0a49236a356ae00a880`; counts unchanged |
| A/B baseline lookup `airbnb-v1` | 44 rows, fingerprint `0ca4b685a4b85babccc0810105eb35c074b34808f28d1a54d4012149b987b65c` |
| Official A/B metrics | Model 75.72 / 76.18 / **75.88**; baseline 94.38 / 97.41 / **95.47** (Milan / Florence / both). Reproduced from the stored test rows and equal to `model_evaluation` |
| Venice ETL run | **782550938914199**, Job `816607442908043`, `TERMINATED/SUCCESS`; tasks bronze 307763021962734, silver 856540313555055, gold 134411079440636, validate 1105744524605448 |
| Venice inputs | `model_features` Delta **v5** (written by that ETL run): 8,844 rows and IDs, 8,144 priced, 700 null price. Raw file SHA-256 `dd14efeb…f982`; runtime manifest identical to the committed blob; canonical hash `84d3e544…ee02` = validation record |
| Protected objects | 15 full-row fingerprints from the Venice ETL evidence, re-run with the same SQL: **0 differences** from the post-ETL values. Milan/Florence raw-file hashes unchanged |

**Run-ID discrepancy:** the task brief gives the ETL run as `7825509389114199`. The Jobs API
says that run does not exist. The real run is `782550938914199` (one digit fewer), as in the
ETL evidence. This looks like a typo in the brief; this report uses the verified ID.

## 2. Scoring run

One-time job run **65362888524059** (task run **793825231802478**), 20:45:19–20:46:42 UTC.
[Run page](https://dbc-1766f78b-980d.cloud.databricks.com/?o=7474659920821008#job/794227027925555/run/65362888524059).
The notebook was `notebooks/08_score_predictions.py` from Git at the pinned commit
`7f76cbe6936e76fa3a7685ac90b40c1ce1c253df`; Databricks reports `used_commit` = the same.
It ran on serverless environment 6 (Python 3.12.3, scikit-learn 1.7.2, numpy 2.3.4, pandas 2.3.3).

| Parameter | Value |
|---|---|
| `catalog` | `workspace` |
| `cities` | `venice` |
| `snapshot_date` | `2026-09-16` |
| `model_version` | `price-v1` (scoring version `score-v1` is fixed in the frozen code) |
| `output_table` | `predictions` → `workspace.airbnb_gold.predictions` |
| `code_revision` | `7f76cbe6936e76fa3a7685ac90b40c1ce1c253df` |
| `scoring_run_id` | `venice-2026-09-16-price-v1-score-v1-first-run` |
| `sources_config_path` | `/Volumes/workspace/airbnb_bronze/raw_files/config/venice-2026-09-16-first-run.json` (same as the ETL run) |

Before scoring, the notebook re-checked the artifact, MLflow copy, registry rows, contract,
baseline lookup and A/B split. All checks passed. It loaded the artifact and called `predict`
only; no fitting code path exists in notebook 08. The write decision was `append`. No Venice
rows existed before.

| Table | Delta version read / written |
|---|---|
| `airbnb_gold.model_features` | read v5 (`source_feature_table_version` = 5 in every row) |
| `model_split` / `baseline_lookup` / `model_artifacts` / `model_selection` / `model_evaluation` | read v0 / v0 / v0 / v0 / v0, unchanged after |
| `airbnb_gold.predictions` | v2 before → **v3** after (`WRITE`, append, job run 65362888524059) |

## 3. Row reconciliation (stored rows, independent SQL)

| Check | Result |
|---|---|
| Venice prediction rows | **8,844**, all `scoring_run_id = venice-2026-09-16-price-v1-score-v1-first-run`; no other Venice rows |
| Distinct `(city, snapshot_date, listing_id, model_version)` | 8,844 (0 duplicates) |
| Missing from / extra relative to Venice `model_features` | 0 / 0 |
| `actual_price_eur` ≠ positive `model_features.price_eur` | 0 |
| Null or non-positive model prediction; `not_scored` rows | 0; 0 |
| `evaluation_split` | `unseen` for all 8,844 |
| Rows with valid actual and all four error columns | **8,144** |
| Rows with null actual and all error/residual columns null | **700** (`no_valid_actual_price`) |
| Residual and absolute-error formulas (model and baseline) | 0 violations |
| Baseline value and fallback level recomputed from the frozen lookup | 0 mismatches |
| A/B prediction rows | full-row fingerprint unchanged; still 38,909 rows from scoring run 772231092119601 |

Counts ([reconciliation.json](reconciliation.json)):

| Breakdown | Counts |
|---|---|
| Prediction status | `scored_with_actual` 8,144; `scored_no_actual` 700; `not_scored` 0 |
| Priced vs unpriced | 8,144 / 700 |
| Room type (all / priced) | Entire home/apt 6,826 / 6,336; Private room 1,970 / 1,762; Hotel room 36 / 35; Shared room 12 / 11 |
| Baseline fallback | `room_type_x_accommodates` 8,839; `room_type` **5**; `overall` 0 |
| Property type, model view | kept training level 8,515; `OTHER`, level in A/B training but under 50 rows 311; `OTHER`, level never in A/B: **18**; missing 0 |

The 5 fallback rows are Hotel room with 6, 7 or 9 guests (one each) and Shared room with 7
guests (two); all are priced. The 18 previously unseen property-type listings span 8 types:
Private room in tower 4, Private room in boat 3, Houseboat 3, Private room in pension 3,
Private room in castle 2, Room in heritage hotel 1, Dammuso 1, Private room in houseboat 1.
All are priced. The frozen grouping maps them to `OTHER` as designed; no row failed.

## 4. Metrics (population: all 8,144 Venice listings with a valid positive price)

The baseline uses only the frozen Milan/Florence lookup (`room_type × accommodates` →
`room_type` → overall A/B training median of 175.00 EUR). Nothing was fitted on Venice labels.
Machine-readable: [metrics.json](metrics.json).

| Metric | Model | Baseline |
|---|---:|---:|
| MAE (EUR) | **106.07** | **142.46** |
| Median absolute error | 46.77 | 72.50 |
| RMSE | 297.55 | 336.38 |
| Mean signed residual | −77.09 | −110.15 |
| Under / over / exact | 5,425 (66.6 %) / 2,719 (33.4 %) / 0 | 5,640 / 2,500 / 4 |

### By room type ([CSV](mae_by_room_type.csv); A/B: [CSV](ab_test_mae_by_room_type.csv))

| Room type | n | Model MAE | Baseline MAE | Mean residual | A/B test model MAE (n) |
|---|---:|---:|---:|---:|---:|
| Entire home/apt | 6,336 | 113.17 | 152.32 | −83.05 | 79.64 (5,968) |
| Private room | 1,762 | 81.56 | 108.35 | −56.56 | 50.96 (868) |
| Hotel room | 35 | 77.12 | 107.30 | −60.25 | 60.89 (13) |
| Shared room | 11 | 31.22 | 36.96 | +15.05 | 34.98 (14) |

### By actual-price band ([CSV](mae_by_price_band.csv); A/B: [CSV](ab_test_mae_by_price_band.csv))

The band edges are the frozen A/B fit-row quartiles and p95 from the locked selection record,
not chosen on Venice. Bands are defined by the actual price, so this table is a diagnostic only.

| Band (EUR) | Venice n | Venice model MAE | Venice baseline MAE | Venice mean residual | A/B n | A/B model MAE |
|---|---:|---:|---:|---:|---:|---:|
| [0, 128) | 1,252 | 26.87 | 55.28 | +20.96 | 1,630 | 35.89 |
| [128, 174.6) | 1,229 | 30.07 | 33.70 | +8.97 | 1,756 | 30.70 |
| [174.6, 249) | 1,996 | 41.58 | 50.50 | −13.21 | 1,689 | 39.42 |
| [249, 513) | 2,859 | 95.48 | 140.03 | −77.00 | 1,440 | 87.99 |
| ≥ 513 | 808 | 541.16 | 678.73 | −518.0 | 348 | 618.04 |

Within each band, Venice error is close to A/B error: −9.0 to +7.5 EUR in the four lower
bands, and lower in the top band. Venice has many more expensive listings: 45.0 % are at
249 EUR or more (26.1 % for A/B), and 9.9 % at 513 EUR or more (5.1 %). The ≥ 513 band alone
produces 50.6 % of Venice's total absolute error. Re-weighting Venice band MAEs to the A/B
band mix gives about 71.8 EUR, close to the A/B 75.88. So most of the gap comes from Venice's
higher price level and its larger expensive tail. This is a descriptive decomposition only:
it conditions on the target and is not a metric.

### Previously unseen property types ([CSV](mae_by_property_type_status.csv))

| Group | n | Model MAE | Baseline MAE | Mean residual |
|---|---:|---:|---:|---:|
| Never in A/B (→ `OTHER`) | 18 | 193.42 | 246.50 | −173.07 |
| In A/B training, under 50 rows (→ `OTHER`) | 275 | 99.83 | 118.91 | −54.02 |
| Kept training levels | 7,851 | 106.09 | 143.04 | −77.68 |

The 18 unseen-type listings have high error (n is small) but make up 0.4 % of total
absolute error. Category shift is not the main driver.

### Distance from the configured centre ([CSV](mae_by_distance_band.csv), [cap CSV](mae_by_distance_cap.csv))

| Distance band (km, frozen `DISTANCE_BANDS_KM`) | n | Model MAE | Baseline MAE | Mean residual |
|---|---:|---:|---:|---:|
| [0, 1) | 3,366 | 142.89 | 199.78 | −113.13 |
| [1, 2) | 2,382 | 107.76 | 132.23 | −88.21 |
| [2, 4) | 373 | 103.39 | 110.05 | −72.48 |
| [4, 8) | 171 | 71.48 | 70.96 | −35.68 |
| ≥ 8 | 1,852 | 40.70 | 64.55 | −2.00 |

The frozen model caps `dist_center_km` at the A/B training p99 of **7.07 km**. In Venice,
2,105 of 8,844 listings (23.8 %) are beyond that cap: mainland and outer islands, up to
18.9 km. For comparison, 378 Milan listings (1.5 %) and 12 Florence listings (0.1 %) are beyond
it. These capped listings are predicted well (MAE 40.70, mean residual −2.08). The large
systematic underprediction is in the historic centre (< 2 km), where Venice prices exceed what
A/B listings of the same size and distance command.

### Residuals ([percentiles](residual_percentiles.json), [model histogram](residual_histogram_model.csv), [baseline histogram](residual_histogram_baseline.csv))

Signed residual = prediction − actual (negative = underprediction).

| Percentile | p1 | p5 | p10 | p25 | p50 | p75 | p90 | p95 | p99 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Venice model | −1,107.6 | −348.4 | −199.7 | −89.4 | −26.9 | +12.5 | +46.5 | +75.0 | +167.7 |
| Venice baseline | −1,204.8 | −472.9 | −286.9 | −139.3 | −52.2 | +14.8 | +61.4 | +84.5 | +145.5 |
| A/B test model | | −198.6 | | −32.0 | +6.5 | +35.4 | | +93.5 | |

Model histogram: < −500: 226; [−500, −200): 586; [−200, −100): 1,022; [−100, −50): 1,320;
[−50, 0): 2,271; (0, 50): 1,984; [50, 100): 497; [100, 200): 184; [200, 500): 48; ≥ 500: 6.
The largest 1 % of absolute errors (81 rows) carry 19.7 % of the total absolute error; the
largest 5 % carry 40.8 %.

### Largest errors ([under](largest_underpredictions.csv), [over](largest_overpredictions.csv))

The 10 largest underpredictions are all Entire home/apt or hotel-room listings in central
Venice, with actual prices of 3,449–12,047 EUR. Seven are silver `extreme_high`, two
`high_tail` and one `stale_high`. The worst is listing 1560209843287885749: actual 12,047,
model 370.82, baseline 213.00, residual −11,676.18. The 10 largest overpredictions (+447 to
+686 EUR) are all `normal` large homes (8–16 guests, 3–7 bedrooms). Several are on the
mainland at about 10 km. Silver price classes are target-derived and are shown only as labels,
never as filters. For reference, the 82 flagged high-price rows have model MAE 1,566–4,090 EUR
by class; the 8,062 `normal` rows have 86.33 ([CSV](mae_by_silver_price_class.csv)).

### Supplementary, secondary only

Population: listings with an actual price at or below the frozen A/B training P99,
**1,156.62 EUR**. It was recomputed from the 26,939 A/B training prices and reproduces A/B's
6,811-row supplementary MAE exactly. Venice: n = 7,999 (145 above the threshold); model MAE
**80.95**, baseline **114.10**. Same population on A/B test: model 59.63, baseline 78.24.
This is not a headline number.

## 5. Protection after scoring

Re-run after scoring ([protected_comparison.json](protected_comparison.json)):

- all 15 protected fingerprints are identical to before;
- artifact, selection file and the Milan, Florence and Venice raw-file and manifest hashes are identical;
- split, baseline, registry and evaluation identity checks are identical;
- every model and reference table version is unchanged.

The only change is `predictions` v2 → v3: an append of the 8,844 Venice rows.
The MLflow experiment `3472336104835299` holds only the frozen training run; no run started at
or after the scoring submission ([mlflow_check.json](mlflow_check.json)).
**No retraining, refitting, re-selection or model change occurred.**

## 6. Tests

Details: [tests.json](tests.json).

- Scoring 30/30, price model 14/14, model 35/35, inputs 9/9, job definition 3/3 passed.
  They cover artifact loading and hash refusal, the frozen feature contract, unknown
  categories in an unseen city, one row per listing, no fitting during scoring, metric
  reproduction and overwrite refusal.
- The full suite on this Windows machine ran 100 tests: 95 passed, 5 errors. The 5 are local
  Spark Python-worker crashes in silver, gold and EDA tests, not related to scoring. They were
  not fixed, because no code change is allowed.
- Live checks are listed in `tests.json`.

## 7. Problems observed and limitations

1. **Systematic underprediction.** Mean residual is −77 EUR; 66.6 % of listings are
   underpredicted (A/B: 44.0 %). It is strongest in the historic centre and in listings above
   249 EUR. The model carries A/B price levels into a more expensive market.
2. **Heavy tail.** 82 listings that silver flags as `extreme_high`, `stale_high` or `high_tail`
   (up to 12,047 EUR) dominate RMSE and a fifth of total MAE. They stay in the headline, as
   the rules require.
3. **Distance-feature transfer.** 23.8 % of Venice listings exceed the frozen 7.07 km distance
   cap. "Distance from Piazza San Marco" mixes water, islands and the mainland, which the A/B
   training data never covered.
4. **Category shift is small.** 18 listings have never-seen property types, plus 311 rare
   types, all handled by the frozen `OTHER` grouping. 5 rows use the `room_type` baseline
   fallback. No scoring failures.
5. **Context.** The Venice snapshot is 3 days earlier than A/B (2026-09-16 vs 2026-09-19). The
   700 unpriced listings have predictions but cannot be evaluated. Predictions are bit-exact
   only on the Databricks serverless runtime (see `docs/model_predictions_run.md`).

## 8. Is a pipeline fix or model change needed?

- **Pipeline fix: none appears necessary.** Every Venice row was ingested, featurised, scored
  and reconciled. Unseen categories and baseline fallbacks worked as designed. No defect was
  found that should have been handled from the start.
- **Model change: not needed for correctness; a team decision if Venice accuracy is a goal.**
  The model transferred partly: it still beats the frozen baseline by 25.5 %, but its absolute
  error is 39.8 % higher, with a systematic downward bias. Any adaptation would be a model
  change under a new `model_version`/`scoring_run_id`. If Venice labels are used, a fixed Venice
  test set must be reserved first and never tuned on, and the result reported separately from
  this first run.

## 9. Files and preservation

This directory is the permanent first-run record. Later fixes or model versions must write to
new directories and new `scoring_run_id`s; see [change_ledger.json](change_ledger.json). Other files:

- [run_request.json](run_request.json), [run_submission.json](run_submission.json), [first_scoring_run.json](first_scoring_run.json): request, run states and Git snapshot.
- [notebook_exit_summary.json](notebook_exit_summary.json): the notebook's own exit record.
- [freeze_checks_before.json](freeze_checks_before.json) / [after](freeze_checks_after.json), [protected_before.json](protected_before.json) / [after](protected_after.json), [file_hashes_before.json](file_hashes_before.json) / [after](file_hashes_after.json).
- [venice_analysis_raw.json](venice_analysis_raw.json): every query result.
- [evidence_index.json](evidence_index.json): SHA-256 of every file here.
