# Team Work Plan — Airbnb Price Analytics

## Goal and working rules

Build the Northern Italy Airbnb analytics project on Databricks Free Edition, using Milan and Florence for training and Venice for unseen-city evaluation. All work must cost nothing.

Sources: [README.md](README.md) and [assignment instructions](group_assignment_2.pdf).

Implementation is under way on working branches. The responsibilities and milestone gates below remain the agreed plan.

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
6. Write predictions for every eligible listing to gold. Preserve excluded listings with a reason and no prediction.
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

## Yaropolk's current engineering status

- Feature 4 Job: three reported successful runs (Milan, Florence, Milan repeat). Post-repeat silver rows/distinct IDs: 25,338/25,338 and 13,571/13,571. Evidence: [run log](docs/pipeline_run_log.md).
- Feature 5: configuration-driven inputs implemented; Milan/Florence success recorded. User reports completing all runs, but repeat/external-manifest IDs and resolved Git SHA remain TODOs in the log.
- Feature 6: engineering/EDA and Nazar's model candidate integrated on a review branch; 99 local tests pass. Frozen scorer input resolution now matches ETL. Read-only workspace reconciliation and integrated scorer acceptance remain pending; follow [integration readiness](docs/integration_readiness.md).
- Shared-data access, integration into main and the joint code/model freeze must be confirmed with the team. Venice remains unseen. Week 2 work is not marked complete.
