# A/B baseline run evidence (MODEL-02 / MODEL-03)

Owner: Mykolaichuk Nazar. Recorded 2026-11-11 (times below are UTC). Every number here was read
from Databricks run output or from SQL on the persisted tables; none was edited by hand.
Venice was not downloaded, configured, queried or run.

## Environment

| Item | Value |
|---|---|
| Workspace | Shared team workspace `dbc-1766f78b-980d.cloud.databricks.com` (workspace id 7474659920821008), Free Edition, serverless |
| Catalog / schemas | `workspace` / `airbnb_bronze`, `airbnb_silver`, `airbnb_gold` (created by `00_setup` in this run; they did not exist before) |
| Raw files | `/Volumes/workspace/airbnb_bronze/raw_files/{milan,florence}/2026-09-19/listings.csv.gz`, uploaded unchanged from the URLs in `config/sources.json` |
| Raw file SHA-256 | Milan `23f51e357f0a779522ca4bdb5fb6fc1f7f98aa93c2711200085c813721368bd3` (14,955,780 B); Florence `a3392ba7e26760536ee6c399f15c550625276cecd618483ae07af16a93c3f0a1` (7,989,275 B) |
| Snapshot dates | Milan 2026-09-19, Florence 2026-09-19 (match `config/sources.json` and `README.md`) |
| Pipeline code | `yaropolk/feature4-pipeline` @ `504278b` (feature3 `d67faa9` + validation task), Git source pinned to that commit |
| Baseline code | `nazar/model-baseline` @ `f3d080b`, `notebooks/06_baseline_eval.py`, run from an exact `git archive` of that commit imported to the workspace |

## Pipeline runs (one-time multi-task runs, same task graph as `jobs/airbnb_etl.job.json`)

| Run | City | Run ID | Tasks | Result |
|---|---|---|---|---|
| Setup | – | 819595896633506 | `00_setup` | SUCCESS |
| Initial Milan | milan | 399786082243961 | bronze → silver → gold → validate | SUCCESS |
| Initial Florence | florence | 334832161613071 | bronze → silver → gold → validate | SUCCESS |
| Idempotency rerun | milan | 768192587578562 | bronze → silver → gold → validate | SUCCESS |

The persistent Job `airbnb-cities-etl` was not registered (Yaropolk's `05_create_etl_job`); these
are `jobs submit` runs and appear in the workspace run history.

### Reconciliation (identical before and after the Milan rerun)

| Layer | Milan rows / distinct keys | Florence rows / distinct keys |
|---|---|---|
| Bronze `listings` (distinct `id`) | 25,338 / 25,338 | 13,571 / 13,571 |
| Bronze `ingestion_manifest.row_count` | 25,338 (1 row) | 13,571 (1 row) |
| Silver `listings` (distinct `(city, snapshot_date, listing_id)`) | 25,338 / 25,338 | 13,571 / 13,571 |
| Gold `model_features` | 25,338 / 25,338 | 13,571 / 13,571 |
| Gold `city_metrics` listings / priced listings | 25,338 / 21,522 | 13,571 / 12,086 |

The only change from the rerun is a second Milan row in the append-only audit
`airbnb_gold.pipeline_validations`, by design. `model_features` equals silver on
`price_eur` and `eligible_for_training` for every key (0 differences). Counts match the EDA reference.

### Target and eligibility checks (silver)

| Check | Milan | Florence |
|---|---|---|
| Missing raw price | 3,684 | 1,423 |
| Raw price present but `price_eur` null | 0 | 0 |
| `price_eur` differs from the parsed raw string | 0 | 0 |
| `price_eur` ≤ 0 | 0 | 0 |
| `price_eur` min / median / max | 14.10 / 163.67 / 88,100 | 11.40 / 198.00 / 17,430 |
| `eligible_for_training` true / false / null | 21,654 / 3,684 / 0 | 12,148 / 1,423 / 0 |
| Rows where eligibility ≠ "valid id and positive price" | 0 | 0 |

`eligible_for_training` is defined in `airbnb/silver.py` only from `invalid_listing_id`,
`missing_or_invalid_price` and `nonpositive_price`. `price_class`, `city_price_p99` and
`eligible_for_analysis` are not used by the split or by the headline population: test rows
include `extreme_high` (Milan 7, Florence 3), `stale_high` (15 / 4), `high_tail` (19 / 7) and `low_tail` (1 / 1).

`model_features` columns: keys, `price_eur`, `currency`, `eligible_for_training` and the 21
`PREDICTORS` of `airbnb/gold.py` (no price-derived or class columns).

## Baseline runs

| Run | Commit | Run ID | Result |
|---|---|---|---|
| First attempt | `3b06f1f` | 418805058420712 | FAILED before any write: serverless Spark Connect rejects `mode("errorifexists")`. Fixed to `mode("error")` in `f3d080b` |
| Baseline | `f3d080b` | 363160174813621 | SUCCESS; `model_split` and `baseline_lookup` created |
| Rerun | `f3d080b` | 245469386416437 | SUCCESS; both tables `unchanged`, identical metrics |

### Persisted tables

| Table | Version key | Delta version | Rows |
|---|---|---|---|
| `workspace.airbnb_gold.model_split` | `split_salt = 'airbnb-v1'` | 0 (2026-11-11T16:31:35Z) | 38,909 |
| `workspace.airbnb_gold.baseline_lookup` | `baseline_version = 'airbnb-v1'` | 0 (2026-11-11T16:31:44Z) | 44 (39 cell, 4 room type, 1 overall) |

Inputs at split time: `model_features` Delta v2, `silver.listings` v2, `bronze.listings` v2.

### Split (SHA-256 of `airbnb-v1|city|listing_id`, test if < 0.20)

| City | Train | Test | Excluded (not eligible) | Test share of eligible |
|---|---|---|---|---|
| Milan | 17,255 | 4,399 | 3,684 | 20.31 % |
| Florence | 9,684 | 2,464 | 1,423 | 20.28 % |

Duplicate keys: 0. A split recomputed from a fresh read of `model_features` differs from the
persisted table in 0 rows. The only exclusion reason is `not_eligible_for_training` (missing price).

### Baseline lookup and fallback use

Pooled training medians over 26,939 training rows; overall training median 175.00 EUR.

| Fallback level | Milan test | Florence test | All Milan rows | All Florence rows |
|---|---|---|---|---|
| `room_type_x_accommodates` | 4,397 | 2,463 | 25,335 | 13,570 |
| `room_type` | 2 | 1 | 3 | 1 |
| `overall` | 0 | 0 | 0 | 0 |

### Baseline MAE (EUR, held-out test rows)

Headline population `test_all_valid_positive_price`: every test row with a valid positive price.
0 test rows were excluded for an invalid actual.

| City group | n | Baseline MAE |
|---|---|---|
| Milan | 4,399 | **94.38** |
| Florence | 2,464 | **97.41** |
| Milan + Florence | 6,863 | **95.47** |

Supplementary only (`test_actual_le_train_threshold`): test rows with actual ≤ 1,156.62 EUR, the
99th percentile of pooled Milan + Florence **training** prices. Not a headline number.

| City group | n | Baseline MAE |
|---|---|---|
| Milan | 4,363 | 75.83 |
| Florence | 2,448 | 82.54 |
| Milan + Florence | 6,811 | 78.24 |

An independent SQL recomputation (exact `percentile` medians from `model_features` joined to
`model_split`) reproduced every MAE to 4 decimals, the fallback counts and the threshold.

## Tests

Linux container (Python 3.12.15, OpenJDK 21, PySpark 4.0.1),
`python -m unittest discover -s tests -v`:

| Tree | Bronze parameters | Silver | Model | Job definition | Result |
|---|---|---|---|---|---|
| `nazar/model-baseline` @ `3b06f1f` | 3 | 5 | 35 | – | 43 run, 43 passed, 0 failed, 0 skipped |
| `yaropolk/feature4-pipeline` @ `504278b` | 3 | 5 (incl. `validate_layers`) | – | 2 | 10 run, 10 passed, 0 failed, 0 skipped |

`f3d080b` changes only a notebook write mode, which no unit test covers; the notebook change was
verified by the Databricks runs above. On native Windows the 4 Spark-worker Silver tests crash
(`Python worker exited unexpectedly`) even for a one-row DataFrame; this is a local environment
issue, not a code failure. The two branches' suites were not run on one combined tree.

## Commit identifiers

The branch history was rewritten on 2026-11-11 to remove commit-message trailers; file
contents are byte-identical (same Git trees). The runs above executed the pre-rewrite commits:

| Current SHA | Pre-rewrite SHA (as run in Databricks) | Tree |
|---|---|---|
| `ea2b3ae` | `a02b758` | unchanged |
| `3b06f1f` | `dc97efb` | unchanged |
| `f3d080b` | `13b50d8` | unchanged |
| `bddffe0` | `ca089bd` | unchanged |

Workspace folder names (`airbnb_baseline_dc97efb`, `airbnb_baseline_13b50d8`) keep the pre-rewrite SHAs.

## Warnings and open items

- The pipeline ran from unmerged `yaropolk/feature4-pipeline`; feature3 is not on `main` yet.
- Tables are owned by Nazar in the shared catalog. Teammates need `USE SCHEMA`/`SELECT` (and
  `MODIFY` for pipeline reruns) if they are not workspace admins.
- The baseline notebook ran from a workspace import of the commit, not a Git folder; the
  imported folder name records the commit (`airbnb_baseline_13b50d8`).
- No prediction table for every listing yet (MODEL-06). The model and its held-out evaluation
  are in [model_selection.md](model_selection.md).
