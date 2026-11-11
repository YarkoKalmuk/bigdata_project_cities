# Venice input and unchanged first-run procedure

This procedure uses the published `M1-freeze` code and existing Job
`816607442908043`, pinned to executable commit
`f408ac01ffdd025fab6df220c8f89b24d3d4fda6`. Its task code matches freeze commit
`7f76cbe6936e76fa3a7685ac90b40c1ce1c253df`. Do not edit notebooks, shared Python
modules, the frozen tag, Job source, or the original A/B inputs.

## Input selection

At preparation, [Inside Airbnb's download page](https://insideairbnb.com/get-the-data/)
lists Venice's latest detailed snapshot as **16 September 2026**:

<https://data.insideairbnb.com/italy/veneto/venice/2026-09-16/data/listings.csv.gz>

Use **Detailed Listings**, not the summary `listings.csv`. Data attribution:
Inside Airbnb, CC BY 4.0. Save the original gzip file unchanged; do not decompress,
clean or profile it before the first frozen pipeline attempt. Record download
time, URL, byte count and SHA-256.

Runtime metadata is in
[`runtime/venice-2026-09-16-first-run.json`](../../runtime/venice-2026-09-16-first-run.json).
It does not modify the A/B-only `config/sources.json`. The centre is the published
Piazza San Marco coordinate, 45°26′2″N / 12°20′17″E, converted to decimal degrees
from [Wikidata Q217527](https://www.wikidata.org/wiki/Q217527). This geographic
reference is selected before dataset inspection and will not be tuned after
observing prices or predictions.

## Download and upload

1. Download that exact URL to ignored local storage, e.g.
   `data/venice/2026-09-16/listings.csv.gz`. Never commit the dataset to Git.
2. In Catalog Explorer, open `workspace.airbnb_bronze.raw_files` and upload the
   original file to:

   ```text
   /Volumes/workspace/airbnb_bronze/raw_files/venice/2026-09-16/listings.csv.gz
   ```

3. Upload the runtime JSON, unchanged, to:

   ```text
   /Volumes/workspace/airbnb_bronze/raw_files/config/venice-2026-09-16-first-run.json
   ```

The volume must grant upload permission to the uploader. Any access provisioning
is input preparation, not an excuse to change the frozen ETL. The automated
intake uses exclusive local creation and remote `overwrite=False`; it must stop
if an input already exists rather than replacing it. Record both file-byte and
canonical-JSON manifest hashes.

## First run, exactly once

Before starting, check that no earlier Venice run or output exists; if it does,
preserve and investigate it instead of presenting a rerun as the first attempt.
Record the Job definition, frozen revision and A/B content fingerprints.

Run the **existing unchanged Job** with these overrides:

| Parameter | Value |
|---|---|
| `catalog` | `workspace` |
| `city` | `venice` |
| `snapshot_date` | `2026-09-16` |
| `source_path` | leave empty; derives the Venice volume path |
| `source_url` | leave empty; uses the runtime manifest |
| `sources_config_path` | `/Volumes/workspace/airbnb_bronze/raw_files/config/venice-2026-09-16-first-run.json` |

There must be zero automatic task retries. Do not click Repair or Run Again.
Capture the parent/task run IDs, state, errors, notebook exit output and actual
task Git snapshots. Preserve partial Bronze/Silver/Gold outputs on failure.
Databricks retains the original task logs/rendered results; keep their run links
alongside the API status/output capture.

After that attempt, inspect only the outputs it produced for counts, schema and
quality differences. Compare A/B fingerprints using their original columns so
additive Venice schema fields do not hide or manufacture row changes. Record
the model artifact and predictions fingerprints too.

## Stop boundary

Stop after first-run evidence and quality profiling. No retries, input cleaning,
pipeline repairs, model training, scoring or model changes are part of this step.
Nazar's unchanged-model Venice evaluation remains a separate task using the same
manifest and frozen scorer. Do not invent a Venice MAE from ETL-only results.

Classify any later work in a separate ledger as a **pipeline fix** or **model
change**, referencing this first run. Do not overwrite its evidence with repaired
outputs or describe ordinary observed distribution differences as applied fixes.
