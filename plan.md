# Team Work Plan — Airbnb Price Analytics

## Goal and working rules

Build the Northern Italy Airbnb analytics project on Databricks Free Edition, using Milan and Florence for training and Venice for unseen-city evaluation. All work must cost nothing.

Sources: [README.md](README.md) and [assignment instructions](group_assignment_2.pdf).

The sections below retain the agreed responsibilities and original schedule. For actual completion and remaining work, use the dated task board at the end; historical instructions are not approval to rerun completed experiments.

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
6. Write versioned predictions and explicit status/exclusion reasons to Gold. The final contract retains all listings, including unpriced rows predicted without evaluation error; see `airbnb/scoring.py`.
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

## Actual task board — 2026-11-12

Statuses refer to evidence, not merely code existence. “Complete, review pending”
means delivered on PR #4 or this documentation follow-up, awaiting approved merge.
No PR was merged/closed and no experiment rerun during this review. The stale
branch plan in PR #1 is superseded by this board after approval; its task IDs are
retained for continuity.

| ID | Deliverable / owner | Actual status and evidence / next action |
|---|---|---|
| SETUP-01 | City claim, team admin, submission deadline / team | Confirmation not present in reviewed repository; team must confirm Teams claim, admin and deadline |
| SETUP-02 | Shared workspace and repository / Yaropolk | Complete for recorded ETL/model runs; final BI viewer access still requires Maksym's acceptance |
| EDA-01 | A/B EDA / Maksym | Complete: notebook, `docs/eda_run.html`, [EDA handoff](docs/eda_handoff.md) |
| EDA-02, MODEL-01 | Leakage and feature allowlist / Maksym, Nazar | Complete: [feature review](docs/model_feature_review.md), [selection](docs/model_selection.md); target-derived fields excluded |
| ARCH-01 | Architecture / Yaropolk | Complete, review pending: [description + PNG/SVG](docs/architecture.md) reflect frozen ETL, separate scorer and pending Venice BI acceptance |
| PIPE-01 | Parameterised Bronze / Yaropolk | Complete: A/B freeze evidence and first Venice 8,844 rows |
| PIPE-02 | Silver typing and quality / Yaropolk | Complete: retained counts/unique keys and explicit flags; [Venice first-run report](docs/week2/venice_first_run_2026-09-16/REPORT.md) |
| PIPE-03 | Gold metrics/features / Yaropolk | Complete: Venice 8,844 features; 1/4/60 metric rows; [joint report](docs/week2/transfer_report.md) |
| PIPE-04 | Immutable ETL Job / Yaropolk | Complete: Job 816607442908043; source f408ac01ffdd025fab6df220c8f89b24d3d4fda6 |
| PIPE-05 | Open city configuration / Yaropolk | Complete: external Venice manifest, unchanged frozen code; no copied city notebooks |
| PIPE-06 | A/B reproducibility/idempotence / Yaropolk | Complete per [M1 acceptance](docs/week1_freeze.md) and [run log](docs/pipeline_run_log.md); not rerun for this review |
| MODEL-02, MODEL-03 | Persisted split and training-only baseline / Nazar | Complete: frozen split and 44-row baseline lookup; [baseline evidence](docs/model_baseline_run.md) |
| MODEL-04, MODEL-05 | Selection and held-out MAE / Nazar | Complete: [selection](docs/model_selection.md), [freeze](docs/week1_freeze.md); combined baseline/model MAE 95.47/75.88 EUR, n=6,863 |
| MODEL-06, MODEL-07 | Versioned predictions and frozen scorer/artifact / Nazar | Complete: price-v1 / score-v1; [model evidence](docs/week2/venice_model_first_run_2026-09-16/REPORT.md), no retraining |
| FREEZE-01 | M1 freeze / team, Yaropolk records | Complete: published M1-freeze at 7f76cbe6936e76fa3a7685ac90b40c1ce1c253df; tag unchanged |
| CITYC-01 | Venice input after M1 / Yaropolk | Complete: 2026-09-16 detailed gzip + separate runtime manifest, original file hash preserved |
| CITYC-02 | First unchanged Venice ETL / Yaropolk | Complete: run 782550938914199, four tasks successful; 19 protected fingerprints unchanged |
| CITYC-03 | First frozen-model Venice score / Nazar | Complete, PR #4 review pending: run 65362888524059; 8,844 predictions / 8,144 evaluated; baseline/model 142.46/106.07 EUR |
| CITYC-04 | Distribution shifts / Maksym, with Nazar and Yaropolk evidence | Quantitative evidence complete in [joint report](docs/week2/transfer_report.md); Maksym's final visual interpretation/demo pending |
| FIX-01 | Pipeline fix / Yaropolk | **None / not required**; first ETL succeeded without intervention. No post-fix run or metric |
| FIX-02 | Model change / Nazar | **None / not required**; frozen artifact handled Venice. No adaptation or post-change model |
| REPORT-01 | Joint transfer report / Yaropolk + Nazar | Complete, review pending: [report](docs/week2/transfer_report.md), separate first-run evidence preserved |
| DASH-01, DASH-02 | Overview / comparison pages / Maksym | A/B deployment/assets reported on maksym/dashboard-genie; Venice refresh, reconciliation and approved BI merge pending |
| DASH-03 | Model transfer page / Maksym + Nazar | Partial: reference SQL/model handoff ready; Venice population/run filters, neighbourhood enrichment and distance-band alignment pending acceptance |
| GENIE-01, GENIE-02 | Space and verified example answers / Maksym | A/B deployment reported on BI branch; Venice questions/SQL/actual answers and viewer access checks pending |
| PRES-01 | Presentation and rehearsal / all; Maksym assembles | Engineering [slide points + diagram](docs/week2/handoff_dashboard_genie_engineering.md) and [model outline](docs/week2/handoff_model_slides.md) ready; final deck/PDF, demo and rehearsal pending |
| REPO-01 | Integration and reproducibility / Yaropolk | Docs complete for review; PR #4 + stacked follow-up require approval, PR #1/#2 disposition pending; BI assets and presentation not yet integrated |
| CONTRIB-01 | Contribution record / all | Complete, review pending: README records delivered work and remaining ownership |
| SUBMIT-01 | Final repository submission / team admin | Pending approved integration, final BI/deck/access checks and submission confirmation |

### Immediate handoff and safe integration

Maksym can proceed now; he does not need another ETL/model run. Use
[engineering handoff](docs/week2/handoff_dashboard_genie_engineering.md) and
[Nazar's SQL/model handoff](docs/week2/handoff_dashboard_genie_model.md).
The [integration review](docs/week2/integration_review.md) proposes PR #4 first,
then this follow-up retargeted to main, with PR #2 closed as redundant and PR #1
closed as superseded only after approval. Final BI/presentation review follows.
