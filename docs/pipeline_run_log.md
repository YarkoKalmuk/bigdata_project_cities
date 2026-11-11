# Pipeline execution evidence

No automated Job runs have been verified by this implementation. Replace pending cells only after observing actual Databricks runs. Manual notebook success does not imply that the multi-task Job has passed.

| Run | City/date | Job/run URL | Resolved Git SHA | Bronze/silver/features rows | Analytical rows | Result |
|---|---|---|---|---|---|---|
| Initial Milan | milan / 2026-09-19 | pending | pending | pending | pending | pending |
| Initial Florence | florence / 2026-09-19 | pending | pending | pending | pending | pending |
| Idempotency rerun | milan / 2026-09-19 | pending | pending | pending | pending | pending |

For the rerun, record Florence's counts before and after, as well as Milan's. Add failures with their task, error, fix and rerun link rather than replacing failure history with a successful run. Successful counts are also stored in `airbnb_gold.pipeline_validations` under the selected catalog.

Week 1 freeze: **pending**. Model revision and evaluation: **pending Nazar's handoff**. Venice has not been run or explored by this implementation.
