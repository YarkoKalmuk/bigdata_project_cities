# Week 1 repository review and proposed merge order

This review changes repository files only. No branches were merged, no freeze tag
was created, no live Job was changed, and no unseen-city input was accessed.

## Requirement audit

| Requirement | Finding | Action |
|---|---|---|
| Configurable cities in notebooks 01–03 | Already satisfied by feature 5: text widgets and shared `airbnb.inputs` resolution; the Milan defaults are not city allowlists | No notebook rewrite; retain existing synthetic-city tests |
| Immutable Job source | Missing: Job JSON still used `git_branch` | Replace with full `git_commit` `f408ac01ffdd025fab6df220c8f89b24d3d4fda6`; add a regression check forbidding branch/tag sources |
| Shared-workspace run IDs | Missing from the primary pipeline log, already present in Nazar's baseline evidence | Add Milan `399786082243961`, Florence `334832161613071`, rerun `768192587578562` as shared reference submit runs; preserve other reported runs separately |
| Windows-breaking scratch filename | Already removed from the current tree: feature 5 renamed it to `notebooks/testing.ipynb` | No second deletion; keep the useful verification query |
| Pipeline/model integration branch | Already satisfied by feature 6 and draft PR #3 | Amend that PR's branch only; do not open another integration PR |

The pinned commit is already published and contains the current executable task
code, generic city input interface and integrated scorer. The follow-up fixes
change only Job settings, regression tests and documentation. Pinning that earlier
commit avoids an impossible self-reference to the commit containing the pin. It
is not a final freeze or an authorization to deploy it.

The three shared runs used pipeline revision `504278b`; they do not certify the
newer runtime-manifest interface. Feature 5's resolved SHA, repeat-run details and
external-manifest evidence remain TODOs rather than being fabricated from older
runs. See [pipeline evidence](pipeline_run_log.md).

Validation: all **100 combined tests passed**, with no skips. The four pinned
notebook blobs match the current task files byte-for-byte. Tracked notebook names,
Python syntax and internal documentation links also passed checks.

## Existing PRs and ancestry

- [PR #3](https://github.com/YarkoKalmuk/bigdata_project_cities/pull/3):
  `yaropolk/feature6-integration` → `main`, draft. The branch contains both
  feature 5 at `7ddaa74` and Nazar's model branch at `f8e0eba`. This is the
  consolidated engineering/EDA/model candidate.
- [PR #2](https://github.com/YarkoKalmuk/bigdata_project_cities/pull/2):
  `nazar/model-baseline` → `yaropolk/feature4-pipeline`. Its head is already an
  ancestor of PR #3; merging it separately is unnecessary for the proposed route.
- [PR #1](https://github.com/YarkoKalmuk/bigdata_project_cities/pull/1):
  `nazar/project-plan` → `main`, documentation only. Its status snapshot predates
  most completed work. Reconcile its useful task-board additions with the current
  plan rather than restoring outdated blockers/statuses.

## Safe order — proposal only, approval required

1. Review PR #3 with these fixes and passing combined tests. Retain draft status
   until the team has reconciled the recorded workspace evidence and verified the
   integrated scorer's manifest route as described in
   [integration readiness](integration_readiness.md). These are runtime acceptance
   gates, not a reason to repeat already completed repository implementation.
2. After explicit merge approval, merge **PR #3 into main once**, preferably with
   a merge commit to preserve the existing teammate commits. Do not first merge
   features 1–5 or PR #2 independently; their relevant work is already included.
3. After that merge, treat PR #2 as superseded (close/reconcile with Nazar rather
   than merging its model back into feature 4). Reconcile PR #1 against integrated
   main and review the updated documentation before any separate merge.
4. Only with separate explicit approval, record the final code/model freeze and
   approve deployment of the exact intended Git commit to the correct shared
   workspace Job. No moving branch should be substituted. Keep the final Job
   settings, artifact identity and run evidence together.
5. Only after the approved Week 1 freeze may the unseen-city metadata/raw input
   be obtained and the first unchanged run begin.

PR states and ancestry above were inspected during this repository-only review;
recheck them if a teammate pushes new commits before the approved merge.
