# Price model selection and held-out evaluation (MODEL-04 / MODEL-05)

Owner: Mykolaichuk Nazar. Milan and Florence only; Venice was not downloaded, configured,
queried or used. Code: `airbnb/price_model.py`, `notebooks/07_train_model.py`.

## 1. Predeclared plan (committed before any validation result was read)

### Data roles

| Role | Rows | Used for |
|---|---|---|
| Subtrain | official `train` rows (split `airbnb-v1`) whose `SHA-256("airbnb-v1-model-selection" \| city \| listing_id)` unit is ≥ 0.20 | fitting preprocessing, category grouping, the validation baseline and every candidate |
| Validation | the other official `train` rows (unit < 0.20) | comparing candidates |
| Official test | persisted `evaluation_split = 'test'` rows | read once, by stage `final`, after the selection record is locked |

The `select` stage loads only `evaluation_split = 'train'` rows. The validation baseline is the
required `room_type × accommodates` median lookup **refitted on subtrain**, not the persisted
`airbnb-v1` lookup (which saw validation rows).

### Features and preprocessing

See [model_feature_review.md](model_feature_review.md) ("Final allowlist (price-v1)"). Every
fitted step is inside one scikit-learn pipeline (`TransformedTargetRegressor` → `Pipeline` →
`ColumnTransformer`), so it is fitted only on the rows passed to `fit`.

- Target: `log1p(price_eur)`; predictions are `expm1` back to EUR.
- `property_type`: levels with < 50 fit rows → `__other__`; missing → `__missing__`.
- Other categoricals (room type and the booleans): every fit-row level kept; unseen → `__other__`.
- One-hot with `handle_unknown="ignore"`: an unseen level never raises.
- Numerics: cap at the fit-row p99; `log1p` on `minimum_nights` and `dist_center_km`; fit-row
  median imputation (+ missing indicator, except review scores); standard scaling for ridge.

### Candidates (8 fits, fixed seed 20261111)

| Family | Model | Search space |
|---|---|---|
| `ridge_log` | `Ridge` on the scaled, one-hot design | `alpha` ∈ {0.1, 1, 10, 100} |
| `hgb_log` | `HistGradientBoostingRegressor` (scikit-learn 1.7.2, no new dependency), `learning_rate` 0.05, `min_samples_leaf` 40, `l2_regularization` 1.0, no early stopping | `max_leaf_nodes` ∈ {15, 31} × `max_iter` ∈ {200, 400} |

### Selection rule

1. Within each family, take the candidate with the lowest pooled (Milan+Florence) validation MAE.
2. A family qualifies only if that candidate beats the subtrain baseline by ≥ 5 % in Milan,
   in Florence **and** pooled.
3. Choose the simplest qualifying family (ridge < gradient boosting) unless the more complex
   one beats it by ≥ 3 % in Milan, in Florence and pooled.
4. If no family qualifies, stop and report; do not evaluate on test.

The rule, candidate list, features and preprocessing are hashed into `spec_sha256`. Stage
`final` refuses to run if the code's `spec_sha256` differs from the locked record.

## 2. Validation results and locked selection

Run 417986478430148 (`select`, commit `3f79eb9`, serverless environment 6: Python 3.12.3,
scikit-learn 1.7.2, numpy 2.3.4, pandas 2.3.3). Inputs: `model_features` v2, `model_split` v0.
Only official training rows were loaded.

| Fold | Milan | Florence |
|---|---|---|
| Subtrain | 13,821 | 7,757 |
| Validation | 3,434 | 1,927 |

Validation baseline (refitted on subtrain): cell level for every validation row except 1
Florence row (room-type fallback).

### Validation MAE (EUR; all validation rows with a valid positive price)

| Candidate | Milan | Florence | Milan+Florence | Gain vs baseline (M / F / both) | Fit s | Predict s | Size |
|---|---:|---:|---:|---|---:|---:|---|
| Baseline (subtrain medians) | 101.51 | 107.85 | 103.79 | – | – | – | median lookup |
| ridge α=0.1 | 88.93 | 94.58 | 90.96 | 12.4 / 12.3 / 12.4 % | 0.36 | 0.13 | 42 coefficients |
| ridge α=1 | 88.93 | 94.58 | 90.96 | 12.4 / 12.3 / 12.4 % | 0.34 | 0.13 | 42 |
| ridge α=10 | 88.94 | 94.62 | 90.98 | 12.4 / 12.3 / 12.3 % | 0.33 | 0.12 | 42 |
| ridge α=100 | 89.00 | 94.72 | 91.05 | 12.3 / 12.2 / 12.3 % | 0.29 | 0.13 | 42 |
| hgb 15 leaves × 200 | 86.16 | 88.37 | 86.96 | 15.1 / 18.1 / 16.2 % | 5.45 | 0.13 | 200 trees |
| hgb 15 leaves × 400 | 85.59 | 87.71 | 86.35 | 15.7 / 18.7 / 16.8 % | 7.09 | 0.39 | 400 trees |
| hgb 31 leaves × 200 | 85.47 | 87.54 | 86.21 | 15.8 / 18.8 / 16.9 % | 5.22 | 0.48 | 200 trees |
| **hgb 31 leaves × 400** | **85.26** | **87.45** | **86.05** | **16.0 / 18.9 / 17.1 %** | 8.71 | 0.35 | 400 trees × ≤ 31 leaves |

Supplementary (validation actual ≤ 1,162.93 EUR, the subtrain p99; Milan 3,405, Florence 1,908 rows):
baseline 75.62 / 85.18 / 79.05; best ridge 61.87 / 71.94 / 65.48; selected hgb 58.81 / 66.57 / 61.59.

### Decision (applied by `select_candidate`, recorded in `airbnb_gold.model_selection`)

- Best per family: `ridge_alpha_0.1` and `hgb_leaves_31_iter_400`. Both qualify (≥ 5 % better
  than the baseline in Milan, Florence and pooled).
- `hgb_leaves_31_iter_400` beats the best ridge by 4.1 % (Milan), 7.5 % (Florence) and 5.4 %
  (pooled), all ≥ 3 %, so the rule selects gradient boosting.
- **Locked:** `HistGradientBoostingRegressor(learning_rate=0.05, max_iter=400, max_leaf_nodes=31,
  min_samples_leaf=40, l2_regularization=1.0, early_stopping=False, random_state=20261111)` on
  `log1p(price_eur)`, with the price-v1 features and preprocessing above.
- `spec_sha256` `acd5e6e0e6a0badec0d34b4d2266c6485bba6135c679d92169db8a419992ea99`;
  selection `record_sha256` `9122ca565f036895a0b41fff61f1ac39bfa5066ea0a4ef8195bb8c0402af49db`.
  Per-candidate rows are in `airbnb_gold.model_candidate_metrics`.

### What drives the model (validation permutation importance, MAE increase in EUR)

Selected hgb: `dist_center_km` 13.6, `accommodates` 8.7, `minimum_nights` 5.9, `bathrooms_n` 5.7,
`bedrooms` 5.4, `log_host_listings_count` 5.0; every other feature ≤ 1.6
(`review_scores_location` 1.5, `property_type` 1.5, `room_type` 0.8).

Ridge (for interpretation; % price effect per one training SD or vs. the reference level):
Shared room −32 %, Room in hotel +44 %, Entire home/apt +31 %, Room in boutique hotel +28 %,
distance −16 % per SD of log distance, minimum nights −14 % per SD, accommodates +15 % per SD,
shared bath −11 %.

### Failure modes seen on validation (no decision was changed by these)

- **Top price tail dominates the error.** Rows at or above the subtrain p95 (513 EUR; 144 Milan,
  133 Florence) have MAE 995 / 557 EUR with the selected model, and every model underpredicts
  them (mean error −972 / −470). A log-target model predicts close to the conditional median, and
  these prices are not explained by the listing attributes available.
- **Underprediction overall** for Entire homes in Milan (mean error −46 EUR) and for private
  rooms in both cities; the cheapest quartile is overpredicted (+34 / +39 EUR).
- **Hotel rooms** (3 Milan, 9 Florence validation rows) are worse than the baseline (58 vs 48 and
  71 vs 55 EUR MAE): too few training rows for the model to separate them.
- **Distance 4–8 km in Florence** (75 rows) has MAE 341 EUR and mean error −286: a few expensive
  villas outside the centre.
- `property_type` falls into `__other__` for 1.7 % (Milan) and 3.2 % (Florence) of validation
  rows. The selected configuration is at the edge of its small grid (most leaves and trees); the
  grid was not widened after seeing results.

## 3. Held-out test evaluation (run once)

Run 1014284074152913 (`final`, commit `d1c2bd6`; the only change since `3f79eb9` is this
document, and the notebook checked `spec_sha256` and the selection-record hash before reading
test rows). The locked pipeline was refitted on all 26,939 official training rows (Milan 17,255,
Florence 9,684; 13.6 s), written to the volume, reloaded from the file and used to score the
6,863 test rows once. The baseline is the frozen `baseline_lookup` `airbnb-v1`.

### Headline: every test row with a valid positive price (`test_all_valid_positive_price`)

| Population | n | Baseline MAE | Model MAE | Absolute improvement | Percentage improvement |
|---|---:|---:|---:|---:|---:|
| Milan | 4,399 | 94.38 | **75.72** | 18.65 | 19.77 % |
| Florence | 2,464 | 97.41 | **76.18** | 21.24 | 21.80 % |
| Milan + Florence | 6,863 | 95.47 | **75.88** | 19.58 | 20.51 % |

The baseline column reproduces the frozen baseline evaluation exactly (94.3754 / 97.4118 /
95.4655). Model and baseline are scored on identical rows; no test row was dropped.

### Supplementary only: test actual ≤ 1,156.62 EUR (p99 of training prices)

| Population | n | Baseline MAE | Model MAE | Absolute improvement | Percentage improvement |
|---|---:|---:|---:|---:|---:|
| Milan | 4,363 | 75.83 | 57.78 | 18.05 | 23.80 % |
| Florence | 2,448 | 82.54 | 62.93 | 19.61 | 23.76 % |
| Milan + Florence | 6,811 | 78.24 | 59.63 | 18.61 | 23.78 % |

The threshold is fitted on training rows only and is the same value as in the baseline run.
It is not a headline number.

### Test failure modes (reporting only)

- The top price band (≥ 514 EUR, the training p95; 200 Milan, 146 Florence rows) still has MAE
  726 / 474 EUR and strong underprediction (mean error −713 / −431). The model's gain is mostly
  in the 250–514 EUR band (Milan 133 → 99, Florence 118 → 77 EUR).
- The cheapest quartile is overpredicted (+30 Milan, +39 Florence); in Florence the 128–175 EUR
  band is worse than the baseline (40.1 vs 27.2 EUR).
- Shared rooms (11 Milan, 3 Florence) are worse than the baseline (31.5 vs 12.8; 47.8 vs 19.2
  EUR), and Florence hotel rooms are level (67.7 vs 66.9): very few training rows.
- Milan listings within 1 km of the centre remain the hardest location band (MAE 154 EUR,
  mean error −108).
- `property_type` is `__other__`/`__missing__` for 1.6 % (Milan) and 2.2 % (Florence) of test rows.

## 4. Persisted artifacts (model identifier for the freeze)

| Item | Value |
|---|---|
| Model file | `/Volumes/workspace/airbnb_gold/model_artifacts/price-v1/model.joblib` (1,484,150 B) |
| Model SHA-256 | `c0416cde7f652342ce5217a936a6aa0a60d2476cc059c7e970b0c8001640fb2c` (recomputed from a download) |
| Selection record copy | `/Volumes/workspace/airbnb_gold/model_artifacts/price-v1/selection_record.json` |
| MLflow run | `a08250c6bcb5415c9591c6427e3d6bf7`, experiment `/Users/<owner>/airbnb_price_model` (params, test metrics, both files) |
| Tables | `airbnb_gold.model_selection` (1 row), `model_candidate_metrics` (48), `model_evaluation` (6), `model_artifacts` (1) |
| Split / baseline | `model_split` `airbnb-v1` (Delta v0), `baseline_lookup` `airbnb-v1` (v0); `model_features` v2 |
| Environment | Serverless environment 6, Python 3.12.3, scikit-learn 1.7.2, numpy 2.3.4, pandas 2.3.3, joblib 1.5.2, MLflow 3.12.0 (probe run 376778873486598) |

Loading the file needs `airbnb/price_model.py` on the path (custom transformers). Stage `final`
refuses a second evaluation of `price-v1`; any change needs a new `model_version`. No prediction
table for every listing exists yet (MODEL-06), and no Git freeze tag has been created.

## Runs

| Stage | Commit | Job run | Task run | Result |
|---|---|---|---|---|
| Environment probe | – | – | 376778873486598 | SUCCESS |
| `profile` | `c143b08` | 602761094288982 | 633923351197764 | SUCCESS (training rows only) |
| `select` | `3f79eb9` | 507329454375587 | 417986478430148 | SUCCESS; selection locked |
| `final` | `d1c2bd6` | 906579585632281 | 1014284074152913 | SUCCESS; test evaluated once |

Each run executed an exact `git archive` of its commit imported to
`/Users/<owner>/airbnb_model_<commit>/` in the shared workspace.

Local tests (Windows, Python 3.12.14, scikit-learn 1.7.2, numpy 2.3.4, pandas 2.3.3):
`python -m unittest tests.test_price_model tests.test_model` → 49 run, 49 passed. Silver and
bronze tests need PySpark and were not rerun here.
