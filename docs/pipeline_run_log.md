# Databricks ETL Pipeline Run Log

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

