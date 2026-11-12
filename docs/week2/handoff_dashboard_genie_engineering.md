# Final engineering handoff to Maksym

Prepared by Yaropolk, 2026-11-12. ETL/model work is complete. This handoff changes
no workspace objects. A/B dashboard/Genie deployment is reported in
`origin/maksym/dashboard-genie:docs/dashboard_genie.md`; Venice acceptance and BI
repository integration remain pending, not independently verified in this review.

## Ready inputs

Use `workspace.airbnb_gold`: `city_metrics`, `room_type_metrics`,
`neighbourhood_metrics`, `model_features`, `predictions`. Definitions and grains:
[Gold contract](../gold_contract.md), [architecture](../architecture.md).
Use [Nazar's model handoff](handoff_dashboard_genie_model.md) for authoritative
Q1–Q6 reference SQL, model joins, results, populations and plot guidance.

| City | Snapshot | All listing rows | Role |
|---|---|---:|---|
| Milan | 2026-09-19 | 25,338 | A/B training + held-out |
| Florence | 2026-09-19 | 13,571 | A/B training + held-out |
| Venice | 2026-09-16 | 8,844 | Unseen; first run, no adaptation |

Nazar's 2026-11-11 audit records `model_features` v5 and `predictions` v3. Reference
split/baseline/artifact/evaluation tables remain v0. These are recorded historical
versions, not a new live check. Venice city/room/neighbourhood metric rows are
1/4/60. The Gold analytical count is **8,101**, whereas headline MAE includes all
**8,144** positive-price rows, including price tails. **700** unpriced listings
remain visible and predicted, with null errors. Do not substitute analytical
eligibility for model evaluation eligibility.

## Reconcile the existing BI branch before final acceptance

1. Refresh BI views from current Gold and preserve A/B results. The branch defines
   `workspace.airbnb_bi` views `city_roles`, `city_metrics`, `room_type_metrics`,
   `neighbourhood_metrics`, `listing_facts`, `prediction_details`, `model_scorecard`.
   Update display titles/instructions for three cities; remove obsolete *expected
   answers* that say Venice is not loaded. Keep a conditional no-data response
   for genuinely absent inputs. Add the distinct Venice snapshot date.
2. Pin model charts to `price-v1`; A/B use `evaluation_split = 'test'`, Venice
   uses `'unseen'`, with nonnull errors. Expose `scoring_run_id` in the BI view
   (currently omitted), or filter the underlying Gold query, so Venice selects
   `venice-2026-09-16-price-v1-score-v1-first-run`. Do not alter frozen tables.
   Baseline/model errors must use identical priced rows; no training-row MAE.
3. The branch's distance groups are **0–1 / 1–2 / 2–4 / 4–7 / 7+ km**, while
   Nazar's reference diagnostics use **0–1 / 1–2 / 2–4 / 4–8 / 8+ km**. Align the
   BI diagnostic groups to the reference SQL or label the difference explicitly;
   never compare unlike groups as if equal. This is a BI change, not FIX-01/02.
4. `prediction_details` lacks neighbourhood enrichment because its BI owner
   previously lacked Silver access. Coordinate minimal read access with the
   owner if needed; join Silver on **city + snapshot_date + listing_id**, avoiding
   fan-out. No grants were changed by this review. Gold neighbourhood metrics
   already support aggregate neighbourhood views without this listing join.
5. Label the city Gold median separately from exact prediction-population medians.
   The ETL approximate Venice parsed-price median is about EUR 231; the model
   report's exact median is EUR 231.34. Follow each metric's population definition.
   Availability means open calendar days, never occupancy. Host-share metrics are
   listing-weighted. Preserve low-sample neighbourhood median suppression.

Reported existing deployment IDs (verify access; not redeployed here):
Dashboard `01f1de0644501777bd4500edcbdfa820`; Genie
`01f1de069377177f84042e25ff9f9e87`. Keep assets/export scripts and SQL in the BI
review; do not copy or edit sealed model/ETL evidence to update the dashboard.

## Acceptance evidence to return

- Dashboard export/link and screenshots for overview, A/B comparison and model
  transfer pages, with visible city/date/model/population filters.
- Counts reconcile to the table above. Held-out A/B MAE is **95.47 / 75.88 EUR**
  (baseline/model); unseen Venice is **142.46 / 106.07 EUR**, n = **8,144**.
  Improvement is **25.5%**, with model MAE **39.8%** above A/B. No post-fix metric
  exists because neither a pipeline fix nor a model change was required.
- Predicted-vs-actual, error-by-group and under/overpricing charts reconcile with
  Nazar's Q1–Q6; residual = prediction − actual, negative means underprediction.
  Avoid describing residuals as proof a listing is objectively mispriced.
- Genie question / reference SQL / actual answer / date recorded for all required
  examples, including Venice price, neighbourhood counts and model underpricing.
  Confirm permissions using the intended viewer account and rehearse a fallback
  to saved SQL/screenshots if Genie is unavailable.
- Reviewed BI PR rebased/integrated with current main after approved PR #4 and
  documentation follow-up; no frozen pipeline/model/evidence changes.

## Engineering presentation material

Use [architecture PNG](../architecture.png) or [SVG](../architecture.svg).
Yaropolk supplies/presents these engineering points; Maksym assembles the deck:

1. **One configured pipeline:** raw detailed gzip → Bronze strings → typed Silver
   with explicit flags → Gold metrics/features; listing key includes city/date.
   Separate runtime manifest added Venice without code edits.
2. **A genuine first attempt:** immutable M1-compatible Job source; ETL run
   `782550938914199`; four successful tasks, 8,844 rows at every layer; 19
   protected A/B/model fingerprints unchanged. No pipeline fix required.
3. **Honest transfer:** 700 missing prices retained, 8,101 analytical vs 8,144
   evaluation rows, price/distance shifts observed. Separate first model run and
   frozen artifact. Link the [joint report](transfer_report.md) and sealed evidence.

Combine these with [Nazar's model slides](handoff_model_slides.md), Maksym's EDA
and dashboard/Genie demo. Final deck/PDF, each member's delivery, rehearsal, access
checks and team-admin submission are still pending. Do not claim new live
verification or a second Venice run to complete the presentation.
