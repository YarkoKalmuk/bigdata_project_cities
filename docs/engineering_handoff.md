# Yaropolk's engineering handoff

Current next step: [feature 6 integration readiness](integration_readiness.md). Feature 5 has two recorded successful A/B runs; its repeat/external-manifest details still need recording. This handoff's input contract remains valid, and scorer 08 now accepts the same manifest path.

## Current status

- Setup, parameterised ingestion, EDA cleaning, gold metrics/model inputs, architecture and the four-task Job are implemented.
- Feature 4 ran successfully for both training cities and a Milan repeat. Reported post-repeat silver counts/unique IDs are Milan 25,338/25,338 and Florence 13,571/13,571.
- Feature 5 removes all notebook city allowlists and centralises metadata validation in `airbnb/inputs.py`. It is locally tested, including synthetic-city silver/gold processing. Its workspace acceptance remains pending.
- This branch preserves the model input schema and transformations. Nazar's model/split/prediction artifacts are not changed. His latest model branch records training profiling work, so confirm current access with him rather than assuming the earlier blocker remains.

## Runtime city input contract

Notebook widgets and Job parameters: `catalog`, `city`, `snapshot_date`, `source_path`, `source_url`, and **`sources_config_path`**. City is now a text widget. An existing saved dropdown might still appear in an old interactive session: run `dbutils.widgets.removeAll()` in a separate cell and rerun the notebook's parameter cell to recreate widgets. Do not remove Job-supplied parameters inside an automated run.

Blank `sources_config_path` uses `config/sources.json` from the Job's Git revision, preserving A/B defaults. A nonblank value must identify a JSON input under:

```text
/Volumes/<catalog>/airbnb_bronze/raw_files/config/<manifest-name>.json
```

The same path is passed to every task automatically. Use a uniquely named, immutable manifest per input set; never overwrite it during or after a recorded run. Its canonical JSON content hash and path are stored in `airbnb_gold.pipeline_validations`. The Job history records the actual code commit separately.

Manifest shape (placeholder only, not a real city/source):

```json
{
  "city_slug": {
    "snapshot_date": "YYYY-MM-DD",
    "source_url": "https://data.insideairbnb.com/.../city_slug/YYYY-MM-DD/data/listings.csv.gz",
    "centre_latitude": 0.0,
    "centre_longitude": 0.0
  }
}
```

Replace placeholders only when the team is allowed to obtain that city's inputs. The city key must match the source URL slug. Both coordinates may be omitted; distance then remains null with a quality flag. Partial, nonfinite or out-of-range coordinates fail validation. The selected snapshot must match the manifest; an empty date widget falls back to its configured date. The Job's existing date default is still September 19, so explicitly override it for other snapshots.

Blank source widgets derive the raw volume path and URL. Explicit values must agree with the manifest and the expected upload location:

```text
/Volumes/<catalog>/airbnb_bronze/raw_files/<city>/<snapshot_date>/listings.csv.gz
```

This interface performs no download or discovery. For the first unseen-city run, keep code pinned, upload the original raw file and runtime metadata only, and preserve the first outcome before any fixes. No unseen-city manifest or data has been created by this implementation.

## Finish workspace acceptance now, using A/B only

1. Pull `yaropolk/feature5-city-inputs`. Update the **existing Job's** Git branch and add `sources_config_path` with an empty default as described in [Job setup](pipeline_job.md).
2. Run Milan, Florence and Milan again with repository defaults. Record run IDs, resolved commit, counts and success; verify the known row totals and unique keys remain unchanged.
3. Copy the unchanged A/B `config/sources.json` to a uniquely named JSON file in the volume's `config` directory. Run Milan once with `sources_config_path` pointing to that file. This tests the frozen-code/runtime-input route without accessing a new city. Check the validation output includes its path/hash.
4. Verify Nazar can query `workspace.airbnb_gold.model_features` (or his agreed catalog). If separate workspaces are required, he can reproduce the same A/B pipeline there; do not share credentials. Confirm both teammates have actual table access before announcing the handoff.
5. Add the new run evidence to `docs/pipeline_run_log.md` and commit/push it.

For user-supplied results, record the evidence as reported rather than implying this local agent observed the workspace directly. All local tests use fixtures, not real city files.

## What remains after engineering acceptance

These tasks depend on the team and cannot be marked complete by preparing code:

- Integrate reviewed engineering/EDA and Nazar's final model branch into `main`, resolving shared documentation deliberately; do not overwrite his persisted splits or model versions.
- Record the full-system Git SHA/tag, Job definition, model artifact/version, model feature/split/baseline table versions and A/B held-out metrics. Use the actual Job run Git snapshot, not an assumed branch-tip revision.
- Pin the Job to the frozen Git **commit**, rerun A/B if the integrated revision changed executable code, and only then begin Week 2.
- After the freeze, obtain Venice input metadata/data and run frozen ETL plus Nazar's frozen scorer. Preserve the first logs/predictions/metrics and classify later fixes. Dashboard/Genie and presentation follow the shared plan.

Yaropolk's code contribution covers `airbnb/inputs.py`, `silver.py`, `gold.py`, `validation.py`, setup/ETL/validation/registration notebooks, Job definition, tests and engineering documentation. EDA belongs to Maksym; model training/evaluation/predictions belong to Nazar.
