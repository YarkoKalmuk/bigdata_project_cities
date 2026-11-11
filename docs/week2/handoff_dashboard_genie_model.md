# Handoff to Maksym: model results for the Dashboard and Genie

From: Mykolaichuk Nazar, 2026-11-11. Model `price-v1`, frozen at `M1-freeze`. Every expected
answer below was produced by running the query read-only on the live tables
([results with statement IDs](venice_model_final_audit_2026-11-11/reference_sql_results.json)).
Full analysis: [transfer report](transfer_report.md).

## 1. Table to use

**`workspace.airbnb_gold.predictions`**: one row per listing per `model_version`. There are no
gold views. Your `workspace.airbnb_bi.prediction_details` view (branch `maksym/dashboard-genie`)
reads the same table and is fine to use, but I cannot read `workspace.airbnb_bi` (no `USE SCHEMA`),
so I checked the gold queries below rather than your views. Please run Q1 against
`airbnb_bi.model_scorecard` and confirm the numbers match.

Always filter `model_version = 'price-v1'`. For Venice, also filter
`scoring_run_id = 'venice-2026-09-16-price-v1-score-v1-first-run'`. It is the only Venice run
today, and the filter keeps charts stable if a later version is ever added.

| Column | Meaning |
|---|---|
| `city`, `snapshot_date`, `listing_id` | Listing key (A/B 2026-09-19, Venice 2026-09-16) |
| `evaluation_split` | `train`, `test`, `excluded` (A/B); `unseen` (Venice) |
| `actual_price_eur` | Advertised nightly price; **null** when missing/invalid |
| `model_prediction_eur`, `baseline_prediction_eur` | Model and required baseline |
| `absolute_error_eur`, `baseline_absolute_error_eur` | \|prediction − actual\| |
| `signed_residual_eur`, `baseline_signed_residual_eur` | **prediction − actual** |
| `baseline_fallback_level` | `room_type_x_accommodates`, `room_type` or `overall` |

**Residual sign:** `signed_residual_eur = model_prediction_eur − actual_price_eur`. **Negative =
the model underpredicts** (listing is priced above what the model expects). Positive = overprediction.

## 2. Join keys for enrichment

- Room type, accommodates, `dist_center_km`: `workspace.airbnb_gold.model_features` on
  `(city, snapshot_date, listing_id)`.
- **Neighbourhood:** `workspace.airbnb_silver.listings` on `(city, snapshot_date, listing_id)` →
  `neighbourhood_cleansed`. To add neighbourhood metrics, then join
  `workspace.airbnb_gold.neighbourhood_metrics` on `(city, snapshot_date, neighbourhood_cleansed)`.

## 3. Required filters (do not skip)

| Chart population | Filter |
|---|---|
| Milan / Florence model performance | `evaluation_split = 'test'` |
| Venice model performance | `evaluation_split = 'unseen'` |
| Any error metric | `actual_price_eur IS NOT NULL` |

**Training rows also have error values filled in** (Milan 17,255 and Florence 9,684 `train` rows).
A chart without the split filter silently mixes in training error and makes the model look better.
Never show `train` errors as held-out performance. Never filter or colour by silver
`price_class` as if it were a model input: it is derived from the price.

## 4. Validated metrics

| Population | n | Baseline MAE (EUR) | Model MAE (EUR) | Mean residual | Underpredicted |
|---|---:|---:|---:|---:|---:|
| Milan test | 4,399 | 94.38 | 75.72 | −35.50 | 45.8 % |
| Florence test | 2,464 | 97.41 | 76.18 | −12.46 | 40.7 % |
| Milan + Florence test | 6,863 | **95.47** | **75.88** | −27.23 | 44.0 % |
| Venice unseen | 8,144 | **142.46** | **106.07** | −77.09 | 66.6 % |

Venice model MAE is +39.8 % above A/B. The model still beats the baseline by 25.5 % (A/B: 20.5 %).

## 5. Suggested charts and title

Model page title: **"Venice error is 40% higher as expensive central listings dominate misses."**

1. Actual vs predicted scatter, coloured by city (log axes help; test + unseen rows only).
2. MAE by city, model vs baseline (Q1).
3. Error by room type (Q2).
4. Error by Venice neighbourhood (Q3).
5. Error by actual-price band: share of listings vs share of error (Q4). This is the key chart:
   the €513+ band is 9.9 % of Venice listings but 50.6 % of its error.
6. Error by distance band (Q5). Use the frozen bands 0–1, 1–2, 2–4, 4–8, 8+ km; your current
   `listing_facts.distance_band` uses 4–7 / 7+, so its numbers will not match the report.
7. Largest under- and overpredictions (Q6), with a link to the listing.

## 6. Reference SQL

All queries start from this evaluation population:

```sql
WITH e AS (
  SELECT * FROM workspace.airbnb_gold.predictions
  WHERE model_version = 'price-v1'
    AND actual_price_eur IS NOT NULL
    AND ((city IN ('milan','florence') AND snapshot_date = DATE '2026-09-19' AND evaluation_split = 'test')
      OR (city = 'venice' AND snapshot_date = DATE '2026-09-16' AND evaluation_split = 'unseen'
          AND scoring_run_id = 'venice-2026-09-16-price-v1-score-v1-first-run'))
)
```

**Q1: headline MAE**, expected as in §4.

```sql
SELECT CASE WHEN grouping(city) = 1 THEN 'milan+florence' ELSE city END AS scope,
       count(*) AS n,
       round(avg(baseline_absolute_error_eur), 2) AS baseline_mae_eur,
       round(avg(absolute_error_eur), 2) AS model_mae_eur,
       round(avg(signed_residual_eur), 2) AS mean_residual_eur
FROM e WHERE city IN ('milan','florence') GROUP BY GROUPING SETS ((city), ())
UNION ALL
SELECT 'venice', count(*), round(avg(baseline_absolute_error_eur), 2),
       round(avg(absolute_error_eur), 2), round(avg(signed_residual_eur), 2)
FROM e WHERE city = 'venice'
```

**Q2: by room type.** Expected Venice: Entire home/apt 6,336 rows, model 113.17, baseline 152.32;
Private room 1,762, model 81.56, baseline 108.35. A/B: Entire home/apt 5,968, model 79.64;
Private room 868, model 50.96.

```sql
SELECT CASE WHEN e.city = 'venice' THEN 'venice' ELSE 'milan+florence' END AS population,
       f.room_type, count(*) AS n,
       round(avg(e.absolute_error_eur), 2) AS model_mae_eur,
       round(avg(e.baseline_absolute_error_eur), 2) AS baseline_mae_eur
FROM e JOIN workspace.airbnb_gold.model_features f USING (city, snapshot_date, listing_id)
GROUP BY 1, 2 ORDER BY 1, 3 DESC
```

**Q3: Venice neighbourhoods (n ≥ 20).** Expected top 3 by error share: Cannaregio 1,458 rows,
MAE 117.26, 19.8 % of error; San Marco 901, MAE 178.08, 18.6 %; Castello 1,485, MAE 104.18, 17.9 %.

```sql
SELECT s.neighbourhood_cleansed AS neighbourhood, count(*) AS n,
       round(avg(e.absolute_error_eur), 2) AS model_mae_eur,
       round(avg(e.signed_residual_eur), 2) AS mean_residual_eur,
       round(sum(e.absolute_error_eur) / max(t.total_error), 3) AS share_of_total_error
FROM e JOIN workspace.airbnb_silver.listings s USING (city, snapshot_date, listing_id)
CROSS JOIN (SELECT sum(absolute_error_eur) AS total_error FROM e WHERE city = 'venice') t
WHERE e.city = 'venice'
GROUP BY 1 HAVING count(*) >= 20 ORDER BY share_of_total_error DESC
```

**Q4: price bands.** The edges are the frozen A/B training quartiles and p95. Expected €513+:
Venice 808 rows, 9.9 % of listings, MAE 541.16, 50.6 % of error; A/B 348 rows, 5.1 %, MAE 618.04, 41.3 %.

```sql
, b AS (
  SELECT *, CASE WHEN city = 'venice' THEN 'venice' ELSE 'milan+florence' END AS population,
         CASE WHEN actual_price_eur < 128 THEN '1: <128'      WHEN actual_price_eur < 174.6 THEN '2: 128-174.6'
              WHEN actual_price_eur < 249 THEN '3: 174.6-249' WHEN actual_price_eur < 513 THEN '4: 249-513'
              ELSE '5: 513+' END AS price_band
  FROM e
)
SELECT population, price_band, count(*) AS n,
       round(count(*) / sum(count(*)) OVER (PARTITION BY population), 3) AS share_of_listings,
       round(avg(absolute_error_eur), 2) AS model_mae_eur,
       round(sum(absolute_error_eur) / sum(sum(absolute_error_eur)) OVER (PARTITION BY population), 3) AS share_of_total_error
FROM b GROUP BY 1, 2 ORDER BY 1, 2
```

(This continues the `WITH e AS (...)` clause above, hence the leading comma.)

**Q5: Venice distance bands.** Expected 0–1 km: 3,366 rows, MAE 142.89, mean residual −113.13;
8+ km: 1,852 rows, MAE 40.70, −2.03.

```sql
SELECT CASE WHEN f.dist_center_km < 1 THEN '1: 0-1 km' WHEN f.dist_center_km < 2 THEN '2: 1-2 km'
            WHEN f.dist_center_km < 4 THEN '3: 2-4 km' WHEN f.dist_center_km < 8 THEN '4: 4-8 km'
            ELSE '5: 8+ km' END AS distance_band,
       count(*) AS n, round(avg(e.absolute_error_eur), 2) AS model_mae_eur,
       round(avg(e.signed_residual_eur), 2) AS mean_residual_eur
FROM e JOIN workspace.airbnb_gold.model_features f USING (city, snapshot_date, listing_id)
WHERE e.city = 'venice' GROUP BY 1 ORDER BY 1
```

**Q6: largest misses.** Expected worst underprediction: listing 1560209843287885749, actual
12,047, predicted 370.82, residual −11,676.18. Worst overprediction: 1722428384412839314,
actual 620, predicted 1,305.66, residual +685.66.

```sql
(SELECT 'underprediction' AS kind, listing_id, actual_price_eur, model_prediction_eur, signed_residual_eur
 FROM e WHERE city = 'venice' ORDER BY signed_residual_eur ASC LIMIT 10)
UNION ALL
(SELECT 'overprediction', listing_id, actual_price_eur, model_prediction_eur, signed_residual_eur
 FROM e WHERE city = 'venice' ORDER BY signed_residual_eur DESC LIMIT 10)
```

## 7. Genie instructions to add

- "Model error questions use `airbnb_gold.predictions` with `model_version = 'price-v1'` and
  `actual_price_eur IS NOT NULL`. Milan/Florence: `evaluation_split = 'test'`. Venice:
  `evaluation_split = 'unseen'`. Never report errors from `train` rows as model performance."
- "`signed_residual_eur` = prediction − actual. Negative means the model underpredicts the price;
  an 'underpriced by the model' listing has a negative residual."
- "The required baseline is `baseline_prediction_eur` (training median by room type and
  accommodates). Compare model and baseline on the same rows."

Example check questions: "What is the model MAE for Venice?" (106.07), "How much better is the
model than the baseline in Milan and Florence combined?" (95.47 → 75.88, 20.5 %), "Which
Venice neighbourhood has the most underpriced listings by the model?" (validate with Q3 or Q6).
