# Gold handoff for Maksym and Nazar

Branch: `yaropolk/feature3-eda-gold`. Execution is pending; announce tables as ready only after notebook 03 succeeds for both cities. Freeze the A/B pipeline and model before Week 2 and Venice.

## Run

Pull the branch in Databricks. If old modules were imported, run `dbutils.library.restartPython()` in a separate cell first. Run updated notebook 02 for Milan and Florence, then notebook 03 for each, using the same catalog/dates. Reconcile counts against silver and the EDA; share actual table names and access with both teammates.

All outputs are in `<catalog>.airbnb_gold`. Each run replaces only its city/snapshot. Outputs are separate Delta writes, not one multi-table transaction: rerun the entire notebook after a failed run before announcing a handoff. Filter snapshots to avoid counting a listing twice.

| Table | Grain | Consumer |
|---|---|---|
| `city_metrics` | city/snapshot | City overview/comparison |
| `room_type_metrics` | city/snapshot/room_type | Room mix/prices |
| `neighbourhood_metrics` | city/snapshot/neighbourhood_cleansed | Neighbourhood comparisons |
| `model_features` | city/snapshot/listing_id | Nazar's model input |
| `predictions` | Proposed: city/snapshot/listing_id/model_version | Nazar publishes after evaluation |

## Metric populations

- `listings`: distinct listing IDs, all rows. `hosts`: distinct nonnull host IDs.
- `priced_listings`: `eligible_for_analysis`, excluding missing/invalid/extreme/stale prices.
- City/room `median_price_eur`: positive prices excluding extremes, including stale-high, matching the EDA city aggregate. This differs from the priced-listings population.
- Neighbourhood median: analytical population, null unless at least 20 priced listings; `meets_price_sample_minimum` exposes suppression. All counts remain visible.
- `open_days_share_365`: average valid availability / 365. `share_blocked`: share of valid availability observations equal to zero. Neither is occupancy. `availability_observations` exposes the denominator; missing/invalid values are excluded.
- `avg_review_score`: nonnull scores for listings with at least one review.
- `share_multi_listing_hosts`: listing-weighted share with `calculated_host_listings_count >= 2`, excluding unknown counts. Label it **share of listings from multi-listing hosts**, not a fraction of distinct hosts.
- `room_type_mix`: room-type listings / city listings, including a null group when present.

Do not sum medians/distinct host counts or average shares across groups. Use city metrics for city totals. Null neighbourhood/room labels mean unknown.

## Model contract

`model_features` keeps all rows. Nazar filters structural `eligible_for_training`, creates the per-city holdout, then fits imputation/preprocessing and model choices using training/validation only.

`price_eur` is the target. City/snapshot/listing ID, currency and eligibility are metadata. Predictors are explicitly listed in `airbnb/gold.py`; select them by name. Raw fields, price quotes, estimated revenue/occupancy, source identifiers and descriptive p99/price classes are absent. No imputation is fitted here. City categories still need unseen-city handling.

Suggested prediction fields to finalise with Nazar: keys, `model_version`, `run_id`, `evaluation_split` (`train`, `test`, `unseen`), `actual_price_eur`, `baseline_prediction_eur`, `prediction_eur`, `absolute_error_eur`, and a nullable scoring-exclusion reason. Cover every listing, using null predictions and reasons when scoring is impossible. This branch does not create fake predictions or an empty prediction table.

Snapshot-wide p99/classes must not filter headline test MAE. Fit percentile-based training treatment on training rows only. Report model and baseline on identical full valid-price holdout rows; optional filtered results must be labelled separately.

## Acceptance

Check counts against silver; room counts and mix reconcile to city totals; low-sample neighbourhood medians are null; price classes reconcile to total rows. Rerun one city and confirm the other is unaffected. Record successful run evidence before handoff. Maksym can validate definitions and prepare questions now; Week 2 model pages require Nazar's real predictions.
