# Databricks ETL Pipeline Run Log

## Executed Week 1 freeze verification

Live verification on 2026-09-19 A/B snapshots passed all 24 integration checks, including
counts, model coverage, reference fingerprints, server-side file hashes and
held-out MAE reproduction. The Jobs API confirmed the three shared submit runs
below succeeded. See [freeze evidence](week1_freeze_verification.json).

No persistent ETL Job existed in the shared workspace. The approved immutable
definition was registered as **816607442908043**, pinned to
`f408ac01ffdd025fab6df220c8f89b24d3d4fda6`, without an automatic schedule.
Explicit A/B acceptance runs are recorded separately after their completion.
This replaces the earlier Job ID as the current shared-workspace Job identity;
historical run IDs below are retained with their original provenance.

The verification read data and hashed files inside Databricks. A/B Job acceptance
refreshes only ETL outputs; no model/prediction data is modified. Generic city input compatibility
passed synthetic ETL/scorer tests; the older feature 5 external-manifest run TODOs
are not newly certified. The authoritative current milestone is
[M1 freeze](week1_freeze.md).

New registered-Job acceptance runs completed successfully, with all four tasks
successful under immutable Git source `f408ac01ffdd025fab6df220c8f89b24d3d4fda6`:

| City | Run ID | Result |
|---|---|---|
| Milan | 27941700122958 | SUCCESS |
| Florence | 367666271706452 | SUCCESS |

Post-run checks passed again: Bronze/Silver/feature/metric Delta versions are
**4**, counts remain 25,338 / 13,571, and model/reference table versions remain
**0**. Predictions reached Delta **2** through `OPTIMIZE`; all 25 columns are
row-identical to version **1** (zero differences). A/B MAE and artifact/reference
hashes remain unchanged. The full local suite passed again (100 tests, no skips).

## Shared-workspace Week 1 reference runs

These are the shared-workspace runs requested by Nazar and recorded in
[the baseline run evidence](model_baseline_run.md#pipeline-runs-one-time-multi-task-runs-same-task-graph-as-jobsairbnb_etljobjson).
They are the reference ETL runs behind his A/B model inputs, not feature 5 tests.

- Workspace: `https://dbc-1766f78b-980d.cloud.databricks.com`, workspace ID `7474659920821008`.
- Date: 2026-11-11; Free Edition serverless; snapshot date: 2026-09-19.
- Pipeline revision: `504278b`, pinned at execution according to Nazar's evidence.
- Invocation: one-time `jobs submit` runs, not executions of persistent Job `721102111883860`.

| City | Shared-workspace run ID | Tasks | Recorded result |
|---|---|---|---|
| Milan | 399786082243961 | bronze → silver → gold → validate | SUCCESS |
| Florence | 334832161613071 | bronze → silver → gold → validate | SUCCESS |
| Milan rerun | 768192587578562 | bronze → silver → gold → validate | SUCCESS |

Nazar's evidence records identical before/after reconciliation for the Milan rerun:
Milan 25,338 listings and Florence 13,571, with complete gold feature coverage.
These facts are carried from the committed run evidence and the team's supplied IDs;
no Databricks query or rerun was performed for this repository correction.

The current repository Job definition is pinned to integration code commit
`f408ac01ffdd025fab6df220c8f89b24d3d4fda6`. That pin is not a new run, a live Job
configuration update, or the final Week 1 freeze. Newer feature 5 acceptance details
remain as recorded below and must not be attributed to the reference runs above.

## Earlier Yaropolk-reported persistent-Job history

The following Job/run IDs are retained as separate reported history. Nazar's shared
workspace check did not find this persistent Job there; these IDs must not be used
in place of the shared-workspace reference runs above.

**Job:** airbnb-cities-etl  
**Job ID:** 721102111883860  
**Execution date:** November 11, 2026  
**Compute:** Databricks Serverless

## Automated Pipeline Runs

| City | Run ID | Duration | Status |
|---|---|---|---|
| Milan | 456920958407795 | 2m 40s | Succeeded |
| Florence | 471517583759997 | 1m 48s | Succeeded |
| Milan (repeat) | 1039839162011700 | 1m 47s | Succeeded |

All three executions completed successfully using the same parameterized Databricks Job.

The Job executes four tasks in sequence:

Bronze → Silver → Gold → Validation

## Row Count Verification

Post-repeat SQL results supplied by Yaropolk:

| City | Snapshot | Rows | Distinct listing IDs |
|---|---|---|---|
| Milan | 2026-09-19 | 25,338 | 25,338 |
| Florence | 2026-09-19 | 13,571 | 13,571 |

The counts match the previously recorded totals; no duplicate listing IDs exist
within either city/snapshot. Resolved Git SHAs and workspace run URLs still need
to be copied from Job history; they were not supplied with these SQL results.

## Additional Notes

The Job used the `workspace` catalog and the snapshot date `2026-09-19` for both cities.

The `source_path` and `source_url` Job parameters were left empty. All three runs completed successfully.

## Conclusion

The feature 4 Job executed successfully for both training cities and a repeated
Milan run. The reported post-repeat counts and unique keys support repeatability.
Feature 5 introduces runtime input manifests and still requires new A/B acceptance
runs; do not attribute the feature 4 run IDs above to the new implementation.


## Feature 5 — Databricks verification

Job ID: 721102111883860
Date: 2026-11-11

| City | Run ID | Duration | Status |
|---|---|---|---|
| Milan | 1103284242992113 | 2m 30s | Succeeded |
| Florence | 942670770239305 | 1m 46s | Succeeded |

Both executions completed successfully.

Git revision: TODO — confirm Feature 5 branch
sources_config_path: TODO — confirm Job parameter
Repeatability test: TODO
External manifest test: TODO

