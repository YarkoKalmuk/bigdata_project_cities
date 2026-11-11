# Run the parameterised ETL Job

Current branch: `yaropolk/feature5-city-inputs`. Feature 4 Job creation/execution succeeded according to the run log. Feature 5 still needs workspace validation. No live Job setting changes merely by pulling this branch.

## Update the existing Job for feature 5

Do not rerun registration or create a duplicate Job. Open `airbnb-cities-etl` (ID `721102111883860`) and change its **remote Git branch** to `yaropolk/feature5-city-inputs`. Add the Job parameter `sources_config_path` with an empty default. Leave the four tasks, existing catalog/date/source parameters and concurrency setting unchanged. Select/pull the same branch in your workspace Git folder for interactive notebook work; this is separate from the Job's Git setting.

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

Once the full A/B system is ready, record an immutable Git revision and model artifacts and configure the Job to that Git **commit**, rather than a moving feature branch. Preserve that exact definition for the first Venice run. Do not freeze now or run Venice yet.

References: [Job parameters](https://docs.databricks.com/aws/en/jobs/job-parameters), [remote Git Jobs](https://docs.databricks.com/aws/en/jobs/git), [serverless Jobs](https://docs.databricks.com/aws/en/jobs/run-serverless-jobs).
