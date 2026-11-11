# EDA handoff — Milan and Florence (snapshot 2026-09-19)

Owner: Matseliukh Maksym. Full evidence: [`notebooks/eda_milan_florence.py`](../notebooks/eda_milan_florence.py) (rendered run: [`docs/eda_run.html`](eda_run.html)).
Venice was not loaded or explored.

## Dataset

| city | snapshot | source | rows (= listings) | with price | neighbourhoods |
|---|---|---|---|---|---|
| Milan | 2026-09-19 | https://data.insideairbnb.com/italy/lombardy/milan/2026-09-19/data/listings.csv.gz | 25,338 | 21,654 (85.5 %) | 87 |
| Florence | 2026-09-19 | https://data.insideairbnb.com/italy/toscana/florence/2026-09-19/data/listings.csv.gz | 13,571 | 12,148 (89.5 %) | 5 |

Grain: one row per listing per snapshot; key `(city, snapshot_date, id)`, `id` unique and non-null. 90 source columns.

## For Nazar — leakage (do NOT use as features)

| column | evidence |
|---|---|
| `price_quote_price_per_night` | equals `price` in 100 % of rows |
| `price_quote_total_price` | price × quoted nights |
| `price_quote_raw` | JSON containing the price and line items |
| `price_quote_checkin_date`, `price_quote_checkout_date` | describe the price quote; nights length reveals monthly pricing |
| `estimated_revenue_l365d` | = `estimated_occupancy_l365d` × `price` (ratio 1.000 ± 0.001) |
| `estimated_occupancy_l365d` | modelled outcome partly driven by price — exclude |
| ids / urls / `scrape_id` / `host_id` / `name` / `license` | identifiers, memorisation |

Use with care: `availability_*` (partly a consequence of price).

Useful, non-leaking signals found in EDA:
- `long_stay = minimum_nights >= 28` — proxy for monthly-priced listings (their `price` is ~45 % lower; 11 % of Milan, 5 % of Florence; agrees with the leaking `is_monthly_priced` flag for 99.5–99.7 % of priced rows).
- `room_type`, `accommodates`, `bedrooms`, `beds`, `bathrooms_n` + `bath_shared` (parsed from `bathrooms_text`), `dist_center_km`, review scores with `has_reviews` flag, `log1p(host_listings_count)`.
- City price level: Florence ≈ +20 % vs Milan within each room type.
- Target is right-skewed (median 164 / 198 €, max 88,100 €) → model `log(price)`.

Baseline cells: `Hotel room` / `Shared room` and `accommodates > 8` are tiny → fall back to room-type median, then city median.

## For Yaropolk — silver cleaning rules

1. CSV: `multiLine`, `escape='"'`, all strings, FAILFAST.
2. Trim; `''`, `'None'`, `'N/A'` → null (`host_verifications` is the literal string `None` in every row — Spark keeps it as a value).
3. Assert key `(city, snapshot_date, id)` unique and non-null.
4. `price_eur = try_cast(regexp_replace(price, '[$,]', '') AS DOUBLE)` — `$` symbol, but values are EUR.
5. Never delete rows in silver; add `exclusion_reason`:
   - `missing_price` — price null (MNAR: 95 % / 73 % of listings with `availability_365 = 0` have no price);
   - `invalid_price` — ≤ 0 or unparseable;
   - `extreme_high` — price > 3 × city p99 or price per guest > 1,000 €;
   - `stale_high` — price > city p99 and `number_of_reviews_ltm = 0`.
6. Numerics via `try_cast` (not `cast`) so a new city cannot crash the job.
7. `bathrooms_n` / `bath_shared` from `bathrooms_text` (`Half-bath` → 0.5); `bathrooms` is 100 % empty.
8. `t`/`f` → boolean; dates → date; `days_since_last_review` vs `snapshot_date`.
9. `has_reviews`; review scores imputed with **training** median (in the model step, not silver).
10. Cap `minimum_nights` at 365; `long_stay` flag.
11. `dist_center_km` from a per-city centre in `config/sources.json` (Milan Duomo 45.4642, 9.1900; Florence Duomo 43.7731, 11.2560).
12. Select columns by name and tolerate missing/extra columns. **14 columns are 100 % empty** in both cities: `neighborhood_overview, host_since, host_response_time, host_response_rate, host_acceptance_rate, host_thumbnail_url, host_neighbourhood, host_total_listings_count, host_verifications, neighbourhood, neighbourhood_group_cleansed, bathrooms, calendar_updated, instant_bookable`.

## Gold metrics (dashboard / Genie)

| metric | definition | population |
|---|---|---|
| `listings` | count distinct `id` | all |
| `priced_listings` | `exclusion_reason IS NULL` | modelling population |
| `median_price_eur` | median `price_eur` | priced, excluding `extreme_high` |
| `open_days_share_365` | avg(`availability_365`)/365 — "share of days open", not occupancy | all |
| `share_blocked` | share with `availability_365 = 0` | all |
| `avg_review_score` | avg `review_scores_rating` | ≥ 1 review |
| `hosts` | count distinct `host_id` | all |
| `share_multi_listing_hosts` | `calculated_host_listings_count >= 2` | all |
| `room_type_mix` | share by `room_type` | all |
| `neighbourhood_median_price` | median by `neighbourhood_cleansed`, ≥ 20 priced listings | priced |

Proposed tables: `gold.city_metrics`, `gold.neighbourhood_metrics`, `gold.room_type_metrics`, `gold.predictions`.

## Transfer risks written before seeing city C

1. Neighbourhood granularity differs (87 vs 5) — neighbourhood one-hots do not transfer.
2. Price level differs by city — a `city` feature has no value for a new city.
3. Monthly-pricing share differs (11 % vs 5 %).
4. Empty columns may be populated (or vice versa) in another snapshot.
5. Rare room types → unseen baseline cells.
