# Run the parameterised ETL Job

> Historical setup/integration instructions below. Current delivery status is in
> [README](../README.md), [reproducibility](reproducibility.md) and the
> [Week 2 engineering handoff](week2/handoff_dashboard_genie_engineering.md).
> M1 and the first Venice ETL/model runs are complete. Do not rerun setup,
> registration, ETL or training to reproduce report numbers. Contracts below remain
> useful; earlier pending-status statements do not describe the current release.

Current review branch: `yaropolk/feature6-integration` (PR #3). The Job settings file pins `git_commit: f408ac01ffdd025fab6df220c8f89b24d3d4fda6`, an existing integration revision containing the runtime city interface and model entry points. No moving branch is used. The pin is a repository fix, not a freeze or live Job update. See [the run log](pipeline_run_log.md) for shared submit runs and separate reported persistent-Job history.

## Update the existing Job for feature 5

Do not rerun registration or create a duplicate Job. Before any deployment, confirm the correct shared workspace and Job identity: the shared reference runs were one-time submissions, and persistent Job `721102111883860` was not found in Nazar's workspace check. After explicit approval, apply the repository's immutable Git **commit** source and the `sources_config_path` parameter to the intended Job. Do not substitute a feature branch. Selecting/pulling a workspace Git folder is separate from configuring the Job's source.

Run Milan, Florence and a Milan repeat with blank `sources_config_path` to verify the repository defaults. Record new run IDs/SHAs separately from feature 4's evidence. Notebook 04 adds the input manifest's canonical JSON SHA-256 to successful validation records through additive schema evolution.

## Register once

1. In Databricks select this Git branch and pull. Setup notebook 00 must already have run, with the original Milan and Florence files uploaded to the volume.
2. Open and run `notebooks/05_create_etl_job`. It reads `jobs/airbnb_etl.job.json`, authenticates through your Databricks session and registers `airbnb-cities-etl`. It does not run the Job. If the SDK import is unavailable, add `databricks-sdk` through the notebook's environment dependencies and restart Python.
3. Find the Job under **Jobs & Pipelines**. Check GitHub credentials, the repository URL and branch, four notebook tasks, serverless compute, and maximum concurrent runs = 1.

The creation notebook refuses to overwrite a same-name Job. If one exists, inspect its tasks and Git source in the UI rather than creating duplicates. This JSON is a Jobs API settings document, not a bundle YAML file. Advanced users can register the same file with the Jobs API or CLI; the notebook is the recommended route here.

Tasks use the remote Git source, not your editable workspace notebook copies. Commit and push changes before rerunning. Each run records its resolved Git snapshot in Job history. Do not switch the Job to `main` while main still lacks these notebooks.

## Run the same Job for each city

Use **Run now with different parameters**. Job parameters are automatically passed to notebook widgets; do not add city-specific task copies or hardcode paths.

| Parameter | Milan run | Florence run |
|---|---|---|
| `catalog` | `workspace`, or your writable catalog | same catalog |
| `city` | `milan` | `florence` |
| `snapshot_date` | `2026-09-19` | `2026-09-19` |
| `source_path` | leave empty to derive the configured volume path | leave empty |
| `source_url` | leave empty to use recorded config URL | leave empty |
| `sources_config_path` | leave empty to use repo config | leave empty |

Graph: **bronze → silver → gold → validate**. Only one task runs at a time. A failure prevents downstream tasks from running. There is no automatic schedule or automatic retry; errors remain visible. Runs are queued when this Job is already active. Avoid manually running the same writers alongside it: the concurrency limit applies to this Job only.

## Acceptance and evidence

1. Run Milan and require all four tasks to succeed.
2. Run Florence and require all four tasks to succeed.
3. Rerun Milan with identical parameters. Check both cities' counts before and after: there must be no added listings or changes to Florence's counts.
4. Record real run links, resolved Git SHA, counts and result in [the run log](pipeline_run_log.md). EDA reference counts are Milan 25,338 / Florence 13,571 when using the same files; they are not substitutes for Job run evidence.

Validation checks bronze/manifest/silver counts, silver keys and price classes, full model-input rows against the allowlist and silver, city analytical-population counts, room-type count/share totals, neighbourhood totals and low-sample median suppression. Successful validation appends evidence to `<catalog>.airbnb_gold.pipeline_validations`. This is an attempt log; manual/repair repeats can append another successful record for a run. It does not claim model accuracy or verify every aggregate value.

Failed tasks remain in Job history. A run that never reaches validation does not get a success record. Outputs from earlier successful tasks may remain: the pipeline is not a multi-table transaction. Fix the cause, commit/push if code changed, and rerun the entire city Job before announcing the outputs as ready. Preserve the failed run URL.

## Finish Week 1 before freezing

After the acceptance runs, give Maksym the metric table locations and give Nazar `model_features` plus its contract. Do not create fake predictions; Nazar must publish those from evaluated model artifacts.

Feature 5 resolves configured cities generically: a new city's metadata can be supplied using a JSON manifest under `/Volumes/<catalog>/airbnb_bronze/raw_files/config/`. This avoids editing frozen code or moving the Job's pinned revision. See the [input contract](engineering_handoff.md). The runtime-manifest route is locally tested with synthetic input; it still needs an A/B workspace check before freezing. Wait for Nazar's baseline, held-out results and scoring entry point too.

Once the full A/B system is ready and the team explicitly approves the freeze, record the final integrated Git revision and model artifacts, then approve deployment of that exact commit to the intended Job. The current repository pin is an integration-code pin, not that approval. Preserve the approved definition for the first unseen-city run. Do not freeze or access the test city yet.

References: [Job parameters](https://docs.databricks.com/aws/en/jobs/job-parameters), [remote Git Jobs](https://docs.databricks.com/aws/en/jobs/git), [serverless Jobs](https://docs.databricks.com/aws/en/jobs/run-serverless-jobs).
