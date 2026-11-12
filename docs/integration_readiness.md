# Integrated A/B system: review before the Week 1 freeze

> Historical setup/integration instructions below. Current delivery status is in
> [README](../README.md), [reproducibility](reproducibility.md) and the
> [Week 2 engineering handoff](week2/handoff_dashboard_genie_engineering.md).
> M1 and the first Venice ETL/model runs are complete. Do not rerun setup,
> registration, ETL or training to reproduce report numbers. Contracts below remain
> useful; earlier pending-status statements do not describe the current release.

Historical integration procedure. PR #3 has been merged into main, and live A/B
verification has now passed. See [the M1 freeze record](week1_freeze.md) for the
current release state, actual Job identity and executed verification evidence.

Status: **integration candidate, not frozen**. No freeze tag, workspace change, model retraining or unseen-city run was performed by this integration.

The latest requirement audit and proposed PR merge order are in
[Week 1 repository review](week1_repository_review.md). Merge, freeze and live
Job deployment remain separate actions requiring explicit approval.

## Integrated source

- Engineering: `yaropolk/feature5-city-inputs` at `7ddaa74`, including Maksym's EDA.
- Model: `nazar/model-baseline` at `f8e0eba`, preserving the original commits/authorship.
- Candidate: `yaropolk/feature6-integration`, prepared for review against `main`.
- `airbnb/model.py`, `price_model.py`, `scoring.py` are unchanged from Nazar's branch. Silver/gold transformations and repository source metadata are unchanged from feature 5.
- The only scoring behaviour change is input resolution in notebook 08: it now accepts the same `sources_config_path` as ETL and records its canonical JSON hash. Model identity, features, artifact, split, baseline, predictions schema and metrics are unchanged.

The repository ETL Job definition pins immutable executable integration commit `f408ac01ffdd025fab6df220c8f89b24d3d4fda6` through `git_commit`; no moving branch or tag is used. This deliberate pin avoids a self-referential commit hash: the current follow-up changes affect only Job settings, tests and documentation, not the task code at the pinned revision. It is not a final freeze. The graph still has four tasks; scorer 08 is separate. No live Job configuration was changed.

## Local validation

Combined suite after repository corrections: **100 tests passed, zero failures, zero skips**. Includes the immutable Job-source regression check. Synthetic inputs only; no city files or Databricks artifact was downloaded.

Python 3.12, Java 21, PySpark 4.0.1, scikit-learn 1.7.2, numpy 2.3.4, pandas 2.3.3, joblib 1.5.2; local SciPy 1.16.3. Dependencies are in `requirements-test.txt`. A broken inherited SciPy binary was replaced only inside the temporary test environment before the passing run.

Reproduce locally in a fresh virtual environment with Java 21 available:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-test.txt
SPARK_LOCAL_IP=127.0.0.1 .venv/bin/python -m unittest discover -s tests -v
```

The explicit `tests` package supports Nazar's shared synthetic fixtures. The new regression test executes scorer 08's parameter cell against a synthetic runtime manifest; no artifact read, scoring or publication occurs in that test.

## Evidence still to reconcile

Live verification was attempted locally using the existing `yaropolk` Databricks CLI profile. Its refresh token is invalid; `databricks current-user me` could not authenticate. Reauthenticate normally with `databricks auth login --profile yaropolk` before retrying CLI checks. No credentials were read or copied, and no workspace object was changed. Notebook 09 remains an alternative from an already authenticated Databricks workspace.

Yaropolk's feature 5 log has successful Milan run `1103284242992113` and Florence run `942670770239305`, but the resolved Git SHA, repeatability and external-manifest run fields remain TODOs. His report says all checks were run; exact run evidence still needs recording, not reclassification as a failure.

Nazar's historical [integration check](week1_integration_check.md) did not find persistent Job `721102111883860` in the shared workspace. The shared ETL reference runs are submit runs `399786082243961`, `334832161613071` and `768192587578562`, now recorded separately in [the pipeline log](pipeline_run_log.md). The shared host is documented in [the baseline evidence](model_baseline_run.md). The persistent-Job IDs remain separate reported history; their location is not inferred from that discrepancy.

## Next workspace action: read-only readiness check

1. Pull/select `yaropolk/feature6-integration` in the workspace holding Nazar's `price-v1` model and reference tables. Use the recorded serverless environment 6 with scikit-learn 1.7.2.
2. Run `09_check_week1_readiness`. Set `catalog` appropriately. Optionally set `job_id` to `721102111883860` **only if checking that Job in this workspace**; an inaccessible Job fails visibly rather than being treated as present.
3. Commit the returned report with the workspace host, actual table versions, artifact hash, fingerprints, reconciliation and MAE. The notebook only reads A/B reference state; it does not create a freeze or prove that an external-manifest ETL run happened.
4. Record the missing feature 5 run IDs, source manifest path/hash and actual Git revisions from Job history / `pipeline_validations` in the run log.

Do not recreate, train or overwrite the model to pass readiness. Missing tables/artifacts indicate a workspace/access issue to resolve with Nazar.

## Integrated scorer acceptance

After read-only checks pass, test the changed scorer entry point using A/B only, preferably with Nazar in the workspace holding the original artifacts:

- `cities=milan,florence`, `model_version=price-v1`, `code_revision=<actual integrated Git SHA>`.
- `sources_config_path=<the immutable copied A/B manifest tested with ETL>`.
- `output_table=integration_check_predictions`, keeping the existing official `predictions` untouched.
- Supply a real `scoring_run_id` (or use its generated manual identifier).

Notebook 08 verifies artifact/reference hashes before scoring and checks official held-out metrics. It writes only the named validation output table. Record the run's source revision and manifest hash. This acceptance is not a new model choice or a new official MAE.

Reported model candidate metrics, from Nazar's existing records:

| Group | Test listings | Baseline MAE (EUR) | Model MAE (EUR) |
|---|---|---|---|
| Milan | 4,399 | 94.38 | 75.72 |
| Florence | 2,464 | 97.41 | 76.18 |
| Both | 6,863 | 95.47 | 75.88 |

These are historical candidate results, not newly observed workspace results from this local integration. Exact hashes and versions are in [the model candidate](model_freeze_candidate.md).

## Freeze gate

Only after acceptance: integrate the reviewed candidate into `main`; record a full-system immutable SHA/tag, Job settings, workspace, raw/source metadata hashes, feature/split/baseline versions and model artifact; pin the live Job to that exact Git revision. Record access and the scorer invocation. The freeze gate remains open until this is done.

For the first unseen-city run, leave code and model pinned and supply runtime metadata/data only. Pass the same manifest to ETL and scorer. Preserve the first outcome before fixes. Do not add the test city to repository config or explore it now.
