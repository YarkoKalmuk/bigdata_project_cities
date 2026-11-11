# Model freeze candidate: price-v1

The model candidate's identity and metrics have now been checked live against
the integrated main source. [The M1 record](week1_freeze.md) is authoritative for
the full-system release; candidate-era access/merge notes below are historical.

The model identity below is preserved. Later code integration and workspace reconciliation are tracked in [integration readiness](integration_readiness.md); this document is not evidence that the full-system freeze has occurred. Access findings below are historical and were superseded by the later [workspace check](week1_integration_check.md#permissions-yaropolk-kalmukpn-maksym-matseliukhpn).

Status: **freeze candidate, not the Week 1 freeze.** No Git freeze tag exists. The final freeze
needs feature3, feature4 and `nazar/model-baseline` integrated into `main`, then a tag on the
integrated commit and an entry in `plan.md` (M1). Recorded 2026-11-11 by Mykolaichuk Nazar.

## Code

| Item | Value |
|---|---|
| Scoring commit (produced `airbnb_gold.predictions`) | `329d3f114cfc1148db2761207154456409515573`, tree `5c78cd632d8d1961c848fb36613eb10010953ae2` |
| Training / selection commits | `d1c2bd6` (`final`), `3f79eb9` (`select`); model code unchanged since |
| Branch | `nazar/model-baseline`, stacked on `yaropolk/feature3-eda-gold` @ `d67faa9`; `main` is still `7ddb183` |
| Pinned record in code | `airbnb/scoring.py` → `FROZEN_MODELS["price-v1"]` |

## Versions

| Item | Value |
|---|---|
| Model version | `price-v1` (reused; meaning unchanged since MODEL-04) |
| Scoring version | `score-v1` |
| Prediction schema version | `predictions-v1` |
| Feature contract | 16 features of `airbnb/price_model.py` `FEATURES`; `spec_sha256` `acd5e6e0e6a0badec0d34b4d2266c6485bba6135c679d92169db8a419992ea99` |
| Split version | `split_salt = 'airbnb-v1'`, test share 0.20, fingerprint `d4625414b6181cecf5de7548b376d77377b500b5e758f0a49236a356ae00a880` |
| Baseline lookup version | `baseline_version = 'airbnb-v1'`, 44 rows, fingerprint `0ca4b685a4b85babccc0810105eb35c074b34808f28d1a54d4012149b987b65c` |
| Training snapshots | Milan 2026-09-19, Florence 2026-09-19 |

## Artifact

| Item | Value |
|---|---|
| Model | `HistGradientBoostingRegressor` on `log1p(price_eur)`, `hgb_leaves_31_iter_400` (learning rate 0.05, 400 iterations, 31 leaves, min 40 rows per leaf, L2 1.0, seed 20261111) |
| File | `/Volumes/workspace/airbnb_gold/model_artifacts/price-v1/model.joblib`, 1,484,150 B |
| SHA-256 | `c0416cde7f652342ce5217a936a6aa0a60d2476cc059c7e970b0c8001640fb2c` |
| MLflow | run `a08250c6bcb5415c9591c6427e3d6bf7`, experiment `/Users/<owner>/airbnb_price_model` (same file hash) |
| Selection record | SHA-256 `9122ca565f036895a0b41fff61f1ac39bfa5066ea0a4ef8195bb8c0402af49db` (`model_selection` and `selection_record.json`) |
| Runtime | Databricks serverless environment 6 (Python 3.12.3, scikit-learn 1.7.2, numpy 2.3.4, pandas 2.3.3) |

## Held-out metrics (`test_all_valid_positive_price`, MAE in EUR)

| Group | Test rows | Baseline | Model | Improvement |
|---|---:|---:|---:|---:|
| Milan | 4,399 | 94.38 | **75.72** | 19.77 % |
| Florence | 2,464 | 97.41 | **76.18** | 21.80 % |
| Milan + Florence | 6,863 | 95.47 | **75.88** | 20.51 % |

Population: every persisted `test` row with a valid positive price; 0 test rows excluded. The stored
predictions table reproduces these numbers exactly ([model_predictions_run.md](model_predictions_run.md)).

## Databricks tables (`workspace.airbnb_gold`)

| Table | Delta version | Rows for this candidate |
|---|---|---|
| `model_features` | 2 | 38,909 |
| `model_split` | 0 | 38,909 (`airbnb-v1`) |
| `baseline_lookup` | 0 | 44 (`airbnb-v1`) |
| `model_selection` / `model_candidate_metrics` | 0 / 0 | 1 / 48 |
| `model_artifacts` / `model_evaluation` | 0 / 0 | 1 / 6 |
| `predictions` | 1 | 38,909 (`price-v1`) |

## Runs

| Stage | Job run | Task run |
|---|---|---|
| `07_train_model` `select` | 507329454375587 | 417986478430148 |
| `07_train_model` `final` | 906579585632281 | 1014284074152913 |
| `08_score_predictions` first scoring | 772231092119601 | 796954295181797 |
| `08_score_predictions` identical rerun | 439004645258706 | 619578019160463 |
| `08_score_predictions` Florence only | 850810674321113 | 858187179953820 |

## Scoring a new city with the frozen model (model part of the add-a-city procedure)

Permitted inputs: the city's `config/sources.json` entry and its uploaded raw file. Then:

1. Run notebooks 01–03 for the city (Yaropolk's pipeline procedure).
2. Run `notebooks/08_score_predictions` from the frozen commit with `cities=<city>`,
   `model_version=price-v1`, `code_revision=<frozen commit>`, `scoring_run_id={{job.run_id}}`.
   The notebook verifies the artifact before scoring, labels every row `unseen`, writes errors for
   every row with a valid price and appends under `price-v1`. It never touches Milan/Florence rows.
3. Preserve that run's output and summary. Any later change uses a new `model_version` or
   `scoring_version`; the notebook refuses different content under an existing one.

## Known limitations

- Predictions are bit-exact only in Databricks serverless environment 6; a Windows x86 run changed
  14 of 38,909 predictions by up to 2.2 EUR (see the run doc).
- The model under-predicts on average (test mean residual −35.5 EUR Milan, −12.5 EUR Florence) and
  most of its error is in the top price tail; hotel and shared rooms have very few training rows.
- The selected configuration is at the edge of its predeclared grid; the grid was not widened.
- `train` rows hold in-sample errors; held-out numbers use `evaluation_split = 'test'` only.
- `room_type` and `property_type` levels unseen in training fall into `__other__`; distance uses the
  configured city centre, so a new city's distance scale may differ.
- No Git freeze tag; the branch is not on `main`.

## Access (not granted)

Kalmuk Yaropolk and Matseliukh Maksym currently have **no** effective Unity Catalog privileges on
`workspace.airbnb_gold` or `predictions`. The only groups holding all three members (`admins`,
`users`) are workspace-local groups, which Unity Catalog cannot grant to, and the account group
`_workspace_users_workspace_7474659920821008` means "every workspace user", not the team. No grant
was made. The schema owner (Mykolaichuk Nazar) should run the following, or the team should create an
account-level team group and grant to it instead:

```sql
GRANT USE SCHEMA ON SCHEMA workspace.airbnb_gold TO `kalmuk.pn@ucu.edu.ua`;
GRANT USE SCHEMA ON SCHEMA workspace.airbnb_gold TO `matseliukh.pn@ucu.edu.ua`;
GRANT SELECT ON TABLE workspace.airbnb_gold.predictions TO `kalmuk.pn@ucu.edu.ua`;
GRANT SELECT ON TABLE workspace.airbnb_gold.predictions TO `matseliukh.pn@ucu.edu.ua`;
```

The dashboard and Genie will also need `SELECT` on the metric tables, and the Venice pipeline run
needs `MODIFY`/`CREATE TABLE` on the schemas; those are outside this model chunk.
