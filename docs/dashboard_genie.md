# Dashboard and Genie Agent

Owner: Matseliukh Maksym. Built on the frozen gold tables (`M1-freeze`, model `price-v1`): Milan and Florence snapshot 2026-09-19, Venice 2026-09-16 (first unchanged run). Nothing in the pipeline, model or sealed evidence was changed; the BI layer only reads.

| Object | Where |
|---|---|
| BI views (semantic layer) | `workspace.airbnb_bi.*`, source [`sql/bi_views.sql`](../sql/bi_views.sql) |
| AI/BI dashboard | *Airbnb Northern Italy - price analytics*, `/Users/matseliukh.pn@ucu.edu.ua/airbnb/`, id `01f1de0644501777bd4500edcbdfa820`, published with embedded credentials; source [`dashboard/build_dashboard.py`](../dashboard/build_dashboard.py) → [`airbnb_price_analytics.lvdash.json`](../dashboard/airbnb_price_analytics.lvdash.json) |
| Genie Agent | *Airbnb Northern Italy - price analyst*, space id `01f1de069377177f84042e25ff9f9e87`; source [`genie/build_genie_space.py`](../genie/build_genie_space.py) → [`genie_space.json`](../genie/genie_space.json) |

## Semantic layer (`workspace.airbnb_bi`)

| View | Grain | Built from |
|---|---|---|
| `city_roles` | city | constant: A = Milan, B = Florence (2026-09-19), C = Venice (2026-09-16) |
| `city_metrics`, `room_type_metrics`, `neighbourhood_metrics` | as in gold | gold metric tables + city letter |
| `listing_facts` | listing | `gold.model_features` + `neighbourhood_cleansed` from silver + `distance_band` |
| `prediction_details` | listing × model version | `gold.predictions` + listing attributes, `is_evaluation_row`, `price_band`, `pricing_direction`, `scoring_run_id` |
| `model_scorecard` | model × city (+ A+B) | evaluation rows of `prediction_details` |

- `is_evaluation_row` = `evaluation_split IN ('test', 'unseen')` with a non-null error: A/B held-out test rows, all priced Venice rows. Training rows never enter an error metric.
- Silver is joined on `(city, snapshot_date, listing_id)`, which is unique (row counts 25,338 / 13,571 / 8,844 unchanged after the join).
- Groups follow the frozen model report: `distance_band` 0–1 / 1–2 / 2–4 / 4–8 / 8+ km; `price_band` edges = A/B training quartiles and p95 (128, 174.6, 249, 513 €).
- The gold key is city/snapshot/listing/model version, so there is one scoring run per city and model; for Venice it is `venice-2026-09-16-price-v1-score-v1-first-run`.

### Reconciliation with the model handoff (Nazar's Q1–Q6), 2026-11-12

| Check | BI layer | Reference |
|---|---|---|
| Q1 MAE baseline / model | A+B 95.47 / 75.88 (n 6,863); Venice 142.46 / 106.07 (n 8,144); improvement 20.5 % / 25.5 % | same |
| Q2 Venice by room type | Entire home 6,336 rows, 113.17 / 152.32; Private room 1,762, 81.56 / 108.35 | same |
| Q3 Venice neighbourhoods | Cannaregio 1,458, 117.26, 19.8 %; San Marco 901, 178.08, 18.6 %; Castello 1,485, 104.18, 17.9 % | same |
| Q4 513+ € band | Venice 808 rows, 9.9 % of listings, MAE 541.16, 50.6 % of error; A/B 348, 5.1 %, 618.04, 41.3 % | same |
| Q5 Venice distance | 0–1 km 3,366, 142.89, −113.13; 8+ km 1,852, 40.70, −2.03 | same |
| Q6 largest misses | under: 1560209843287885749, 12,047 vs 370.82; over: 1722428384412839314, 620 vs 1,305.66 | same |

## Dashboard pages (titles state the finding)

1. **City overview** — "Venice is the priciest market (median 231 €/night), Florence 197 €, Milan 163 €; Milan is by far the biggest": KPI table for all three cities with snapshot dates, room-type mix, price distribution, most expensive and largest neighbourhoods.
2. **Milan vs Florence** — "Florence looks ~20 % pricier, but at the same distance from the centre Milan costs as much or more: Florence's premium is location": side-by-side table with differences, median price by room type, guests and distance to the Duomo (55 % of Florence's priced listings within 1 km vs 9 % of Milan's).
3. **Price model and city C** — "On Venice the frozen model's error is 40 % higher than on Milan/Florence, because expensive central listings dominate the misses; it still beats the baseline by 25 %": counters, the three required numbers side by side (baseline on C, model on A+B, model on C), model vs baseline per city, predicted vs actual, residual by price band, share of listings vs share of error, error by distance, Venice neighbourhoods, room types, largest misses per city.

There is no "after changes" number: no pipeline fix and no model change were required (see the [transfer report](week2/transfer_report.md)).

To rebuild: edit `build_dashboard.py`, run it, then import the JSON (Dashboards → Import) or `databricks lakeview update <id>` with the file as `serialized_dashboard`, and publish.

## Genie configuration — the tricks

- **Curated views, not raw tables:** seven narrow views with clean names; no raw, identifier or leaking columns are visible to Genie.
- **City letters in data:** every view has `city_letter`, so "City A/B/C" is a filter, not a guess; snapshot dates are in the instructions. For a city without rows Genie says it is not loaded instead of substituting another.
- **Pre-computed medians first:** the gold metric tables answer city / room type / neighbourhood medians (same population as the dashboard); `MEDIAN(price_eur)` from `listing_facts` only for other filters, never `AVG(price)`.
- **Honest model errors:** only `is_evaluation_row` and `price-v1`; never training rows; sign convention spelled out; groups need ≥ 20 listings; a residual is not called proof of mispricing.
- **Easy-to-misread definitions:** `open_days_share_365` is not occupancy; `share_multi_listing_hosts` is a share of listings.
- **Eight example SQL queries** (the three assignment questions, MAE per city, Venice vs A/B, Venice error by neighbourhood, city comparison, guests filter), seven sample questions, entity matching on city, room type, neighbourhood and bands.

## Verified answers (2026-11-12, via the Genie API)

| Question | Genie answer | Reference |
|---|---|---|
| What is the median price of entire homes in City A? | 169 € (22,309 listings) | `room_type_metrics`: 169 € |
| Which neighbourhoods in City B have the most listings? | Centro Storico 9,986; Campo di Marte 1,318; Rifredi 1,174; Isolotto Legnaia 593; Gavinana Galluzzo 500 | `neighbourhood_metrics`: same |
| Where does the model under-price listings the most? | San Marco, Venice: −148 € mean residual (901 listings); San Polo, Venice −137 €; Duomo, Milan −111 € | evaluation rows, neighbourhoods ≥ 20 listings |
| What is the model MAE for Venice? | 106.07 € vs baseline 142.46 € (8,144 listings), 25.5 % better | Nazar Q1: 106.07 |
| How much better is the model than the baseline in Milan and Florence combined? | 95.47 → 75.88 €, 20.5 % (6,863 test listings) | Nazar Q1 |
| Which Venice neighbourhood has the most underpriced listings by the model? | Cannaregio: 1,060 of 1,458 under-priced | Q3: Cannaregio largest error share |
| What is the median price in City C? | 231 € (8,844 listings) | `city_metrics`: 231 € |

Fallback for the demo if Genie is unavailable: the same questions as saved SQL are the example queries in [`genie_space.json`](../genie/genie_space.json); the answers above are their results.
