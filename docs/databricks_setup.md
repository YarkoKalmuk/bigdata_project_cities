# First milestone: Milan and Florence in bronze

> Historical setup/integration instructions below. Current delivery status is in
> [README](../README.md), [reproducibility](reproducibility.md) and the
> [Week 2 engineering handoff](week2/handoff_dashboard_genie_engineering.md).
> M1 and the first Venice ETL/model runs are complete. Do not rerun setup,
> registration, ETL or training to reproduce report numbers. Contracts below remain
> useful; earlier pending-status statements do not describe the current release.

Status: Yaropolk reports running setup, ingestion and initial silver in Databricks. Maksym's EDA provides both snapshot URLs and observed counts in `docs/eda_handoff.md`. This review did not download city data.

## 1. Get this branch into Databricks

After the branch is committed and pushed to GitHub, open the Databricks Git dialog, fetch/pull updates and select `yaropolk/feature1-setup`. You should see `config`, `docs` and `notebooks`. Git does not synchronise uncommitted local files.

Use Databricks Free Edition serverless compute. Each collaborator should use their own Git folder/branch. Agree on workspace access and table permissions without sharing passwords; if separate workspaces are required, each person can rerun the same setup and ingestion.

## 2. Create storage

Open `notebooks/00_setup` in Databricks. Set the `catalog` widget to an existing catalog where you have permission to create schemas and volumes (default: `workspace`). Run all cells.

The notebook creates:

- `<catalog>.airbnb_bronze`: raw-file volume, raw string listings and ingestion manifest.
- `<catalog>.airbnb_silver`: reserved for typed listings after EDA.
- `<catalog>.airbnb_gold`: reserved for metrics, features and predictions.

If permission is denied, select a writable catalog or ask the workspace owner to grant access. Do not switch to a paid trial to resolve permissions.

## 3. Obtain only the two training snapshots

Use [Inside Airbnb's download page](https://insideairbnb.com/get-the-data/) and locate **Milan** and **Florence** only. Choose the detailed `listings.csv.gz`, not the summary `listings.csv`. Record the exact dated download link for each file. Data attribution: Inside Airbnb, CC BY 4.0.

Both dates and URLs are recorded from the completed A/B EDA in config. A blank source URL widget falls back to config; a blank source path derives the expected upload path. Existing widget values persist: clear Milan's old values before running Florence. Preserve the recorded snapshots rather than replacing them mid-experiment.

Do not open, download or profile Venice. Its first run belongs after the Week 1 pipeline and model freeze.

Download the two files into separate local directories under ignored `data/`. In Catalog Explorer, find the `airbnb_bronze.raw_files` volume and upload each original compressed file into this layout:

```text
/Volumes/<catalog>/airbnb_bronze/raw_files/milan/<YYYY-MM-DD>/listings.csv.gz
/Volumes/<catalog>/airbnb_bronze/raw_files/florence/<YYYY-MM-DD>/listings.csv.gz
```

Keep these raw files unchanged. Uploading original files preserves bronze provenance and avoids reliance on outbound downloads from serverless compute.

## 4. Ingest each city with the same notebook

Open `notebooks/01_ingest_bronze`, set widgets and run all cells:

| Widget | Value |
|---|---|
| `catalog` | The same catalog used in setup |
| `city` | `milan`, then `florence` in the second run |
| `snapshot_date` | Verified ISO date matching config and README |
| `source_path` | Exact volume path above |
| `source_url` | Exact dated Inside Airbnb detailed-file URL |

The notebook preserves all source columns as strings, adds `_city`, `_snapshot_date`, `_source_path`, `_source_url` and `_ingested_at`, and writes `<catalog>.airbnb_bronze.listings`. It checks required columns, nonempty data, unique/nonmissing IDs and stored row counts. Optional missing/extra string columns are tolerated through additive schema evolution; missing required fields fail visibly.

Rerunning replaces only the selected city/date. Run cities sequentially for this milestone. If the audit step fails after writing listings, the notebook run is not complete: rerun after resolving the error to reconcile the manifest. Do not manually append the file again.

## 5. Verify and hand off

Run this in a SQL cell, replacing `<catalog>`:

```sql
SELECT _city, _snapshot_date, COUNT(*) AS listings,
       COUNT(DISTINCT id) AS distinct_listing_ids
FROM <catalog>.airbnb_bronze.listings
GROUP BY _city, _snapshot_date;

SELECT * FROM <catalog>.airbnb_bronze.ingestion_manifest;
```

Require one row per uploaded city/snapshot, positive counts and equal listing/distinct-ID counts. Rerun Milan and confirm neither city's counts change. Check several descriptions containing newlines/quotes in the notebook and confirm that `price` remains a source string. Do not treat successful parsing as completed EDA.

Give Nazar and Maksym the catalog/table names, manifest row counts, snapshot dates, source links and notebook run instructions. They can start EDA and leakage review on bronze while silver rules are agreed.

If teammates cannot query the shared catalog, resolve access or reproduce the setup in their workspaces before assuming the handoff is complete.

## Next feature branches

- `yaropolk/feature2-silver`: implement EDA-agreed typing, price parsing, quality flags and exclusion reasons.
- `yaropolk/feature3-pipeline`: orchestrate bronze/silver/gold through a parameterised Databricks Job, then test reproducibility.
- Add the Week 1 freeze and Venice run log only when the team reaches that milestone.

Commit working notebook changes in Databricks and push them. Pull here before editing the same files locally; commit and push local changes before pulling them into Databricks.

References: [Git folders](https://docs.databricks.com/aws/en/repos/git-operations-with-repos/), [volume files](https://docs.databricks.com/aws/en/volumes/volume-files), [CSV options](https://docs.databricks.com/aws/en/spark/api-options).
