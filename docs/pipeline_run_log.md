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

Previously verified Silver counts:

- Milan: 25,338 listings
- Florence: 13,571 listings

**Post-repeat row-count verification:** Pending  
**Duplicate listing-key check:** Pending

## Additional Notes

The Job used the `workspace` catalog and the snapshot date `2026-09-19` for both cities.

The `source_path` and `source_url` Job parameters were left empty. All three runs completed successfully.

## Conclusion

The automated pipeline executed successfully for both training cities and completed a repeated Milan run. Final confirmation of idempotency requires checking that row counts remain unchanged and that duplicate listing keys are absent.