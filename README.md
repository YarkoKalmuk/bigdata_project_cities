# Airbnb Price Analytics — Northern Italy

## Group Assignment 2

### Colaborators:
#### Kalmuk Yaropolk
#### Mykolaichuk Nazar
#### Matseliukh Maksym

Region: Northern Italy
Currency: EUR

### Cities
- City A: Milan (Training)
- City B: Florence (Training)
- City C: Venice (Unseen test)

### Dataset
Source: Inside Airbnb
File: Detailed listings.csv.gz

Snapshot dates:
- Milan: 19 September 2026
- Florence: 19 September 2026
- Venice: To be recorded in Week 2

### Project objective
Build a Databricks lakehouse, ETL pipeline,
Airbnb price prediction model, dashboard,
and Genie Agent.

Evaluate how well the system transfers
to an unseen city (Venice).

### Work plan and setup

Current release evidence: [M1 Week 1 freeze](docs/week1_freeze.md), including live
workspace checks, immutable Job identity, model hashes and held-out A/B results.
The feature-status notes below describe the earlier integration stages.

- [Three-person work plan](plan.md)
- [Databricks setup and bronze ingestion](docs/databricks_setup.md)
- [Lakehouse architecture](docs/architecture.md)
- [Silver listings contract and verification](docs/silver_contract.md)
- [Completed A/B EDA and cleaning handoff](docs/eda_handoff.md)
- [Gold metrics and model handoff](docs/gold_contract.md)
- [Parameterised Job setup and execution](docs/pipeline_job.md)
- [Pipeline run evidence](docs/pipeline_run_log.md)
- [Generic city inputs and engineering handoff](docs/engineering_handoff.md)
- [Integrated system and remaining freeze checks](docs/integration_readiness.md)
- [Model selection and held-out evaluation](docs/model_selection.md)
- [Prediction schema and run evidence](docs/model_predictions_run.md)

Yaropolk reports successful execution of the initial silver notebook. Maksym's
completed EDA records 25,338 Milan listings and 13,571 Florence listings for
2026-09-19, including 21,654 and 12,148 nonmissing prices respectively. These are
EDA observations, not results from the new gold pipeline.

The feature 4 Job completed Milan, Florence and a repeated Milan run. Reported
post-repeat silver counts are 25,338 / 13,571 with no duplicate listing keys.
Both source URLs and city centres are recorded in `config/sources.json`.

`yaropolk/feature5-city-inputs` removes hardcoded city restrictions and accepts
an optional runtime JSON manifest. Its A/B workspace acceptance is pending.
Venice stays unseen; the joint pipeline/model freeze is not complete.

`yaropolk/feature6-integration` combines the engineering/EDA line with Nazar's
price-v1 model candidate. Its 100 local tests pass. Scorer 08 now accepts runtime
input manifests alongside ETL; read-only notebook 09 helps reconcile model data,
workspace identity and reference versions before the joint freeze. Integration
workspace acceptance and merge into main are still pending.
