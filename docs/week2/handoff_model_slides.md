# Model slides: outline for Maksym (presentation assembly)

Owner and presenter: Mykolaichuk Nazar. Every number is verified in the
[transfer report](transfer_report.md) and the
[first-run model report](venice_model_first_run_2026-09-16/REPORT.md).
Suggested chart sources are the queries in the [Dashboard/Genie handoff](handoff_dashboard_genie_model.md).

## Slide 1: The model beats the required baseline by 20.5 % on held-out Milan + Florence

- Split: 20 % of listings per city held out before any model choice (`airbnb-v1`, 38,909
  listings; 6,863 priced test rows).
- Baseline: training median by `room_type × accommodates`, falling back to `room_type`, then the
  overall median. Fitted on training rows only.
- Model `price-v1`: gradient-boosted trees on log price (`hgb_leaves_31_iter_400`, 16 features,
  no price-derived inputs). Chosen on training-only validation.
- Held-out MAE (EUR):

  | | Baseline | Model |
  |---|---:|---:|
  | Milan | 94.38 | 75.72 |
  | Florence | 97.41 | 76.18 |
  | **Milan + Florence** | **95.47** | **75.88** (−20.5 %) |

## Slide 2: Venice, an honest first run of the frozen solution

- Frozen at `M1-freeze` before Venice was touched. Only the city's config entry and raw file were
  added.
- ETL run 782550938914199 and scoring job run 65362888524059 both succeeded on the first
  attempt. All 8,844 listings were scored; 8,144 have a valid price.
- Side by side (EUR):

  | | Baseline MAE | Model MAE |
  |---|---:|---:|
  | Milan + Florence held-out | 95.47 | 75.88 |
  | Venice first run | 142.46 | **106.07** |

- Venice error is **39.8 % higher** (+30.18 EUR), but the model still beats the baseline by
  **25.5 %**.
- Chart: MAE by city, model vs baseline.

## Slide 3: Venice error is 40 % higher as expensive central listings dominate misses

- 66.6 % of Venice listings are underpredicted (A/B 44.0 %); mean residual −77 EUR.
- The €513+ band is 9.9 % of Venice listings (A/B 5.1 %) but produces **51 %** of Venice error.
- Within 1 km of San Marco: MAE 142.89 EUR, mean residual −113 EUR.
- Not the cause: 23.8 % of listings are beyond the frozen distance cap, yet those (mostly mainland)
  have MAE 40.70. The 18 truly unseen property types (MAE 193) are only 0.4 % of total error.
- 82 extreme-price listings make up about one fifth of total error.
- Chart: share of listings vs share of error by price band (A/B vs Venice).
- **Takeaway: the gap comes from Venice's price distribution and geography, not from a pipeline
  failure or unseen categories.**

## Slide 4: We chose not to adapt the model

- Pipeline fixes: **none**. Model changes: **none**.
- Why: the frozen pipeline and model completed, scored every listing, kept every contract and
  clearly beat the baseline. No defect was found; the gap is a market shift.
- We made no cosmetic change to show an "after" number. `price-v1` is the only model version.
- Secondary check (prices ≤ frozen A/B P99): model 80.95 vs baseline 114.10 EUR.

## Slide 5: Main limitation and next step

- Limitation: no feature captures a city's centre premium, so predictions are systematically low
  in an expensive historic centre. Distance from one point mixes canals, islands and the mainland.
- Next step (would be a model change): reserve a fixed Venice test set first. Then add a
  city-agnostic location-premium feature or recalibrate the price level, and report the result
  under a new `model_version`, separately from the first run.
