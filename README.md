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

Setup and bronze ingestion have been run in Databricks according to Yaropolk's
report. The repository does not yet contain run counts confirming both cities.
Milan's source URL is recorded in `config/sources.json`; Florence's URL and load
still need confirmation. No snapshot dates were changed by this code review.

The next feature adds conservative silver typing and quality flags. Its workspace
execution and EDA-driven cleaning decisions remain pending. Venice stays unseen.
