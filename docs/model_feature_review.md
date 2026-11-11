# Model feature and leakage review (MODEL-01)

Owner: Mykolaichuk Nazar. Reviewed against `PREDICTORS` in `airbnb/gold.py` and the silver
schema in `airbnb/silver.py` on `yaropolk/feature3-eda-gold` (`d67faa9`). Missingness figures come
from Maksym's [EDA handoff](eda_handoff.md) and EDA notebook; where the EDA gives no figure, the
rate must be measured on **training rows** in MODEL-04 and is marked "measure".

Status: signed off for MODEL-04. The "measure" items below are now measured on the persisted
**official training rows only** (split `airbnb-v1`, 17,255 Milan + 9,684 Florence) by
`notebooks/07_train_model.py` stage `profile`, run 633923351197764 at commit `c143b08`
(`model_features` Delta v2, `model_split` v0). No test row was read. The final allowlist is in
`airbnb/price_model.py` (`FEATURES`) and in the section "Final allowlist (price-v1)" below.
`airbnb/gold.py` is Yaropolk's file and is not changed here: the model selects the allowlist by
name from `model_features`.

## Training-row measurements (profile run 633923351197764)

Missing = null or blank. "Rare" = fewer than 50 training rows. All candidates are listing
attributes in the same snapshot, so every one is available at prediction time, including for
listings without a price; review scores exist only when the listing has reviews.

| Feature | Missing Milan | Missing Florence | Levels | Rare levels (rows) | p01 / p50 / p99 | Max |
|---|---|---|---|---|---|---|
| `room_type` | 0 % | 0 % | 4 | 2 (91: Hotel 46, Shared 45) | – | – |
| `property_type` | 0 % | 0 % | 55 | 42 (467 rows, 1.7 %) | – | – |
| `accommodates` | 0 % | 0 % | 16 | – | 1 / 4 / 10 | 16 |
| `bedrooms` | 0 % | 0 % | 13 | – | 0 / 1 / 4 | 12 |
| `beds` | 2.1 % | 1.6 % | 18 | – | 1 / 2 / 6 | 20 |
| `bathrooms_n` | 0 % | 0 % | 21 | – | 1 / 1 / 3 | 21 |
| `bath_shared` | < 0.1 % | < 0.1 % | 2 (true 1,185; 4 rows missing in total) | 0 | – | – |
| `minimum_nights` | 0.6 % | 3.0 % | 54 | – | 1 / 1 / 31 | 365 |
| `long_stay` | 0.6 % | 3.0 % | 2 (true 2,494) | 0 | – | – |
| `dist_center_km` | 0 % | 0 % | – | – | 0.16 / 2.03 / 7.07 | 9.73 |
| `has_reviews` | 0 % | 0 % | 2 (false 3,194) | 0 | – | – |
| `review_scores_*` (all seven) | 13.6 % | 8.7 % | – | – | rating 3.00 / 4.84 / 5.00 | 5 |
| `log_host_listings_count` | 0 % | 0 % | – | – | 0.69 / 1.79 / 6.30 | 7.24 |
| `host_is_superhost` | 0 % | 0 % | 2 (true 10,005) | 0 | – | – |
| `instant_bookable` | **100 %** | **100 %** | 0 | – | – | – |

Spearman correlation of review sub-scores with `review_scores_rating` (training rows with
reviews): accuracy 0.81, value 0.80, cleanliness 0.75, communication 0.72, check-in 0.68,
location 0.45.

Property types with ≥ 50 training rows (13): Entire rental unit 16,471; Entire condo 5,039;
Private room in rental unit 1,555; Private room in condo 584; Entire home 553; Private room in
bed and breakfast 550; Entire loft 432; Room in hotel 415; Entire vacation home 328; Entire
serviced apartment 225; Private room in home 145; Room in boutique hotel 125; Private room in
vacation home 50. The grouping is refitted on whichever rows a model is fitted on (subtrain
during selection, all training rows for the final model), so the kept list can differ slightly.

## Final allowlist (price-v1)

```
categorical: room_type, property_type (grouped), bath_shared, long_stay, has_reviews, host_is_superhost
numeric:     accommodates, bedrooms, beds, bathrooms_n, minimum_nights (log1p), dist_center_km (log1p),
             log_host_listings_count, review_scores_rating, review_scores_cleanliness,
             review_scores_location
```

Changes from the draft allowlist, all decided from the measurements above before any model was fitted:

- `instant_bookable` dropped: 100 % missing in both training cities.
- `review_scores_value` dropped: it rates value for the price paid (partly encodes the target).
- `review_scores_accuracy`, `_checkin`, `_communication` dropped for compactness: they correlate
  0.68–0.81 with the overall rating and describe host service, not the listing. `cleanliness`
  and `location` (0.45, carries location information) are kept.
- `room_type` is **not** rare-grouped: Hotel room (46) and Shared room (45) are below 50 rows but
  have opposite price levels; merging them would be wrong. Only `property_type` is grouped.
- Booleans are encoded as categories `true` / `false` / `__missing__`.
- Every numeric feature is capped at its fit-row 99th percentile (limits linear extrapolation in a
  new city); review scores are median-imputed without an indicator because `has_reviews` already
  marks the missing rows; other numerics get median imputation plus a missing indicator when the
  fit rows have missing values.

## Rules for every model

- Target: `price_eur` (EUR, no conversion). Model `log(price_eur)` and convert back; report MAE in EUR.
- All imputation values, category vocabularies, clipping bounds and scalers are fitted on
  `evaluation_split = 'train'` rows only (`airbnb/model.py`), never on test rows.
- Unseen categories map to an explicit `__other__` level, and a missing value maps to `__missing__`.
  Neither ever raises an error.
- Numeric imputation uses the training median plus a `<name>_missing` indicator when the training
  missing rate is above 0 %.
- Never predictors or test filters: `price_eur`, `price`, `raw_price`, `price_quote_*`,
  `estimated_revenue_l365d`, `estimated_occupancy_l365d`, `price_class`, `city_price_p99`,
  `exclusion_reason`, `eligible_for_analysis`, `quality_flags` (contains `missing_price`,
  `nonpositive_price`), `exclusion_reasons`, any prediction, residual, error or baseline column.
  `eligible_for_training` is used only to choose split-eligible rows; it is never a feature.

## Current `PREDICTORS` (from `airbnb/gold.py`)

| Feature | Decision | Silver type | Missingness | Encoding | Why useful | Leakage risk | Transfer risk (unseen city) |
|---|---|---|---|---|---|---|---|
| `room_type` | keep | string | Flagged `missing_room_type` when null; rate: measure | One-hot of training levels + `__other__`/`__missing__` | Strongest price driver; part of the baseline | None | Low. Rare levels (`Hotel room`, `Shared room`) are small in A/B; a level unseen in training uses `__other__` |
| `property_type` | transform | string | Measure | Keep training levels with ≥ 50 training rows across both cities; the rest become `__other__` | Separates e.g. serviced flats from rooms in homes, beyond `room_type` | None | **High.** High cardinality; the long tail is city-specific. Grouping limits overfitting; the share of `__other__` in a new city must be reported |
| `accommodates` | keep | int | Flagged when null/≤ 0; rate: measure | Numeric, clipped to the training [1, p99] | Guest capacity; part of the baseline | None | Low |
| `bedrooms` | keep | double | Not quantified in EDA: measure | Training-median impute + indicator; clip to training p99 | Size signal | None | Low |
| `beds` | keep | double | 1.5–2 % (EDA) | Training-median impute + indicator; clip | Size signal | None | Low |
| `bathrooms_n` | keep | double | `bathrooms_text` < 0.03 % (EDA) | Training-median impute + indicator | Size/quality signal | None | Low. Parsing depends on `bathrooms_text` wording. An unparsed value is null and flagged `invalid_bathrooms_text` |
| `bath_shared` | keep | boolean | As `bathrooms_text` | 0/1 + `__missing__` indicator | Shared bath lowers price, mainly for private rooms | None | Low |
| `minimum_nights` | transform | int (capped 365) | 0.6 % Milan, 2.8 % Florence (EDA) | `log1p`, training-median impute + indicator | Long minimum stays come with lower nightly prices | Low. A listing's rules are set with its price, but they are not computed from it | Medium. The monthly-stay share differs by city (11 % / 5 %) |
| `long_stay` | keep | boolean | Null when `minimum_nights` null | 0/1, missing → training mode + indicator | Proxy for monthly pricing (~45 % lower price; EDA) | Low. Agrees 99.5–99.7 % with the leaking `is_monthly_priced` flag, but derived only from `minimum_nights` | Medium. Same as above |
| `dist_center_km` | transform | double | Null when coordinates or city centre are missing (`missing_city_centre` flag) | `log1p`, training-median impute + indicator | Location premium, defined the same way in every city | None | **Medium–high.** Depends on the configured centre. City size and shape differ, so a km means a different premium in each city. Report error by distance band |
| `has_reviews` | keep | boolean | Never null when `number_of_reviews` is known | 0/1 | Separates new or inactive listings. Review scores are null if and only if there are no reviews (EDA) | Low | Low |
| `review_scores_rating` | keep | double | Null ⇔ no reviews (structural) | Training-median impute; `has_reviews` is the indicator | Quality signal | Low | Low–medium. Score inflation can differ by city |
| `review_scores_accuracy`, `_cleanliness`, `_checkin`, `_communication` | keep for tree models; for a linear model keep only if training-validation shows a gain | double | Null ⇔ no reviews | As rating | Small extra signal | Low | Low–medium. Strongly collinear with the rating |
| `review_scores_location` | keep | double | Null ⇔ no reviews | As rating | Guest view of location; complements distance | Low | Medium. Its meaning is relative to each city |
| `review_scores_value` | **drop** (recommended) | double | Null ⇔ no reviews | — | — | **Medium.** "Value" means quality relative to the price paid, so it partly encodes the target | Medium |
| `log_host_listings_count` | keep | double | Measure (null when the count is missing or < 0) | Training-median impute + indicator | Professional multi-listing hosts price differently | None | Medium. The share of professional hosts differs by city |
| `host_is_superhost` | keep | boolean | Not quantified in EDA: measure | Three levels: true / false / `__missing__` | Host quality signal | Low | Low |
| `instant_bookable` | **drop** | boolean | **100 % empty in both cities (EDA)** | — | None: constant in training | None | **High.** If a new snapshot fills it, the frozen model has never learned it. It must not be in the frozen allowlist |

## Fields outside `PREDICTORS` that were considered

| Field | Decision | Reason |
|---|---|---|
| `city` | drop as a predictor | It has no value for a new city. Florence's ≈ +20 % price level is a known transfer risk and must not become a fitted city effect. `city` stays as metadata for the split and reports |
| `neighbourhood_cleansed` | drop | 87 levels in Milan versus 5 in Florence (EDA). The levels are city-specific and do not transfer. Use it for error analysis only |
| `neighbourhood`, `neighbourhood_group_cleansed` | drop | 100 % empty (EDA) |
| `latitude`, `longitude` | drop (raw) | Absolute positions are specific to each city. `dist_center_km` carries the transferable part |
| `availability_*`, `has_availability` | drop | Partly a consequence of price. Missing price is tied to `availability_365 = 0` (MNAR; EDA) |
| `number_of_reviews*`, `reviews_per_month`, `days_since_last_review` | not in v1 | They proxy booking volume, which reacts to price. `has_reviews` keeps the safe part. Revisit only on training-validation evidence |
| `estimated_occupancy_l365d`, `estimated_revenue_l365d` | drop | Leak: revenue = occupancy × price (ratio 1.000 ± 0.001; EDA) |
| `price_quote_*` | drop | Leak: the per-night quote equals `price` in 100 % of rows (EDA) |
| `price_class`, `city_price_p99`, `exclusion_reason`, `eligible_for_analysis` | drop; never test filters | Computed from `price_eur` over the whole snapshot, including test rows |
| `quality_flags`, `exclusion_reasons` | drop | Contain price-derived flags |
| `baseline_prediction_eur` | not a v1 feature | A target encoding. It would need out-of-fold fitting to avoid leakage |
| ids, URLs, `host_id`, `name`, `description`, `license`, `scrape_id` | drop | Identifiers or free text that lead to memorisation |
| `host_since`, `host_response_*`, `host_acceptance_rate`, `host_total_listings_count`, `bathrooms`, `calendar_updated` | drop | 100 % empty in both cities (EDA) |

## Draft allowlist (MODEL-01; superseded by "Final allowlist (price-v1)" above)

```
room_type, property_type (grouped), accommodates, bedrooms, beds, bathrooms_n, bath_shared,
minimum_nights (log1p), long_stay, dist_center_km (log1p), has_reviews, review_scores_rating,
review_scores_accuracy, review_scores_cleanliness, review_scores_checkin,
review_scores_communication, review_scores_location, log_host_listings_count, host_is_superhost
```

Dropped from the current `PREDICTORS`: `instant_bookable` (empty) and `review_scores_value`
(price-relative). Yaropolk may remove both from `PREDICTORS` in gold, but that is not required:
the model selects columns by name.

## Split, baseline and evaluation decisions (implemented in `airbnb/model.py`)

- **Split (D8):** SHA-256 of `salt|city|listing_id` with salt `airbnb-v1`. A listing is `test` when
  its hash value in [0, 1) is below 0.20. The result does not depend on row order, on other rows
  or on price. Only `eligible_for_training = true` rows are split. Other rows keep
  `evaluation_split = NULL` and a `split_exclusion_reason`. Each listing is a Bernoulli draw, so
  the realised share varies by about ±0.3–0.4 percentage points (1 σ) at A/B sizes. The notebook
  records the actual share per city. Persisted to `airbnb_gold.model_split`, keyed by
  `(city, snapshot_date, listing_id, split_salt)`.
- **Baseline (D3):** pooled Milan + Florence training medians by `room_type × accommodates`, then
  by `room_type`, then the overall median. There is no city-level fallback, because it would be
  undefined for a new city. Missing or blank room types, and accommodates that are null, ≤ 0 or
  not whole numbers, fall back to the next level. Every row gets a prediction and a
  `baseline_level`. There is no minimum cell size: tiny cells (EDA) are used as they are, as the
  brief requires. Persisted to `airbnb_gold.baseline_lookup`, keyed by `baseline_version`.
- **MAE (D4):** the headline population is every `test` row with a valid positive actual price,
  including `extreme_high` and `stale_high` rows. All predictions are scored on identical rows, and
  a missing prediction on a headline row raises an error. An optional upper-price cut-off must be
  fitted on training rows (`fit_upper_price_threshold`). Its results are labelled as a
  supplementary population and never change the headline.
