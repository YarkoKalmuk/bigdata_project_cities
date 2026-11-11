# Week 2 transfer report: Milan + Florence → Venice (REPORT-01)

Status: **model section final** (owner: Mykolaichuk Nazar, 2026-11-11). The pipeline section
belongs to Kalmuk Yaropolk; until he writes it, it only links his first-run evidence.

Every number comes from the preserved first-run evidence and was re-checked read-only on
2026-11-11 ([audit](venice_model_final_audit_2026-11-11/audit.json)). Nothing was retrained,
rescored or re-run for this report.

## Identifiers

| Item | Value |
|---|---|
| Frozen revision | tag `M1-freeze`, commit `7f76cbe6936e76fa3a7685ac90b40c1ce1c253df` |
| Model / scoring / baseline | `price-v1` / `score-v1` / `airbnb-v1` lookup (44 rows, fitted on A/B training rows only) |
| Artifact | `/Volumes/workspace/airbnb_gold/model_artifacts/price-v1/model.joblib`, SHA-256 `c0416cde…0fb2c`; MLflow run `a08250c6bcb5415c9591c6427e3d6bf7` |
| Venice snapshot | 2026-09-16 (A/B: 2026-09-19) |
| Venice ETL run | **782550938914199** (Job `816607442908043`, `TERMINATED/SUCCESS`) |
| Venice scoring run | Job run **65362888524059**, `scoring_run_id = venice-2026-09-16-price-v1-score-v1-first-run` |
| Gold output | `workspace.airbnb_gold.predictions` v3, 8,844 Venice rows, `evaluation_split = 'unseen'` |
| First-run evidence | [ETL](venice_first_run_2026-09-16/REPORT.md) (commit `bb5b857`), [model](venice_model_first_run_2026-09-16/REPORT.md) (commits `b89dba9`, `7ec51d6`) |

**Run-ID note.** A team message gave the ETL run as `7825509389114199`. That is a digit-entry
error: it has an extra `1` (16 digits instead of 15). The Jobs API says that run does not exist.
The verified run is `782550938914199`. The only places the wrong ID appears in the repository are
the two `freeze_checks_*.json` API records and the first-run model report, and all three state
that it does not exist. Nothing needed correcting, and the hashed first-run files were left
unchanged.

## Pipeline section (owner: Yaropolk)

*To be written by Yaropolk.* Facts already recorded in [his first-run report](venice_first_run_2026-09-16/REPORT.md):
one submission with no retries or repairs; all four tasks succeeded; 8,844 Venice rows reached
Bronze, Silver and `model_features`; A/B fingerprints were unchanged. The pipeline fix list is
empty (see the change classification below).

## Model section

### Headline: side by side

Population: A/B = frozen held-out test rows (`evaluation_split = 'test'`) with a valid positive
price. Venice = every Venice listing with a valid positive price (`evaluation_split = 'unseen'`;
8,144 of 8,844; 700 unpriced rows have predictions but no error).

| Population | n | Baseline MAE (EUR) | Model MAE (EUR) | Model vs baseline |
|---|---:|---:|---:|---:|
| Milan held-out | 4,399 | 94.38 | 75.72 | −19.7 % |
| Florence held-out | 2,464 | 97.41 | 76.18 | −21.8 % |
| **Milan + Florence held-out** | 6,863 | **95.47** | **75.88** | **−20.5 %** |
| **Venice, first unchanged run** | 8,144 | **142.46** | **106.07** | **−25.5 %** |
| Venice post-change | — | — | — | not applicable: no change made |

- Venice model MAE is **+30.18 EUR (+39.8 %)** above the A/B held-out MAE.
- The frozen model still beats the frozen baseline by **36.39 EUR (25.5 %)**, a larger relative
  gain than on A/B (20.5 %). It has the smaller error on 73.8 % of Venice listings.
- Secondary metric only (actual price ≤ the frozen A/B training P99 of 1,156.62 EUR; Venice
  n = 7,999): model **80.95** vs baseline **114.10** EUR (A/B test: 59.63 vs 78.24).

### Why Venice error is higher

Signed residual = prediction − actual. Negative = underprediction.

1. **The model underprices Venice.** 66.6 % of Venice listings are underpredicted (A/B 44.0 %).
   Mean residual is −77.09 EUR (A/B −27.23). The model carries A/B price levels into a more
   expensive market.
2. **The price distribution is shifted toward expensive listings.** The €513+ band is
   **9.9 %** of Venice listings vs **5.1 %** of A/B, yet it produces **50.6 %** of total Venice
   absolute error (model MAE 541.16, mean residual −518). Venice has 45.0 % of listings at ≥ 249 EUR
   (A/B 26.1 %). Within each band, Venice error is close to A/B error: −9.0 to +7.5 EUR in the four
   lower bands, and lower in the top band. Re-weighting the Venice band MAEs to the A/B band mix
   gives about 71.8 EUR, close to A/B's 75.88. *These bands are defined on the actual price, so
   this is a diagnostic decomposition, not a metric.*
3. **Geography: the historic centre is the problem.** Within 1 km of Piazza San Marco,
   MAE is **142.89 EUR** and mean residual **−113 EUR** (n = 3,366). Within 1–2 km: 107.76 / −88.
   The highest neighbourhood MAEs are San Marco (178), San Polo (165) and Dorsoduro (130).
   Cannaregio, San Marco and Castello together hold 56 % of total error.
4. **The distance cap is not the cause.** **23.8 %** of Venice listings (2,105 of 8,844) are
   beyond the frozen 7.07 km `dist_center_km` cap, mostly on the mainland. A/B has 1.5 % (Milan) and
   0.1 % (Florence). Those listings are predicted well: priced n = 1,912, MAE **40.70 EUR**, mean
   residual −2.08.
5. **Unseen categories are not the cause.** **18** listings have a property type never seen in
   A/B training. Their MAE is **193 EUR**, but they contribute only **0.4 %** of total error. All were
   mapped to `OTHER` as designed. 5 rows used the `room_type` baseline fallback. No row failed.
6. **The extreme tail.** **82** listings flagged by silver as `extreme_high`, `stale_high` or
   `high_tail` (up to 12,047 EUR) contribute **19.4 %** (about one fifth) of total absolute error.
   They stay in the headline population, as the rules require. Silver price classes are used here
   only as labels: they are target-derived and are never predictors or filters.

> **Conclusion: the transfer gap is driven mainly by the Venice price distribution and
> geography, not by pipeline failure or unseen categories.**

Venice's historic centre is more expensive than any A/B area of the same size and distance, and
Venice has twice A/B's share of €513+ listings. The model ranks Venice listings sensibly and
beats the baseline by more than on A/B, but its price level is too low.

Breakdowns and CSVs: [first-run model report §4](venice_model_first_run_2026-09-16/REPORT.md#4-metrics-population-all-8144-venice-listings-with-a-valid-positive-price).
Neighbourhood figures: [reference SQL results](venice_model_final_audit_2026-11-11/reference_sql_results.json) (query `q3`).

### Limitations

- The model has no feature that captures the Venice centre premium. `dist_center_km` measured
  from Piazza San Marco mixes canals, islands and the mainland, which A/B never covered.
- Signed bias is large (−77 EUR), so Venice price estimates are systematically low. This matters
  for any "underpriced listing" story in the dashboard or Genie.
- 700 unpriced Venice listings cannot be evaluated.
- The snapshot is 3 days earlier than A/B (2026-09-16 vs 2026-09-19).

## Change classification

| Category | Changes after the first run | Reason |
|---|---|---|
| **Pipeline fixes** (FIX-01) | **None** | The frozen ETL completed on the first submission, kept all 8,844 rows and every contract held. No defect was found that should have been handled from the start. |
| **Model changes** (FIX-02) | **None: not required** | The frozen model scored every listing, unseen categories and baseline fallbacks worked, all contracts were preserved, and it beats the frozen baseline by 25.5 %. The gap is a market-level shift, not a defect. |

The project brief allows unchanged post-run results when no fix is justified. No cosmetic
change was made to produce an "after" number. No Venice labels were used for adaptation, so no
Venice test set needed reserving. `price-v1` is the only model version. MLflow holds only the
frozen training run, and `predictions` has a single Venice `scoring_run_id`
([audit](venice_model_final_audit_2026-11-11/audit.json)).

**Future improvement (not done, would be a model change):** reserve a fixed Venice test set first,
then add a city-agnostic location-premium feature or recalibrate the price level on the remaining
Venice rows. Report the result under a new `model_version`, separately from this first run.
