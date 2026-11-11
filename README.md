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

- [Three-person work plan](plan.md)
- [Databricks setup and bronze ingestion](docs/databricks_setup.md)
- [Lakehouse architecture](docs/architecture.md)
- [Silver listings contract and verification](docs/silver_contract.md)
- [Completed A/B EDA and cleaning handoff](docs/eda_handoff.md)
- [Gold metrics and model handoff](docs/gold_contract.md)
- [Parameterised Job setup and execution](docs/pipeline_job.md)
- [Pipeline run evidence](docs/pipeline_run_log.md)

Yaropolk reports successful execution of the initial silver notebook. Maksym's
completed EDA records 25,338 Milan listings and 13,571 Florence listings for
2026-09-19, including 21,654 and 12,148 nonmissing prices respectively. These are
EDA observations, not results from the new gold pipeline.

The EDA-informed silver rules and gold metrics are implemented on
`yaropolk/feature3-eda-gold`; their Databricks execution is pending. Both source
URLs and city centres are recorded in `config/sources.json`. Venice stays unseen.

`yaropolk/feature4-pipeline` adds a version-controlled, serverless Databricks Job
definition and a registration notebook. Job execution evidence is pending; it
reuses the existing bronze/silver/gold notebooks and adds cross-layer validation.
