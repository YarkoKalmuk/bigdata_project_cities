# Week 1 integration check (pipeline + model)

Owner: Mykolaichuk Nazar. Recorded 2026-11-11 (UTC). Status: **integration candidate, not the freeze**.
No freeze tag exists. Venice was not downloaded, configured, queried or run. No model was retrained,
no prediction was rewritten and no Databricks object was created or modified for this check.
Detailed model evidence stays in [model_baseline_run.md](model_baseline_run.md),
[model_selection.md](model_selection.md), [model_predictions_run.md](model_predictions_run.md) and
[model_freeze_candidate.md](model_freeze_candidate.md).

## Branch topology (after `git fetch --all --prune`)

| Ref | Head | Notes |
|---|---|---|
| `origin/main` | `7ddb183` | feature3/feature4 **not merged**; only open PR is #1 (`nazar/project-plan` → `main`) |
| `origin/yaropolk/feature3-eda-gold` | `d67faa9` | merge base with `main`: `7ddb183` |
| `origin/yaropolk/feature4-pipeline` | `1a33bc3` | contains feature3 (`d67faa9` is an ancestor) + `504278b`, `1a33bc3` |
| `nazar/model-baseline` before merge | `a6d2df1` | merge base with feature3 and feature4: `d67faa9`; 11 model commits on top |
| `nazar/project-plan` | `001d0f1` | unrelated to this integration |

Integration commit: `7c3536d` — `git merge --no-ff origin/yaropolk/feature4-pipeline` into
`nazar/model-baseline` (parents `a6d2df1`, `1a33bc3`). No conflicts: the two sides change disjoint
files. Teammate commits keep their original SHAs and authorship. Model code, `airbnb/silver.py`,
`airbnb/gold.py` and `config/sources.json` are byte-identical to `a6d2df1`; pipeline files are
byte-identical to `1a33bc3`.

The shared Databricks tables were produced by pipeline code `504278b`; `504278b..1a33bc3` changes
only `docs/pipeline_run_log.md`, whitespace in `notebooks/05_create_etl_job.py` and adds a scratch
notebook, so the pipeline that produced the model's inputs is the pipeline in this tree.

## Notebook sequence (collision-free)

`00_setup` · `01_ingest_bronze` · `02_prepare_silver` · `03_build_gold` · `04_validate_pipeline` ·
`05_create_etl_job` · `06_baseline_eval` · `07_train_model` · `08_score_predictions`, plus
`eda_milan_florence`. The Job (`jobs/airbnb_etl.job.json`) chains 01 → 02 → 03 → 04.

## Combined tests

Linux container (`airbnb-tests:pyspark401` + pinned scikit-learn): Python 3.12.15, OpenJDK 21.0.13,
PySpark 4.0.1, scikit-learn 1.7.2, numpy 2.3.4, pandas 2.3.3, joblib 1.5.2.
`SPARK_LOCAL_IP=127.0.0.1 python -m unittest discover -s tests -v` on the merged tree:

| Module | Tests |
|---|---:|
| `test_bronze_parameters` | 3 |
| `test_silver` (incl. gold build and `validate_layers`) | 5 |
| `test_job_definition` | 2 |
| `test_model` (split, baseline, MAE) | 35 |
| `test_price_model` | 14 |
| `test_scoring` | 30 |
| **Total** | **89 run, 89 passed, 0 failed, 0 skipped** — 26.3 s (unittest), 27.3 s wall |

Without scikit-learn installed the image skips `test_price_model` and `test_scoring` (47 run, 2
module skips); the numbers above are with it installed.

## Contract compatibility

| Check | Result |
|---|---|
| feature4 changes to preprocessing inputs or eligibility | None: `airbnb/silver.py` and `airbnb/gold.py` are untouched by feature4 |
| `model_features` columns (code and Databricks `DESCRIBE`) | 27 = keys, `price_eur`, `currency`, `eligible_for_training` + 21 `gold.PREDICTORS`; equals the `validate_layers` allowlist |
| Frozen `FEATURES` (16) ⊆ `gold.PREDICTORS` | Yes; unused predictors: `instant_bookable`, `review_scores_accuracy/_checkin/_communication/_value` |
| Forbidden/leaky columns among `PREDICTORS` | None |
| Code `spec_sha256` in merged tree | `acd5e6e0…a99` = frozen value in `scoring.FROZEN_MODELS["price-v1"]` |
| Prediction schema | `predictions-v1`, 25 columns, Databricks `DESCRIBE` equals `scoring.PREDICTION_SCHEMA` |
| City-specific code for Venice | None. `config/sources.json` keys: `milan`, `florence` |

## Databricks state (read-only SQL / Files API, warehouse `Serverless Starter Warehouse`)

| Item | Result |
|---|---|
| Artifact file `/Volumes/workspace/airbnb_gold/model_artifacts/price-v1/model.joblib` | 1,484,150 B, SHA-256 `c0416cde…0fb2c` = frozen |
| `selection_record.json` | SHA-256 `9122ca56…49db` = frozen |
| `model_artifacts` row | artifact/spec/selection hashes, `hgb_leaves_31_iter_400`, `hgb_log`, scikit-learn 1.7.2, MLflow `a08250c6bcb5415c9591c6427e3d6bf7` = frozen |
| `model_split` `airbnb-v1` | Milan 17,255 / 4,399 / 3,684, Florence 9,684 / 2,464 / 1,423 (train / test / excluded); fingerprint `d4625414…0a880` = frozen |
| `baseline_lookup` `airbnb-v1` | 44 rows |
| `model_features` | Delta v2; Milan 25,338, Florence 13,571 |
| `predictions` | Delta v1 (history: v0 CTAS, v1 WRITE, both 17:16 UTC; nothing later); 38,909 rows = 38,909 distinct `(city, snapshot_date, listing_id, model_version)`; 0 `model_features` rows without a prediction; `price-v1` only; one `scoring_run_id` 772231092119601; `source_feature_table_version` 2 |
| `predictions` content fingerprint | `3ec054b4…ad3b3f` at `VERSION AS OF 1` and at current version (identical) |

Content fingerprint: SHA-256 of sorted
`city|snapshot_date|listing_id|model_version|evaluation_split|actual|baseline_pred|model_pred|status|fallback_level`
lines. Full value: `3ec054b452ce36c5cf7a2c50979b5400a0401fd7598b3a1a29e326e5c3ad3b3f`.

### Official metric reproduction (from `predictions`, `evaluation_split = 'test'`)

| Group | Test rows | Baseline MAE | Model MAE |
|---|---:|---:|---:|
| Milan | 4,399 | 94.38 | **75.72** |
| Florence | 2,464 | 97.41 | **76.18** |
| Milan + Florence | 6,863 | 95.47 | **75.88** |

Equal to `model_evaluation` (`test_all_valid_positive_price`) and to `FROZEN_MODELS` to within 1e-12 EUR.

### Venice absence

Bronze, silver, every gold table and `pipeline_validations` contain only `milan`/`florence`; the raw
volume has only `milan/` and `florence/`; no catalog table or schema name matches Venice.

## Permissions (Yaropolk `kalmuk.pn@…`, Maksym `matseliukh.pn@…`)

Supersedes "Access (not granted)" in `model_freeze_candidate.md`.

| Securable | Effective UC privileges (both) |
|---|---|
| catalog `workspace` | `USE CATALOG` (via all-workspace-users group) |
| schema `airbnb_gold` | `USE SCHEMA` (direct) |
| all 12 `airbnb_gold` tables | `SELECT` (direct), no `MODIFY` |
| schemas `airbnb_bronze`, `airbnb_silver` | none |

**Not met:** both are members of the workspace `admins` group. The `workspace` catalog is owned by
`_workspace_admins_workspace_7474659920821008`, so as workspace admins they hold catalog-owner
control over the gold tables despite the read-only grants. All `airbnb_*` schemas and tables are
owned by Mykolaichuk Nazar. Changing admin membership affects the whole team (and the Venice pipeline
run needs write access), so it was not changed here; the team decides.

## Remaining upstream dependencies before the freeze

1. Merge feature3/feature4 into `main`, then this branch; the freeze tag goes on the `main` commit.
2. Notebooks 01–03 restrict `city` to a `["milan", "florence"]` dropdown, so a new city needs a code
   edit — conflicts with freeze item 5 (config entry + raw file only). Yaropolk's
   `docs/pipeline_job.md` already lists this as pending. Notebook 08 already validates against config.
3. `jobs/airbnb_etl.job.json` pins `git_branch: yaropolk/feature4-pipeline`; it must point at the
   frozen commit/tag. The persistent Job `airbnb-cities-etl` is not registered in the shared
   workspace (`jobs list` is empty).
4. `docs/pipeline_run_log.md` cites Job 721102111883860 and runs 456920958407795, 471517583759997,
   1039839162011700, which do not exist in the shared workspace. The runs behind the current tables
   are submit runs 399786082243961, 334832161613071, 768192587578562 (recorded in
   `pipeline_validations` and `model_baseline_run.md`).
5. feature4 adds `notebooks/New Notebook 2026-11-11 17:48:57.ipynb` (a scratch duplicate-key query).
   The `:` in its name makes it impossible to check out on Windows; this check used a local
   sparse-checkout exclusion. It should be removed upstream.
6. Admin membership vs read-only access (above); `plan.md` freeze record (tag, artifact, split,
   MAE table, add-a-city procedure).
