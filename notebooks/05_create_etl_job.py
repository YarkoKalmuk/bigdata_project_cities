# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "6"
# ///
# MAGIC %md
# MAGIC # Register the version-controlled ETL Job
# MAGIC Run manually once after pulling this branch. Creates the Job only; it does
# MAGIC not start processing. An existing same-name Job is never silently replaced.

# COMMAND ----------

import json
from pathlib import Path

from databricks.sdk import WorkspaceClient
from databricks.sdk.service import jobs

root = next((p for p in [Path.cwd(), *Path.cwd().parents] if (p / "jobs/airbnb_etl.job.json").is_file()), None)
if root is None:
    raise ValueError("Open this notebook in the project Git folder.")
settings = json.loads((root / "jobs/airbnb_etl.job.json").read_text())
client = WorkspaceClient()
existing = list(client.jobs.list(name=settings["name"]))
if existing:
    raise ValueError(f"A Job with this name already exists: {[j.job_id for j in existing]}. Open it in Jobs & Pipelines; do not create a duplicate.")
response = client.jobs.create(
    name=settings["name"],
    description=settings["description"],
    tasks=[jobs.Task.from_dict(task) for task in settings["tasks"]],
    parameters=[jobs.JobParameterDefinition.from_dict(parameter) for parameter in settings["parameters"]],
    git_source=jobs.GitSource.from_dict(settings["git_source"]),
    max_concurrent_runs=settings["max_concurrent_runs"],
    queue=jobs.QueueSettings.from_dict(settings["queue"]),
    timeout_seconds=settings["timeout_seconds"],
    tags=settings["tags"],
)
print(f"Created Job {response.job_id}: {settings['name']}. Open Jobs & Pipelines to run it with city parameters.")