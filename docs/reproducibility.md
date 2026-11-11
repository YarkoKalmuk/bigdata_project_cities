# Reproducibility and preserved results

## Default: inspect and verify without rerunning the experiment

1. Fetch repository refs and tags. `M1-freeze` resolves to
   `7f76cbe6936e76fa3a7685ac90b40c1ce1c253df`; inspect it in a separate clone or
   detached checkout. Do not move the tag or edit frozen modules/configuration.
2. Follow [the freeze record](week1_freeze.md) for artifact hashes, A/B MAE,
   original table versions and immutable Job source. The Job uses executable
   commit `f408ac01ffdd025fab6df220c8f89b24d3d4fda6`, byte-identical to M1 for
   pipeline/model files. A/B and Venice inputs use EUR despite `$` formatting.
3. Verify preserved first-run indexes locally: SHA-256 each indexed file's
   committed **LF bytes**, not a Windows worktree conversion. ETL has 25 indexed
   files and the model has 34. Neither indexed directory is edited by this
   documentation integration. `docs/week2/integration_review.json` records this
   review's checks and the source PR heads.
4. With Python 3.12 and Java 21, run the synthetic suite in an isolated environment:

   ```sh
   python3 -m venv .venv
   .venv/bin/python -m pip install -r requirements-test.txt
   SPARK_LOCAL_IP=127.0.0.1 .venv/bin/python -m unittest discover -s tests -v
   ```

   The suite fits synthetic fixtures only. It does not retrain `price-v1`, submit
   Databricks Jobs or access the real Venice inputs.
5. For read-only metric reproduction, use the SELECT queries in Nazar's
   [model/BI handoff](week2/handoff_dashboard_genie_model.md). Filter `price-v1`,
   correct snapshots and evaluation splits. Recompute MAE from stored rows;
   do not invoke notebook 08 or any Job just to reproduce a report number.

## Preserved inputs and execution lineage

| Input / stage | Authoritative reference |
|---|---|
| Milan / Florence | `config/sources.json`, snapshots 2026-09-19; original detailed `listings.csv.gz` in the raw volume |
| Venice | `runtime/venice-2026-09-16-first-run.json`, snapshot 2026-09-16; original gzip hash in the first ETL report |
| Runtime manifest | `/Volumes/workspace/airbnb_bronze/raw_files/config/venice-2026-09-16-first-run.json` |
| ETL Job | `816607442908043`; `jobs/airbnb_etl.job.json`, immutable source commit |
| First Venice ETL | `782550938914199`, four successful tasks; 8,844 rows retained |
| First Venice scorer | `65362888524059`, frozen tag/model, 8,844 predictions; 8,144 evaluated |
| Model / scorer / baseline | `price-v1` / `score-v1` / `airbnb-v1` |
| Artifact | `/Volumes/workspace/airbnb_gold/model_artifacts/price-v1/model.joblib`; owner-provided artifact must match the frozen hash |
| Last recorded post-scoring versions | `model_features` 5, `predictions` 3; split/baseline/artifact/evaluation 0, per Nazar's 2026-11-11 audit |

Version history is chronology, not a contradiction: features were v2 at training,
v4 after freeze acceptance and v5 after Venice ETL; predictions were v1 after A/B,
v2 after content-preserving OPTIMIZE and v3 after the first Venice append. A/B
contents and frozen references were checked unchanged. Do not rewrite either
first-run directory to make its historical versions match a later table version.

## Flow for a separately authorised rebuild

The notebook sequence is `00_setup` → `01_ingest_bronze` → `02_prepare_silver` →
`03_build_gold` → `04_validate_pipeline`. Run one configured city/snapshot at a
time using the existing Job; do not register a duplicate Job through 05.
Notebook 06 creates the original persisted A/B split/baseline, 07 is the historical
training/selection/evaluation entry point, and 08 is the frozen-artifact scorer.
These are lineage instructions, **not** approval to execute them again now.

Any future rebuild belongs in an isolated catalog/workspace after separate
authorisation, using original inputs and an authorised copy of the preserved
artifact. Do not rerun 06/07 against frozen references, overwrite artifacts,
repair/rescore the first Venice run or create a substitute model to bypass a
missing-file/access error. Coordinate missing access with the securable owner.

## Review and delivery boundary

No new live verification was performed for this documentation pass. Runtime
results are attributed to the preserved ETL/model reports and Nazar's read-only
audit; local evidence hashes and arithmetic are checked again. See
[integration review](week2/integration_review.md) for PR order and remaining
Dashboard/Genie/presentation acceptance, and [plan.md](../plan.md) for owners.
