-- BI semantic layer for the AI/BI dashboard and the Genie Agent.
-- Owner: Matseliukh Maksym.
--
-- Read-only views over the gold (and, for listing attributes, silver) tables.
-- Nothing here is materialised and no pipeline table is modified, so the
-- frozen Week 1 pipeline/model stay untouched. A new city (e.g. city C) appears
-- automatically once the pipeline and scorer have written it.
--
-- Run each statement on a SQL warehouse (catalog `workspace`).
-- Statements are separated by lines containing only ';;' for the runner script.

CREATE SCHEMA IF NOT EXISTS workspace.airbnb_bi
COMMENT 'Dashboard/Genie views over airbnb_gold (read-only semantic layer)';
;;

-- City letters used in the assignment (A, B = training, C = new client).
CREATE OR REPLACE VIEW workspace.airbnb_bi.city_roles
COMMENT 'Maps pipeline city keys to assignment letters: A = Milan, B = Florence (training), C = Venice (unseen new client).'
AS SELECT * FROM VALUES
  ('milan',    'A', 'Milan',    'training'),
  ('florence', 'B', 'Florence', 'training'),
  ('venice',   'C', 'Venice',   'new client (unseen)')
AS t(city, city_letter, city_name, city_role);
;;

CREATE OR REPLACE VIEW workspace.airbnb_bi.city_metrics
COMMENT 'One row per city and snapshot. Prices in EUR. open_days_share_365 is the share of days open for booking, NOT occupancy.'
AS
SELECT r.city_letter, r.city_name, r.city_role, m.*
FROM workspace.airbnb_gold.city_metrics m
LEFT JOIN workspace.airbnb_bi.city_roles r USING (city);
;;

CREATE OR REPLACE VIEW workspace.airbnb_bi.room_type_metrics
COMMENT 'One row per city, snapshot and room_type. room_type_mix = share of the city''s listings. Prices in EUR.'
AS
SELECT r.city_letter, r.city_name, r.city_role, m.*
FROM workspace.airbnb_gold.room_type_metrics m
LEFT JOIN workspace.airbnb_bi.city_roles r USING (city);
;;

CREATE OR REPLACE VIEW workspace.airbnb_bi.neighbourhood_metrics
COMMENT 'One row per city, snapshot and neighbourhood. median_price_eur is NULL when fewer than 20 priced listings (meets_price_sample_minimum = false).'
AS
SELECT r.city_letter, r.city_name, r.city_role,
       m.city, m.snapshot_date,
       m.neighbourhood_cleansed AS neighbourhood,
       m.listings, m.priced_listings, m.median_price_eur, m.open_days_share_365,
       m.availability_observations, m.share_blocked, m.avg_review_score, m.hosts,
       m.share_multi_listing_hosts, m.meets_price_sample_minimum
FROM workspace.airbnb_gold.neighbourhood_metrics m
LEFT JOIN workspace.airbnb_bi.city_roles r USING (city);
;;

-- One row per listing (gold model_features: cleaned attributes, no raw/leaking columns).
-- Note: neighbourhood, name and coordinates live in silver; this layer reads gold only.
CREATE OR REPLACE VIEW workspace.airbnb_bi.listing_facts
COMMENT 'One row per listing and snapshot with cleaned attributes from gold model_features. price_eur is the advertised nightly price in EUR (null when missing/invalid). distance_band groups dist_center_km.'
AS
SELECT r.city_letter, r.city_name, r.city_role,
       f.city, f.snapshot_date, f.listing_id,
       f.room_type, f.property_type, f.accommodates, f.bedrooms, f.beds, f.bathrooms_n,
       f.dist_center_km,
       CASE WHEN f.dist_center_km IS NULL THEN 'unknown'
            WHEN f.dist_center_km < 1 THEN '0-1 km'
            WHEN f.dist_center_km < 2 THEN '1-2 km'
            WHEN f.dist_center_km < 4 THEN '2-4 km'
            WHEN f.dist_center_km < 7 THEN '4-7 km'
            ELSE '7+ km' END AS distance_band,
       f.minimum_nights, f.long_stay, f.has_reviews, f.review_scores_rating,
       f.host_is_superhost, f.price_eur, f.eligible_for_training
FROM workspace.airbnb_gold.model_features f
LEFT JOIN workspace.airbnb_bi.city_roles r USING (city);
;;

-- Predictions enriched with listing attributes, for error analysis.
CREATE OR REPLACE VIEW workspace.airbnb_bi.prediction_details
COMMENT 'Model and baseline predictions per listing. Honest error analysis uses is_evaluation_row = true (held-out test rows for A/B, all priced rows for an unseen city). signed_residual_eur < 0 means the model under-prices the listing.'
AS
SELECT f.city_letter, f.city_name, f.city_role,
       p.city, p.snapshot_date, p.listing_id, p.model_version,
       p.evaluation_split,
       p.evaluation_split IN ('test', 'unseen') AND p.absolute_error_eur IS NOT NULL AS is_evaluation_row,
       f.room_type, f.property_type, f.accommodates, f.bedrooms, f.dist_center_km, f.distance_band, f.long_stay,
       p.actual_price_eur, p.model_prediction_eur, p.baseline_prediction_eur,
       p.absolute_error_eur, p.signed_residual_eur,
       p.baseline_absolute_error_eur, p.baseline_signed_residual_eur,
       CASE WHEN p.signed_residual_eur < 0 THEN 'under-priced'
            WHEN p.signed_residual_eur > 0 THEN 'over-priced'
       END AS pricing_direction,
       try_divide(p.signed_residual_eur, p.actual_price_eur) AS relative_residual,
       concat('https://www.airbnb.com/rooms/', CAST(p.listing_id AS STRING)) AS listing_url,
       p.baseline_fallback_level, p.prediction_status,
       p.evaluation_exclusion_reason, p.scoring_run_id, p.scored_at
FROM workspace.airbnb_gold.predictions p
LEFT JOIN workspace.airbnb_bi.listing_facts f
       ON f.city = p.city AND f.snapshot_date = p.snapshot_date AND f.listing_id = p.listing_id;
;;

-- Headline model metrics, recomputed from the evaluation rows so that a new
-- city shows up without changing this file. For A and B these reproduce the
-- official `model_evaluation` (population test_all_valid_positive_price).
CREATE OR REPLACE VIEW workspace.airbnb_bi.model_scorecard
COMMENT 'MAE in EUR of model vs baseline on evaluation rows only. scope = one city, or A+B for both training cities together.'
AS
WITH e AS (
  SELECT * FROM workspace.airbnb_bi.prediction_details WHERE is_evaluation_row
),
per_city AS (
  SELECT model_version, city_letter, city_name AS scope, city_role, evaluation_split,
         count(*) AS n,
         avg(absolute_error_eur) AS model_mae_eur,
         avg(baseline_absolute_error_eur) AS baseline_mae_eur,
         median(absolute_error_eur) AS model_median_ae_eur,
         avg(signed_residual_eur) AS mean_signed_residual_eur
  FROM e GROUP BY ALL
),
ab AS (
  SELECT model_version, 'A+B' AS city_letter, 'Milan + Florence' AS scope, 'training' AS city_role, 'test' AS evaluation_split,
         count(*), avg(absolute_error_eur), avg(baseline_absolute_error_eur),
         median(absolute_error_eur), avg(signed_residual_eur)
  FROM e WHERE city_role = 'training' GROUP BY model_version
)
SELECT *, baseline_mae_eur - model_mae_eur AS improvement_eur,
       try_divide(baseline_mae_eur - model_mae_eur, baseline_mae_eur) AS improvement_share
FROM (SELECT * FROM per_city UNION ALL SELECT * FROM ab);
;;
