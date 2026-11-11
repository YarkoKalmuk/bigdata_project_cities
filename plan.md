# Team Work Plan — Airbnb Price Analytics

## Goal and working rules

Build the Northern Italy Airbnb analytics project on Databricks Free Edition, using Milan and Florence for training and Venice for unseen-city evaluation. All work must cost nothing.

Sources: [README.md](README.md) and [assignment instructions](group_assignment_2.pdf).

This document is a plan only. Start implementation after the team has switched to working branches.
*(2026-11-11: implementation is under way on working branches; status is tracked in the task board at the end of this file.)*

- Use detailed `listings.csv.gz` snapshots. Verify Milan and Florence's recorded dates, and record Venice's snapshot in Week 2.
- Do not download or explore Venice before Week 1 is complete.
- Freeze the Milan/Florence pipeline, preprocessing, baseline and model before running Venice.
- Each person owns implementation, verification, documentation and presentation of their work.
- Aim for roughly one-third of the effort each. Review workloads at the end of Days 3 and 7 and redistribute supporting tasks if needed.

## Work divided among three people

| Member | Main ownership | Week 1 deliverables | Week 2 deliverables |
|---|---|---|---|
| **Kalmuk Yaropolk** | Data engineering and architecture | Workspace setup, source manifest, bronze ingestion, parameterised bronze → silver → gold pipeline, architecture diagram | Unchanged Venice pipeline run, pipeline fixes, reproducibility instructions, final repository integration |
| **Mykolaichuk Nazar** | Features, baseline and price model | Leakage review, training/test split, feature preparation, baseline, model comparison, evaluation and gold predictions | Unchanged Venice model evaluation, justified model changes, transfer-error analysis and model slides |
| **Matseliukh Maksym** | Exploratory analysis and analytics experience | Reproducible EDA notebook, missingness/outlier analysis, cleaning recommendations and gold metric definitions | Three-page dashboard, Genie configuration and answer checks, demo preparation and presentation assembly |

Maksym's substantial Week 1 EDA work balances his dashboard and Genie work in Week 2. Nazar owns model evaluation and the transfer analysis; Yaropolk owns pipeline operation and integration. Presentation assembly means combining everyone's completed slides, not writing everyone's content.

### Yaropolk — start first

1. Confirm that the region and city choices have been claimed in Teams; if needed, the team admin posts them with a one-sentence reason for choosing Venice.
2. Set up shared Databricks access and agree on a common catalog/schema location.
3. Establish repository folders for notebooks, pipeline definitions, documentation and presentation.
4. Load only Milan and Florence into bronze. Record source URLs, snapshot dates and row counts.
5. Publish a small data contract so Nazar and Maksym can start:
   - Bronze preserves source fields and adds city and snapshot metadata.
   - Silver uses `(city, snapshot_date, listing_id)` as the listing key, with typed columns and numeric EUR nightly price.
   - Invalid target values are flagged and excluded from training and scored evaluation; their counts remain visible.
6. Implement one pipeline accepting city, snapshot date and source location as parameters. No copied city-specific pipelines.
7. Apply the cleaning rules agreed from EDA, build gold outputs and document the architecture.

**Handoff:** As soon as A/B bronze data is available, provide its location and ingestion instructions to both teammates. Full ETL completion must not block EDA or initial modelling.

### Nazar — modelling and honest evaluation

1. Review candidate features for leakage, including fields derived from price.
2. Hold out 20% of eligible listings per training city before model selection, using a fixed seed. Fit preprocessing on training data only; use training-only validation for model choices.
3. Implement the required baseline: training median price by room type and accommodates. For unseen combinations, fall back to room-type median, then overall training median.
4. Train an interpretable regression model and compare it with the baseline. Handle unseen categories explicitly.
5. Report held-out MAE in EUR for Milan, Florence and both together.
6. Write predictions for every eligible listing to gold. Preserve excluded listings with a reason and no prediction. *(See decision D5: the assignment requires predictions for every listing.)*
7. Label training, held-out and unseen-city rows so dashboard evaluation charts use the correct population.

**Handoff:** Publish model artifacts, preprocessing, baseline lookup, feature list, evaluation results and a reproducible scoring entry point.

### Maksym — EDA, dashboard and Genie

1. Create a separate reproducible A/B EDA notebook with a summary at the top.
2. Document grain, snapshot dates, row counts, selected column types, missingness patterns, price and availability distributions, and outlier classifications.
3. Agree cleaning rules with Yaropolk and contribute findings to Nazar's leakage review.
4. Define gold metrics with the team, including availability meaning, host counts and missing-value handling.
5. In Week 2, build an AI/BI dashboard with finding-based page titles:
   - City overview.
   - Milan versus Florence comparison.
   - Model performance, later extended to Venice.
6. Configure Genie over gold tables with instructions and example questions covering prices, neighbourhood counts and model underpricing.
7. Check Genie answers against reference SQL queries and prepare a reliable demo.

**Handoff:** Commit EDA, dashboard queries/export where available, Genie instructions, example questions and verified answers.

## Two-week schedule and integration

| Period | Required outcome |
|---|---|
| **Week 1, Days 1–2** | Yaropolk starts setup and A/B ingestion. Maksym begins EDA once bronze is ready. Nazar begins leakage review and split design. |
| **Week 1, Days 3–4** | Agree cleaning and feature contracts. Implement silver, baseline, model and gold outputs. Review workload balance. |
| **Week 1, Day 5** | Complete A/B pipeline and model, run reproducibility checks and freeze the Week 1 Git revision and model artifacts. Record held-out A/B results. |
| **Week 2, Days 6–7** | Run the frozen pipeline and model on Venice. Preserve first-run logs and outputs before any fixes. Build dashboard and Genie. |
| **Week 2, Days 8–9** | Apply justified fixes, rerun evaluation, finish analytics and write the transfer report. Each member supplies their slides. |
| **Week 2, Day 10** | Rehearse, verify repository completeness and dashboard/Genie access, export the presentation and submit the repository link. |

The gold prediction interface must include listing key, actual price, baseline prediction, model prediction, evaluation split and model/run version. Metrics must identify their evaluation population.

For Venice:

- Yaropolk records pipeline success, failures and data-quality differences.
- Nazar records baseline MAE and frozen-model MAE; Maksym documents visible distribution shifts after the first run.
- Maintain a change log separating **pipeline fixes** from **model changes**, with reasons and before/after results.
- If adapting the model using Venice labels, reserve a fixed Venice test set before adaptation and never tune on it. Clearly distinguish this adapted evaluation from the original unseen-city result.
- Present Venice baseline, A/B held-out model MAE, Venice first-run model MAE and post-change MAE side by side. If scoring fails, preserve the failure honestly before reporting repaired results.

## Verification and submission checklist

- **Pipeline:** Same code runs for both training cities; rerunning a snapshot creates no duplicate listings; price parsing, missing values and exclusion counts are checked.
- **Model:** No target-derived features; preprocessing and baseline use training data only; unseen categories work; reported evaluation metrics use held-out or explicitly identified unseen-city rows.
- **Analytics:** Dashboard counts and metrics reconcile with gold tables; model error charts exclude training rows; Genie's example answers match SQL.
- **Transfer:** Frozen Week 1 revision is recorded; Venice first-run evidence is preserved; every subsequent change is classified and explained.
- **Repository:** Include notebooks, pipeline/job definition, architecture diagram, model reproduction instructions, transfer report, updated README and presentation PDF or link.
- **Presentation:** Each member presents their contribution. Include architecture, EDA, baseline/model results, Venice findings, dashboard/Genie demo and challenges.
- **Submission:** Only the team admin submits the repository link.

Defaults: use relative working days because no deadline was supplied; keep all three city choices from the README; use no optional reviews/calendar datasets unless the required work is complete.

---

## Task board

Added 2026-11-11 from a repository audit. Stable rules are in [CLAUDE.md](CLAUDE.md); this section holds changing status. Update a row only with evidence.

### Status legend

| Status | Meaning |
|---|---|
| `verified` | Implemented, and evidence of a successful run or test is committed or linked |
| `implemented-unverified` | Code exists; no committed evidence of a run (self-reports are noted) |
| `partial` | Some acceptance criteria met |
| `planned` | Described in this plan; no implementation |
| `blocked` | Cannot proceed until the listed dependency or decision is resolved |
| `missing` | Required by the assignment but not yet planned or assigned |

### Status snapshot (2026-11-11)

Nothing is merged into `main` yet. `main` (`7ddb183`) contains only this plan, the README, `.gitignore` and the brief.

| Branch | Head | Contents |
|---|---|---|
| `yaropolk/feature1-setup` | `e506c8c` | Setup notebook, parameterised bronze ingestion, `config/sources.json`, setup guide |
| `yaropolk/feature2-silver` | `e51e975` | First silver version and tests (superseded by feature3; diverged by one notebook-whitespace commit) |
| `yaropolk/feature3-eda-gold` | `9814b25` | Merges `maksym/eda`; EDA-informed silver, gold metrics, `model_features`, silver/gold contracts, tests. **Most complete line.** |
| `maksym/eda` | `4b97db4` | EDA notebook, exported run (`docs/eda_run.html`), EDA handoff |

Databricks (checked from Nazar's CLI profile, metadata only): `workspace.airbnb_bronze`, `airbnb_silver` and `airbnb_gold` do not exist in that workspace. `workspace.maksym_airbnb_eda` exists, but Nazar lacks `USE SCHEMA` on it. The reported bronze/silver runs are therefore not visible to Nazar (see B1).

City C check: no Venice URL, config entry, file or query was found on any branch.

### Setup and data

| ID | Task | Owner | Status | Depends on | Acceptance criteria | Evidence required |
|---|---|---|---|---|---|---|
| SETUP-01 | Claim the region and post cities A/B/C, with a one-sentence reason for choosing C, in Teams | Yaropolk (team admin?) | planned | — | Claim posted; reason for C recorded in README | Screenshot or quote of the Teams post; README line |
| SETUP-02 | Shared Databricks workspace, catalog and schemas readable by all three members | Yaropolk | blocked (B1) | — | Each member can `SELECT` from the bronze, silver and gold schemas | `SHOW GRANTS` output or a query run by each member |
| SETUP-03 | Verify that 2026-09-19 is the latest Milan/Florence snapshot | Yaropolk | partial | — | Dates confirmed against Inside Airbnb; README and config agree | Note with check date |

### EDA (deliverable 3.1)

| ID | Task | Owner | Status | Depends on | Acceptance criteria | Evidence required |
|---|---|---|---|---|---|---|
| EDA-01 | Reproducible A/B EDA notebook (summary, grain, counts, column profile, missingness patterns, distributions, outliers, cleaning rules) | Maksym | implemented-unverified (run export committed on branch) | — | All 3.1 bullets covered; reruns from raw files | `notebooks/eda_milan_florence.py` and `docs/eda_run.html` on `main` |
| EDA-02 | Leakage review | Maksym; Nazar signs off for features | implemented-unverified | EDA-01 | Leaks tested, not just listed; feature allowlist agreed | `docs/eda_handoff.md` and the MODEL-01 sign-off |

### Architecture and pipeline (deliverables 3.2, 3.3)

| ID | Task | Owner | Status | Depends on | Acceptance criteria | Evidence required |
|---|---|---|---|---|---|---|
| ARCH-01 | Architecture diagram and description | Yaropolk | partial (Mermaid draft in `docs/architecture.md`) | PIPE-03 | Bronze, silver and gold purposes stated; matches the implemented tables | Diagram on `main`; rendered image for the slides |
| PIPE-01 | Bronze ingestion, parameterised by city | Yaropolk | implemented-unverified (self-reported run) | SETUP-02 | Both cities loaded; manifest counts equal source counts; rerun is idempotent | Manifest query output for both cities |
| PIPE-02 | Silver typing, price parsing, quality flags and exclusion reasons (EDA rules) | Yaropolk | implemented-unverified (unit tests on synthetic data; EDA-updated version not yet run) | PIPE-01 | Counts match bronze (Milan 25,338; Florence 13,571); key unique; rerun leaves the other city unchanged | Notebook 02 output for both cities; passing test log |
| PIPE-03 | Gold metrics and `model_features` | Yaropolk | implemented-unverified (execution pending) | PIPE-02 | Checks in `docs/gold_contract.md` pass; feature count equals silver count | Notebook 03 output for both cities |
| PIPE-04 | Databricks Job or declarative pipeline definition with `city` as a parameter, run per city | Yaropolk | missing | PIPE-01..03 | One definition runs bronze → silver → gold for each city; definition committed | Job YAML/JSON or bundle in the repository; run IDs for both cities |
| PIPE-05 | Make the city parameter genuinely open before the freeze | Yaropolk | planned | D2 | Adding a city needs only a config entry and a raw file, with no code edit. Today, notebook dropdowns hard-code `milan`/`florence`. | Code diff; test using a synthetic third city name |
| PIPE-06 | Reproducibility check: rerun A/B from scratch | Yaropolk | planned | PIPE-04 | Identical counts and metrics after the rerun | Before/after counts |

### Model (deliverable 3.4) — Nazar

| ID | Task | Owner | Status | Depends on | Acceptance criteria | Evidence required |
|---|---|---|---|---|---|---|
| MODEL-01 | Feature allowlist and leakage sign-off | Nazar | planned | EDA-02, PIPE-03 | Every predictor justified. Drop or flag empty and high-cardinality fields (`instant_bookable`, which EDA reports 100 % empty; `property_type`). No target-derived columns. Unseen categories handled. | Feature table with a reason per feature, in `docs/` |
| MODEL-02 | Deterministic, persisted 80/20 test split per city, created before any model choice | Nazar | planned | PIPE-03 (code can start now) | The split depends only on `(city, listing_id)` and a seed, not on row order. Each city gets a 20 % ± 1 % test share. The split is persisted to a table. | Split table and counts per city |
| MODEL-03 | Required baseline: training median by `room_type × accommodates`, with a fallback chain | Nazar | planned | MODEL-02, D3 | Fitted on training rows only. Every test row gets a prediction. The fallback level used is recorded per row. | Lookup table; fallback-level counts |
| MODEL-04 | Model selection on training-only validation (log price, interpretable model) | Nazar | planned | MODEL-01..03 | The test set is untouched during selection; choices are logged. | MLflow runs or a notebook export |
| MODEL-05 | Held-out evaluation: MAE in EUR for Milan, Florence and both, model vs baseline on identical rows | Nazar | planned | MODEL-03, MODEL-04, D4 | Population stated; optional filtered metrics labelled separately | Metrics table; notebook export |
| MODEL-06 | `gold.predictions` for every listing | Nazar | planned | MODEL-05, D5, D9 | One row per listing per `model_version`. Fields: keys, `model_version`, `run_id`, `evaluation_split` (`train`/`test`/`unseen`), actual, baseline, prediction, error, signed residual, scoring-exclusion reason. Row count equals silver. | Count reconciliation query |
| MODEL-07 | Frozen artifacts and a city-parameterised scoring entry point | Nazar | planned | MODEL-06 | Scores any configured city from `model_features` without retraining | Artifact ID; scoring run for A/B |

### Dashboard and Genie (deliverables 3.5, 3.6) — Week 2

| ID | Task | Owner | Status | Depends on | Acceptance criteria | Evidence required |
|---|---|---|---|---|---|---|
| DASH-01 | City overview page | Maksym | planned | PIPE-03 | Finding-based title; figures reconcile with `city_metrics` | Dashboard export/link; reconciliation query |
| DASH-02 | Cross-city comparison page | Maksym | planned | PIPE-03 | Finding-based title; side-by-side metrics and the differences that matter | Same as DASH-01 |
| DASH-03 | Model page (later extended with Venice) | Maksym, with Nazar | planned | MODEL-06 | Predicted vs actual; error by room type or neighbourhood; most under- and over-priced listings; test or unseen rows only | Same as DASH-01 |
| GENIE-01 | Genie space over gold tables, with instructions and example questions | Maksym | planned | PIPE-03, MODEL-06 | The three example questions in the brief are covered; instructions define metric populations | Committed instructions text |
| GENIE-02 | Validate Genie answers against reference SQL | Maksym | planned | GENIE-01 | Each example answer matches its SQL | Question / SQL / answer table |

### Freeze and city C (deliverable 3.7)

| ID | Task | Owner | Status | Depends on | Acceptance criteria | Evidence required |
|---|---|---|---|---|---|---|
| FREEZE-01 | **Milestone M1: A/B freeze** | All; Yaropolk records it | planned | PIPE-04..06, MODEL-07 | Everything in the "Week 1 freeze" definition in CLAUDE.md is recorded below | Tag name, artifact ID, metrics table |
| CITYC-01 | Record the Venice snapshot date and URL; upload the raw file (only after M1) | Yaropolk | planned | FREEZE-01 | README and config updated; no other change | Commit SHA |
| CITYC-02 | **Milestone M2: first unchanged pipeline run on Venice** | Yaropolk | planned | CITYC-01 | Ran or failed at the frozen tag; logs preserved | Run IDs, errors and counts committed under `docs/` |
| CITYC-03 | First unchanged model scoring on Venice: baseline MAE and frozen-model MAE | Nazar | planned | CITYC-02 | Written under the frozen `model_version`; never overwritten | Metrics table; prediction row count |
| CITYC-04 | Distribution shifts visible after the first run | Maksym | planned | CITYC-02 | Shifts described with numbers | Notes or notebook export |
| FIX-01 | Pipeline fixes, logged as "pipeline fix" | Yaropolk | planned | CITYC-02 | Each change has a reason and before/after effect | Change log in the transfer report |
| FIX-02 | Model changes, logged as "model change" | Nazar | planned | CITYC-03, D10 | If Venice labels are used, a Venice test set is reserved first; adapted results are reported separately | Change log; new `model_version` |
| REPORT-01 | **Milestone M3: transfer report** | Nazar (model), Yaropolk (pipeline) | planned | FIX-01, FIX-02 | Venice baseline, A/B model MAE and Venice first-run/post-change model MAE side by side; gap explained | Report file in the repository |

### Presentation and repository (deliverables 3.8, 3.9)

| ID | Task | Owner | Status | Depends on | Acceptance criteria | Evidence required |
|---|---|---|---|---|---|---|
| PRES-01 | Presentation: each member's slides, assembled by Maksym | All | planned | REPORT-01, DASH-*, GENIE-* | Covers every 3.8 bullet; demo rehearsed | PDF or link in the repository |
| REPO-01 | Integrate branches into `main`; README with region, cities, dates, links, reproduction steps | Yaropolk | planned | D11 | `main` holds notebooks, pipeline definition, docs and presentation | `main` tree |
| CONTRIB-01 | Contribution record per member | All | missing | — | Each member's work listed with evidence links | Section in README or report |
| SUBMIT-01 | Submit the repository link | Team admin | planned | REPO-01, PRES-01 | Submitted once | Confirmation |

### Work that can run in parallel now

- **Nazar:** MODEL-02, MODEL-03 and MODEL-05 logic plus synthetic tests, without Databricks data. Also the MODEL-01 draft against `PREDICTORS` in `airbnb/gold.py`.
- **Yaropolk:** B1 (shared access), PIPE-02/03 execution, PIPE-04 Job definition, PIPE-05 open city parameter.
- **Maksym:** draft dashboard SQL and Genie instructions against the `docs/gold_contract.md` schemas; resolve D4 with Nazar.

### Blockers

| ID | Blocker | Affects | Owner |
|---|---|---|---|
| B1 | Gold `model_features` is not reachable from Nazar's workspace: the `airbnb_*` schemas don't exist there, and there is no access to `maksym_airbnb_eda` | MODEL-02..07 runs | Yaropolk |
| B2 | Nothing is merged into `main`; feature2 and feature3 have diverged | Shared base for new branches | Yaropolk (D11) |

### Open decisions (need team confirmation)

| ID | Decision | Recommendation |
|---|---|---|
| D1 | Reason for choosing Venice, and who the team admin is | Record both in the README |
| D2 | Which edits are allowed for the first Venice run | Config entry and raw-file upload only; remove the hard-coded city dropdowns before M1 |
| D3 | Baseline scope and fallback chain | Pooled A+B training medians by `room_type × accommodates` → `room_type` → overall training median. Avoid a "city median" fallback: it is undefined for Venice under the frozen lookup. Report per-city variants only as extras. |
| D4 | Headline MAE population | All test rows with a valid positive price (per the silver contract), with a separately labelled `extreme_high`-excluded MAE. Fix this before any test number is computed. |
| D5 | Predictions for every listing vs every eligible listing | Score every listing with usable predictors. `actual_price_eur` is null for unpriced rows, and the scoring-exclusion reason is recorded when scoring is impossible. |
| D6 | Training-side outlier treatment | Fit any trimming threshold on training rows only. Never use `price_class`/`eligible_for_analysis` from silver: they are computed on the whole snapshot, test rows included. |
| D7 | City level as a feature | No city one-hot: it does not transfer. Accept the A/B level gap as a documented limitation, or use only city-agnostic location features (`dist_center_km`). |
| D8 | Split implementation | Hash of `(city, listing_id)` with a fixed salt; 20 % test per city; persisted |
| D9 | Prediction-table key and write mode | Key `(city, snapshot_date, listing_id, model_version)`; writes replace only their own `model_version` |
| D10 | Whether Venice labels may be used for model changes | Only with a reserved Venice test set, reported separately |
| D11 | Merge policy into `main` | Merge `yaropolk/feature3-eda-gold` (which includes `maksym/eda`) via a PR. New branches start from it. |
| D12 | Calendar dates for the Week 1 freeze, Week 2 and the deadline | Record actual dates in the schedule |

### Freeze and first-run record

*(Empty until M1. Fill in: tag, commit SHA, model artifact ID, split table version, baseline lookup version, A/B metrics. After M2: Venice snapshot date, run IDs, outcome, first-run metrics.)*
