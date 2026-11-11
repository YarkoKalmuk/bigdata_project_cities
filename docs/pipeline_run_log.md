# Databricks ETL Pipeline Run Log

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

