# Silver listings: first implementation

Run `notebooks/02_prepare_silver` from the Databricks Git folder, using the same catalog, city and snapshot date as the completed bronze load. Run Milan and Florence separately. The notebook checks for a successful bronze manifest entry before writing. If Florence has not been loaded yet, finish notebook 01 for Florence first.

This is a conservative typing foundation pending Maksym's EDA and the team's cleaning decisions. There are no price cutoffs, imputation, model feature selection or Venice inputs.

## Data contract

Target: `<catalog>.airbnb_silver.listings`. One row per `(city, snapshot_date, listing_id)`; all bronze rows remain. Invalid or duplicate keys stop the write. Repeating a city/date replaces only that slice; other cities/dates remain unchanged.

- Original source fields are preserved under `raw_<original_name>`, including `raw_price`. Bronze ingestion metadata retains its `_` prefix.
- `listing_id` and `host_id` are big integers; `city` and `snapshot_date` identify the source snapshot.
- `price` is `DECIMAL(18,2)`, with `currency = EUR`. Missing, unparseable, zero or negative prices remain with exclusion reasons.
- Numeric predictors include accommodates, bedrooms, beds, bathrooms, nights, availability, reviews and coordinates. Failed casts become null, with flags for nonblank values that cannot be parsed. Optional absent fields become null. NaN/infinity become null and are flagged.
- Room/property types and neighbourhood names are trimmed without category remapping. Superhost and instant-bookable recognise `t/f` and `true/false`; other nonblank values are flagged.
- `quality_flags` describes observed problems; `exclusion_reasons` describes target/key problems. `eligible_for_training` means only that the key and positive target are valid. Predictors still need EDA and leakage review.

## Initial rules and reasons

| Rule | Reason |
|---|---|
| Preserve every raw field and row | Keep cleaning auditable and expose excluded-target counts |
| Parse decimal-dot prices with optional comma thousands separators | Avoid silently misreading ambiguous formats such as `1.234,56` |
| Accept leading `$` or `€` formatting symbols | Inside Airbnb formatting can use `$` in EUR cities; the project region determines currency, with no FX conversion |
| Exclude missing/unparseable/nonpositive targets from training | They do not provide a usable positive nightly-price label |
| Flag impossible availability/coordinates and nonpositive accommodates | Expose structural issues without inventing outlier removal |
| Keep large positive prices and unseen categories | Their treatment requires EDA and model decisions |

Confirm the price-format rule against raw samples during EDA. Other formats are flagged and require a documented change.

## Acceptance in Databricks

1. Run notebook 02 for Milan, then Florence after its bronze load.
2. Confirm silver and bronze counts match for each snapshot.
3. Inspect `raw_price`, `price`, `quality_flags`, `exclusion_reasons` and `eligible_for_training`, especially every price-format failure.
4. Rerun Milan and verify both cities' row counts and keys are unchanged.
5. Send the silver table and quality summaries to Maksym and Nazar. Agree additional cleaning rules from EDA before extending the transformation.

Do not report these workspace checks as passed until they run. Local tests cover synthetic prices, invalid/missing values, optional columns, unexpected categories, row preservation, nonfinite predictors and the bronze city-parameter regression. They do not exercise Delta writes, workspace permissions or real datasets.

Run checks with `SPARK_LOCAL_IP=127.0.0.1 python3 -m unittest discover -s tests -v` using PySpark 4.0.1 and Java 21. Databricks uses the workspace's supplied PySpark runtime.
