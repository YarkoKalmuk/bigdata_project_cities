# Week 2 repository integration review — 2026-11-12

Review scope: fetched repository/open PR heads, preserved evidence, offline metric
checks, synthetic tests and documentation. **No new Databricks verification,
Venice execution, model training, artifact write, tag change, PR merge or closure.**
The [machine-readable check record](integration_review.json) records source refs,
hash counts and checks. Workspace results are attributed to the preserved reports
and Nazar's 2026-11-11 audit, not claimed as newly executed here.

## Open PR disposition

| PR | Reviewed source / base | Findings | Recommendation |
|---|---|---|---|
| [#4](https://github.com/YarkoKalmuk/bigdata_project_cities/pull/4) | `nazar/week2-venice-model-first-run` @ `582aa9559f7a1633c8c999ba936c91c6bb2539ea` → main | GitHub CLEAN/MERGEABLE. Docs/evidence only, no executable/config change. Model metrics, hashes, protected-state comparisons, readonly audit and BI/model-slide handoffs present. Pipeline section was explicitly pending; this follow-up completes it. | **Safe to merge after approval**, preserving sealed evidence. No blocking model/pipeline finding. |
| [#2](https://github.com/YarkoKalmuk/bigdata_project_cities/pull/2) | `nazar/model-baseline` @ `f8e0eba4f5d94b1635ea8ffd5a3fdb67d84badf0` → old `yaropolk/feature4-pipeline` | GitHub CLEAN/MERGEABLE against its old base, but head is already an ancestor of main through PR #3. No unintegrated model commits. Its old target is misleading. | **No merge needed.** Close as integrated/superseded only after approval. |
| [#1](https://github.com/YarkoKalmuk/bigdata_project_cities/pull/1) | `nazar/project-plan` @ `9510d714961269b1971781cc9d4010c345b95722` → main | GitHub DIRTY/CONFLICTING. Overlaps `plan.md`; most statuses describe early Week 1, with only partial Week 2 updates. Claims such as nothing merged, Gold/model pending and hardcoded city dropdowns are obsolete; freeze definition links nonexistent CLAUDE.md. | **Do not merge as-is.** This follow-up retains task IDs/ownership and replaces stale status with evidence-backed completion/pending work. Review it, then close #1 as superseded after approval. |

`main` reviewed at `bb5b857` (full SHA in JSON); PR #3 is already merged. The
follow-up branch `yaropolk/week2-integration-handoff` starts at PR #4's exact head,
so it does not cherry-pick model commits, rewrite Nazar's branch or duplicate his
sealed evidence. Its intended PR base is `nazar/week2-venice-model-first-run` until
#4 lands. Only documentation/diagram changes belong in this follow-up.

## Recommended order — actions still require approval

1. Review PR #4 and this stacked follow-up together. Approve and merge **#4 into
   main first**. Retain its original indexed bytes and chronology.
2. Retarget the documentation follow-up to main after #4 lands. Recheck its diff,
   conflicts, hashes and unchanged frozen paths, then approve/merge it. This avoids
   competing edits to `plan.md`/`transfer_report.md` and duplicate evidence commits.
3. With confirmation that the integrated model and updated task board are present,
   approve closure of **#2 as already integrated** and **#1 as superseded**. Do not
   merge the old feature4 target or resolve #1 by overwriting the current board.
4. Maksym integrates his BI branch with the updated main, addresses the acceptance
   items below and opens a separate BI review. Merge only after reconciliation and
   approval; final deck/demo/submission follow. Do not re-freeze or move M1.

No merge/closure is performed by this recommendation. If any source head moves,
recheck the diff and evidence rather than relying on this dated review.

## Overlaps and documentation completeness

PR #4 supplies the authoritative model transfer analysis, artifact/run provenance,
reference SQL and model slides. This follow-up links those files, adds the missing
pipeline section, records FIX-01 **none / not required**, refreshes README/task
board, supplies PNG/SVG architecture and adds reproduction/engineering handoff.
Historical Week 1 operational docs are labelled so old instructions cannot be
mistaken for current acceptance tasks. Sealed ETL/model directories, their indexes,
frozen executables, runtime inputs, model artifacts and tag remain unchanged.

`origin/maksym/dashboard-genie` contains BI SQL/views, dashboard/Genie exports and
build scripts, and reported A/B deployment checks. There is no open BI PR at this
review. Its old branch point does not imply that all later main files should be
deleted; review changes from its merge base. Expect documentation overlaps and
reconcile against the current README/task board rather than replacing them.

Outstanding BI gaps found in those assets:

- Venice refresh and actual question/SQL/answer evidence still needed; earlier
  expected answers that Venice is absent predate its completed loading/scoring.
- Expose/filter `scoring_run_id` for the first Venice result; preserve `price-v1`,
  city/date and held-out/unseen filters. Never mix training errors into headline MAE.
- Reconcile 4–7/7+ BI distance groups versus Nazar's frozen 4–8/8+ reference groups.
- Neighbourhood enrichment for listing predictions requires the full-key Silver
  join and authorised read access; existing BI-owner access was insufficient.
- Final presentation PDF/link, viewer checks, rehearsal and admin submission are
  not present as completed deliverables.

These are **BI/presentation/integration tasks**, not pipeline failures or model
changes. Exact owner actions and acceptance outputs are in the
[engineering handoff](handoff_dashboard_genie_engineering.md).

## Validation

- **100 tests passed** (`unittest discover -s tests -q`, Python 3.12 / Java 21 /
  pinned test dependencies). Spark emitted socket ResourceWarnings; suite finished OK.
- **59/59 indexed evidence files match** their committed LF-byte SHA-256 hashes
  (25 ETL + 34 model). No first-run directory/index was rewritten.
- Counts/MAE arithmetic agree with stored metrics: 8,144 priced + 700 unpriced =
  8,844; 25.5447% improvement over baseline, 39.7753% gap versus A/B model MAE.
- Frozen executable/config paths and original M1 tag identity are unchanged;
  PR #2 ancestor check confirms it was already integrated.
- Updated-document local links, SVG XML and documentation whitespace are checked;
  architecture PNG visually inspected for clipping and legibility.

See [reproducibility](../reproducibility.md) for read-only result verification.
