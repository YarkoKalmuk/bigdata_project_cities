# Silver listings after A/B EDA

Rules originate in Maksym's [EDA handoff](eda_handoff.md). Initial silver execution succeeded according to Yaropolk; this expanded version still needs workspace execution.

## Migration and contract

Pull `yaropolk/feature3-eda-gold`. If an older module was imported, run `dbutils.library.restartPython()` in a separate cell before running notebook 02. Rerun 02 for **both Milan and Florence**. Additive schema evolution preserves existing tables and replaces only the selected snapshot. Old snapshots otherwise retain null values in added columns; do not drop the table.

Target: `<catalog>.airbnb_silver.listings`; key `(city, snapshot_date, listing_id)`. Invalid/duplicate keys abort the write. Every bronze row and original `raw_<name>` value remains.

- Normalised source columns trim strings and map `''`, `'None'`, `'N/A'`, `'null'` to null, including `host_verifications`.
- `price` stays decimal for compatibility; `price_eur` is its double alias. `$`/`€` formatting and comma thousands separators do not imply currency conversion: these are EUR values. Ambiguous price formats are flagged.
- Numerics use `try_cast`; nonfinite values become null. Optional missing columns become null; extra columns are retained. Dates use tolerant casts. No imputation is fitted here.
- Parse `bathrooms_n` and `bath_shared` from `bathrooms_text`, including half-baths. Preserve empty numeric source `bathrooms` separately.
- Cap `minimum_nights` at 365, preserving `raw_minimum_nights`; derive `long_stay`, `has_reviews`, `days_since_last_review`, `log_host_listings_count` and haversine `dist_center_km` from configured centres.
- `quality_flags` exposes problems without removing rows; missing coordinates/centres yield null distance.
- `city_price_p99` uses positive prices in that city/snapshot. `price_class`: missing, invalid, extreme-high (> 3 × p99 or > EUR 1,000 per valid positive guest capacity), stale-high (> p99 with explicitly zero reviews in the last 12 months), high-tail, low-tail (< EUR 20), or normal. Unknown reviews do not imply zero.
- Singular `exclusion_reason` contains the EDA analytical exclusion (`missing_price`, `invalid_price`, `extreme_high`, `stale_high`). `eligible_for_analysis` is true when it is null.

## Evaluation distinction

Existing plural `exclusion_reasons` and `eligible_for_training` retain their structural key/positive-target meaning. A high positive target therefore remains in the headline evaluation population, even when analytically flagged.

Snapshot-wide percentiles/classes are descriptive, not predictors or train/test filters. Nazar must split first and fit any percentile-based training treatment using training rows only. Evaluate baseline and model on the same full valid-price holdout; filtered MAE may supplement it with explicit labelling. This intentionally does not implement the EDA notebook's suggestion to remove extremes from headline MAE.

## Workspace verification

1. Run updated 02 for both cities. Counts must match bronze and, for the same files, EDA: Milan 25,338; Florence 13,571.
2. Verify cleaned `host_verifications` is null while its raw literal is preserved.
3. Inspect prices/classes, bathrooms, capped nights, invalid dates and distances.
4. Rerun Milan: no duplicate keys and Florence unaffected.
5. Run 03 for each city; follow the [gold handoff](gold_contract.md).

Local tests use synthetic data with PySpark 4.0.1 / Java 21: `SPARK_LOCAL_IP=127.0.0.1 python3 -m unittest discover -s tests -v`. They do not verify Delta migration, workspace permissions or real city results.
