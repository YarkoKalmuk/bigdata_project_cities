# M1 Week 1 freeze

**Verification: PASS.** All 100 local tests passed (zero skips), and all 24 live
workspace verification checks passed on 2026-11-11 UTC. The annotated release tag
is `M1-freeze`; its resolved commit will be recorded after successful publication.

## Code and execution identity

- Verified integrated source: `2ceb9c35e0a356bfc74b3e0f45260d596de3dbc1` on `main`.
- Release commit reference: `git rev-parse 'M1-freeze^{commit}'`.
- Workspace: `https://dbc-1766f78b-980d.cloud.databricks.com`, ID `7474659920821008`.
- Persistent Job: `airbnb-cities-etl`, ID **816607442908043**.
- Live Job Git source: **`f408ac01ffdd025fab6df220c8f89b24d3d4fda6`**, not a branch
  or mutable tag. The `airbnb`, notebook and source-config files at this revision
  match verified integrated main byte-for-byte. The main merge and subsequent
  verification documentation do not alter executable pipeline/model behaviour.
- The previously cited persistent Job `721102111883860` does not exist in this
  shared workspace. The correct Job was registered from the approved repository
  definition, without an automatic schedule. A/B acceptance runs were then started
  explicitly; both completed successfully (run IDs below).

The full [executed verification evidence](week1_freeze_verification.json) contains
SQL statement IDs, queries, counts, hashes, table versions, successful reference
run states, registered Job settings and source-file digests. Checks used actual
Databricks APIs and SQL; they are not inferred from notebook syntax or a teammate's
report. Only aggregates, metadata and hashes were retrieved. File contents and
row-level datasets were processed server-side, not downloaded.

## Data and model identity

Training snapshots: Milan and Florence, **2026-09-19**, EUR. Bronze, Silver and
gold feature counts are **25,338** and **13,571**, respectively, with unique keys.
All **38,909** feature rows have exactly one `price-v1` prediction. Gold city,
room-type and neighbourhood totals reconcile to those counts.

| Object | Frozen value |
|---|---|
| Model version | `price-v1` |
| Scoring / prediction schema | `score-v1` / `predictions-v1` |
| Selected model | `hgb_leaves_31_iter_400` (`hgb_log`) |
| Artifact | `/Volumes/workspace/airbnb_gold/model_artifacts/price-v1/model.joblib` |
| Artifact size | 1,484,150 bytes |
| Artifact SHA-256 | `c0416cde7f652342ce5217a936a6aa0a60d2476cc059c7e970b0c8001640fb2c` |
| Selection record SHA-256 | `9122ca565f036895a0b41fff61f1ac39bfa5066ea0a4ef8195bb8c0402af49db` |
| Model specification SHA-256 | `acd5e6e0e6a0badec0d34b4d2266c6485bba6135c679d92169db8a419992ea99` |
| MLflow run | `a08250c6bcb5415c9591c6427e3d6bf7` |
| Split / baseline version | `airbnb-v1` / `airbnb-v1` |
| Split fingerprint | `d4625414b6181cecf5de7548b376d77377b500b5e758f0a49236a356ae00a880` |
| Baseline fingerprint | `0ca4b685a4b85babccc0810105eb35c074b34808f28d1a54d4012149b987b65c` |

The model artifact and adjacent selection file were hashed inside Databricks and
matched the registered records and frozen code. Raw Milan/Florence files also
matched their recorded hashes. No artifact was retrained or changed.

The final live check found Bronze/Silver/features/metric tables at Delta **4**
after the two immutable-Job acceptance runs. Frozen model inputs were trained
from feature version **2**. Split, baseline, selection, candidate metrics,
artifact registry and evaluation remain **0**. Predictions are now Delta **2**
due to an `OPTIMIZE` operation; a server-side comparison of all 25 columns found
**zero row differences** from original prediction version **1**. No model or
prediction values changed. Do not overwrite the model, split or baseline to
reproduce the freeze.

## A/B held-out evaluation, reproduced live

Population: all persisted test rows with a valid positive nightly price. Errors
were recomputed server-side from stored actual/predicted values and reconciled
with `model_evaluation` and the frozen registry; no target-based tail filtering.

| Group | Test rows | Baseline MAE (EUR) | Model MAE (EUR) |
|---|---|---|---|
| Milan | 4,399 | 94.38 | 75.72 |
| Florence | 2,464 | 97.41 | 76.18 |
| Both | 6,863 | 95.47 | 75.88 |

Successful shared reference runs were also checked through the Jobs API:
Milan **399786082243961**, Florence **334832161613071**, Milan rerun
**768192587578562**. They are earlier submit runs, not new executions of the
registered persistent Job. New acceptance-run IDs are recorded separately; no
frozen model table or official prediction is rewritten by those ETL runs.

The registered immutable Job also completed both new acceptance runs, with all
four tasks successful and source revision `f408ac0…` confirmed:

| City | Run ID | Result |
|---|---|---|
| Milan | 27941700122958 | SUCCESS |
| Florence | 367666271706452 | SUCCESS |

All live data/hash/metric checks were repeated after these runs. The full local
suite was also rerun after the fixes: 100 passed, zero failures/skips (25.740 s).

## Necessary fixes made during verification

The authenticated user lacked Bronze/Silver schema access and volume-read rights.
After explicit user approval, `USE SCHEMA`, required table `SELECT`, and raw/model
`READ VOLUME` were granted. A final execution check found the Job also needed
writes. With separate explicit approval, `CREATE TABLE` on the three ETL schemas
and `MODIFY` on the eight ETL output/audit tables were added. No ownership or
grant-management right was added, and frozen model/prediction/reference tables
received no new write grants. The missing persistent Job was registered from the
approved immutable definition. No pipeline, model or source-config behaviour changed.

## Week 2 procedure

The shared `sources_config_path` interface is verified by synthetic tests for
both ETL and scorer 08; it needs configuration and a raw file, not a code edit.
The original feature 5 external-manifest run IDs remain historical TODOs; they
are not claimed as observed by this verification or substituted with older runs.

Once `M1-freeze` is published, retain that code and `price-v1`. For the first
unseen-city run, supply its immutable runtime JSON manifest and original raw file,
then pass the same manifest to the unchanged ETL Job and scorer. Override the
city/snapshot parameters; do not change the code or model. Record the first ETL
and scoring outcomes before any fixes, including failures. Any fixes must be
classified as pipeline fixes or model changes under a new recorded revision.

No unseen-city file, metadata, query or run was accessed for this freeze. No
Week 2 evaluation has started.
