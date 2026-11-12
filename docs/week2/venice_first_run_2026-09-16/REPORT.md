# Venice: unchanged first ETL run

**Result: SUCCESS. Stopped before fixes or model scoring.**

- First and only submitted Venice attempt: **782550938914199**.
- [Databricks run](https://dbc-1766f78b-980d.cloud.databricks.com/?o=7474659920821008#job/816607442908043/run/782550938914199); Job `816607442908043`.
- Snapshot: **2026-09-16**, detailed Inside Airbnb `listings.csv.gz`.
- Frozen tag: `M1-freeze`, commit `7f76cbe6936e76fa3a7685ac90b40c1ce1c253df`.
- Actual source used by every task: `f408ac01ffdd025fab6df220c8f89b24d3d4fda6`;
  its frozen task/module files match M1. No Job settings or executable files changed.
- Exactly one submission, zero task retries, zero repairs and zero model actions.

## Inputs and provenance

[Download/upload instructions](../venice_input_instructions.md) and
[runtime JSON](../../../runtime/venice-2026-09-16-first-run.json) document the
published source, volume paths and predeclared Piazza San Marco centre.
The snapshot differs from A/B's September 19 snapshot by three days.

Raw file: **5,465,156 bytes**, SHA-256
`dd14efeb23677a87e13f479802cd581b5e16191762a73e6b1373e263f79bf982`.
Canonical runtime-manifest SHA-256:
`84d3e54441a104cb6640b20e8bef56fdbdc97f26ee246608bd60f42f647fee02`.
Both uploaded files matched their original byte hashes. Validation recorded the
same canonical manifest hash. Original gzip bytes were never cleaned or rewritten.
Input preparation added the explicitly approved `WRITE VOLUME` permission on the
raw-files volume for the uploader. Uploads used `overwrite=False`; no model-table
permissions were changed and this was not a pipeline/model repair.

## First-run execution and outputs

| Task | Task run ID | Result |
|---|---|---|
| Bronze | 307763021962734 | SUCCESS |
| Silver | 856540313555055 | SUCCESS |
| Gold | 134411079440636 | SUCCESS |
| Validate | 1105744524605448 | SUCCESS |

Bronze, Silver and `workspace.airbnb_gold.model_features` each contain **8,844**
Venice rows; listing IDs are unique. Gold contains one city-metric row, four
room-type metric rows and 60 neighbourhood metric rows. All rows were retained;
**8,144** have usable positive targets and **8,101** are in the separate analytical
population. This distinction follows the frozen rules, not a new filter.

There were **no frozen-pipeline failures**. Rendered notebook tables/full runtime
logs remain attached to the linked Databricks run. The committed task output API
captures preserve status, metadata and available exit output; that API does not
export every rendered notebook table. Aggregate query results are in
[first_run_summary.json](first_run_summary.json).

## Observed differences, not fixes

Parsed-price medians below describe the observed snapshots, not a model's
predictions or MAE. Distance is from each configured centre; these ranges are
snapshot observations, not the fitted model's learned bounds.

| City | Listings | Missing raw price | Median parsed price (EUR) | Max centre distance (km) | Neighbourhoods |
|---|---:|---:|---:|---:|---:|
| Milan | 25,338 | 3,684 (14.54%) | 163.67 | 9.98 | 87 |
| Florence | 13,571 | 1,423 (10.49%) | 198.00 | 8.11 | 5 |
| Venice | 8,844 | 700 (7.91%) | 231.00 | 18.90 | 60 |

- **Schema:** the same 90 source columns as A/B; no missing or extra columns.
- **Price parsing:** all 8,144 present prices use `$` formatting but represent EUR.
  Zero nonblank/non-placeholder price strings failed parsing. Missing-price rows
  remain visible and excluded from the usable-target population.
- **Existing price classes:** 14 `extreme_high`, 29 `stale_high`, 39 `high_tail`,
  8,062 `normal`, 700 `missing_price`. These are frozen descriptive rules, not
  fitted model changes. Do not remove the flagged positive targets from the
  headline unseen-city MAE.
- **Category shift:** 18 Venice listings have property types absent from the full
  A/B snapshots; no new room types. This is not a fitted-vocabulary check and no
  model response is inferred from it.
- **Missing predictors:** beds missing for 114 listings; minimum nights/long-stay
  for 186; bathroom-derived fields for six; review scores for 681. Full per-city
  predictor null counts are recorded in the JSON summary.
- **Shared source limitations:** raw numeric bathrooms, host-verification values
  and instant-bookable are missing/placeholders throughout Venice too. The frozen
  bathroom-text parsing/null normalisation handled these without a code change.
- **Date flags:** Venice has no `review_after_snapshot` flags; the unchanged A/B
  data retains 568 in Milan and 282 in Florence. No dates were edited.

The quality-flag table for Venice contains only the 700 missing-price flags.
Distribution/category differences remain observations for the transfer story;
none has been turned into a repair or a model adjustment.

## Protection and first-run evidence

[Before](protected_before.json) / [after](protected_after.json) server-side content
fingerprints are identical for **19 protected objects**: A/B slices of all ETL
and prediction/split tables, pooled model/reference tables, both original A/B raw
files, the model artifact and selection file. Comparisons use original columns
and hash complete rows inside Databricks; no original listing rows are exported.

The original frozen tag object, source files and Job settings also match their
pre-run values; see [frozen_state_unchanged.json](frozen_state_unchanged.json).
Only new Venice inputs, its table slices and its validation audit row were added.

Evidence includes the sealed request/submission, first terminal run, status
transitions, four task outputs, actual task Git snapshots, original input hashes,
validation record, source header read after execution, aggregate quality summary,
and SQL statement IDs. [Preparation/reporting events](preparation_events.jsonl)
separately record the API page-limit issue, successful-grant result parsing issue,
SDK endpoint warning and local reporting import collision. Those occurred outside
frozen ETL, did not clean source data, and caused no ETL retry or repair.

## Stop and team handoff

**No fixes applied. No model scoring performed. Venice predictions: zero.**
There is no Venice MAE yet; ETL success does not establish model transfer quality.
Nazar can next run the unchanged `price-v1` scorer from M1 with `cities=venice`,
`snapshot_date=2026-09-16` and the exact same `sources_config_path`. Preserve that
first model result separately before considering any changes.

[Change ledger](change_ledger.json) is empty for both pipeline fixes and model
changes. Any later change needs its own revision/run and must reference this
first-run ID; it must not replace these artifacts or be described as the first run.
