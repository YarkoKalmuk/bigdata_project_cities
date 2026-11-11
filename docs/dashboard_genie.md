# Dashboard and Genie Agent

Owner: Matseliukh Maksym. Built on the Week 1 gold tables (`price-v1`, snapshot 2026-09-19); nothing in the pipeline or model was changed.

| Object | Where |
|---|---|
| BI views (semantic layer) | `workspace.airbnb_bi.*`, source [`sql/bi_views.sql`](../sql/bi_views.sql) |
| AI/BI dashboard | *Airbnb Northern Italy - price analytics*, `/Users/matseliukh.pn@ucu.edu.ua/airbnb/`, id `01f1de0644501777bd4500edcbdfa820`, published; source [`dashboard/build_dashboard.py`](../dashboard/build_dashboard.py) → [`airbnb_price_analytics.lvdash.json`](../dashboard/airbnb_price_analytics.lvdash.json) Rendering checked on screenshots of all three pages (2026-11-11). |
| Genie Agent | *Airbnb Northern Italy - price analyst*, space id `01f1de069377177f84042e25ff9f9e87`; source [`genie/build_genie_space.py`](../genie/build_genie_space.py) → [`genie_space.json`](../genie/genie_space.json) |

## Semantic layer (`workspace.airbnb_bi`)

Read-only views; a new city appears without code changes once the pipeline and scorer have written it.

| View | Grain | Built from |
|---|---|---|
| `city_roles` | city | constant: A = Milan, B = Florence, C = Venice |
| `city_metrics`, `room_type_metrics`, `neighbourhood_metrics` | as in gold | gold metric tables + city letter |
| `listing_facts` | listing | `gold.model_features` + `distance_band` |
| `prediction_details` | listing × model version | `gold.predictions` + listing attributes, `is_evaluation_row`, `pricing_direction` |
| `model_scorecard` | model × city (+ A+B) | evaluation rows of `prediction_details` |

`model_scorecard` reproduces the official `gold.model_evaluation` exactly (MAE 75.72 / 76.18 / 75.88 € vs baseline 94.38 / 97.41 / 95.47 €).

Why a separate schema: `airbnb_gold` belongs to the frozen Week 1 pipeline; BI views must not touch it. **Limitation:** the views read gold only — the BI owner has no access to `airbnb_silver` — so predictions carry room type, guests and distance to centre but not the neighbourhood name. With `SELECT` on `airbnb_silver.listings`, `prediction_details` can join `neighbourhood_cleansed`.

## Dashboard pages (titles state the finding)

1. **City overview** — "Florence is the pricier market (median 197 € vs 163 €/night), Milan the bigger one (25.3k vs 13.6k listings)": KPI table (listings, priced listings, hosts, median price, days open, blocked, reviews, multi-listing hosts), room-type mix, price distribution, most expensive and largest neighbourhoods.
2. **Milan vs Florence** — "Florence looks ~20 % pricier, but at the same distance from the centre Milan costs as much or more: Florence's premium is location": side-by-side table with differences, median price by room type, by guests, by distance to the Duomo. 55 % of Florence's priced listings are within 1 km of the centre vs 9 % of Milan's.
3. **Price model** — "The model beats the baseline by 20.5 % (MAE 75.9 € vs 95.5 €), but systematically under-prices luxury listings": headline counters, scorecard per city, predicted vs actual, residual by price band, share of error by price band (1 % of listings ≥ 1,000 € cause 26 % of the error), error by room type and distance, 40 most mis-priced listings.

City C: no change needed — after its pipeline + scorer run, Venice rows (`evaluation_split = 'unseen'`) show up in the scorecard and every model chart. Add Venice's colour only if it differs from `CITY_COLORS` in the builder.

To rebuild: edit `build_dashboard.py`, run it, then import the JSON (Dashboards → Import) or `databricks lakeview update <id> --serialized-dashboard ...`.

## Genie configuration — the tricks

- **Curated views, not raw tables:** seven narrow views with clean names; no raw, identifier or leaking columns are visible to Genie.
- **City letters in data:** every view has `city_letter`, so "City A/B/C" is a filter, not a guess. Instructions say to answer "not loaded yet" for Venice rather than substitute another city.
- **Pre-computed medians first:** Genie is told to use the gold metric tables for city / room type / neighbourhood medians (same population as the dashboard) and to compute `MEDIAN` from `listing_facts` only for other filters, never `AVG(price)`.
- **Honest model errors:** errors only from `is_evaluation_row = true`; sign convention for under- vs over-pricing spelled out; groups need ≥ 20 listings.
- **Definitions that are easy to get wrong:** `open_days_share_365` is not occupancy; `share_multi_listing_hosts` is a share of listings.
- **Six example SQL queries** (the three assignment questions + MAE vs baseline, city comparison, guests filter) and five sample questions; entity matching on city, room type, neighbourhood and distance band.

## Verified answers (2026-11-11, via the Genie API)

| Question | Genie answer | Reference |
|---|---|---|
| What is the median price of entire homes in City A? | 169 € (22,309 listings) | `room_type_metrics`: 169 € |
| Which neighbourhoods in City B have the most listings? | Centro Storico 9,986; Campo di Marte 1,318; Rifredi 1,174; Isolotto Legnaia 593; Gavinana Galluzzo 500 | `neighbourhood_metrics`: same |
| Where does the model under-price listings the most? | Milan centre (< 1 km): private rooms −184 € (23 listings), entire homes −104 € (387) | `prediction_details` evaluation rows: same |
| What is the median price in City C? | "Venice has not been loaded or scored yet" | correct (no Venice rows) |
| How occupied are Florence listings compared to Milan? | answers with days open (57.9 % vs 51.3 %), not an invented occupancy | `city_metrics` |
| What is the median price of 6-guest entire homes in Milan? | 249 € (1,538 listings) | `listing_facts` |
| What is the model error in Florence? | MAE 76 € vs baseline 97 € (2,464 test listings) | `model_evaluation`: 76.18 / 97.41 |
