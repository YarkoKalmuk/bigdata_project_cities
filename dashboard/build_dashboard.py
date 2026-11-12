"""Build the AI/BI (Lakeview) dashboard definition from code.

Usage:  python dashboard/build_dashboard.py
Writes  dashboard/airbnb_price_analytics.lvdash.json

The file can be imported in Databricks (Dashboards > Create > Import) or sent to
the Lakeview API. All datasets read the read-only views in `workspace.airbnb_bi`
(see sql/bi_views.sql), so a new city appears without editing this file.
Owner: Matseliukh Maksym.
"""
import json
from pathlib import Path

BI = "workspace.airbnb_bi"
CITY_COLORS = {"Milan": "#2A6FDB", "Florence": "#E07B39", "Venice": "#2E9E6A"}

datasets = []
pages = []


def dataset(name, display, sql):
    datasets.append({"name": name, "displayName": display, "queryLines": [sql.strip()]})
    return name


def city_color(field="city_name"):
    return {
        "fieldName": field,
        "scale": {
            "type": "categorical",
            "mappings": [{"value": k, "color": v} for k, v in CITY_COLORS.items()],
        },
        "displayName": "City",
    }


class Page:
    def __init__(self, name, title):
        self.page = {"name": name, "displayName": title, "pageType": "PAGE_TYPE_CANVAS", "layout": []}
        pages.append(self.page)
        self.n = 0

    def _add(self, widget, x, y, w, h):
        self.page["layout"].append({"widget": widget, "position": {"x": x, "y": y, "width": w, "height": h}})

    def _name(self):
        self.n += 1
        return f"{self.page['name']}_w{self.n}"

    def text(self, lines, x, y, w, h):
        # Lines are concatenated as-is, so each paragraph needs its own blank line.
        md = [l + "\n\n" for l in lines[:-1]] + lines[-1:]
        self._add({"name": self._name(), "multilineTextboxSpec": {"lines": md}}, x, y, w, h)

    def chart(self, ds, fields, spec, x, y, w, h):
        widget = {
            "name": self._name(),
            "queries": [{
                "name": "main_query",
                "query": {
                    "datasetName": ds,
                    "fields": [{"name": f, "expression": f"`{f}`"} for f in fields],
                    "disaggregated": True,
                },
            }],
            "spec": spec,
        }
        self._add(widget, x, y, w, h)


def frame(title, description=None):
    f = {"showTitle": True, "title": title}
    if description:
        f["showDescription"] = True
        f["description"] = description
    return f


def bar(x, y, title, desc=None, color=None, x_type="categorical", y_type="quantitative", stack=None, horizontal=False):
    enc = {
        "x": {"fieldName": x[0], "scale": {"type": x_type}, "displayName": x[1]},
        "y": {"fieldName": y[0], "scale": {"type": y_type}, "displayName": y[1]},
    }
    if horizontal:
        enc["x"], enc["y"] = (
            {"fieldName": y[0], "scale": {"type": y_type}, "displayName": y[1]},
            {"fieldName": x[0], "scale": {"type": x_type, "sort": {"by": "x-reversed"}}, "displayName": x[1]},
        )
    if color:
        enc["color"] = color
    spec = {"version": 3, "widgetType": "bar", "encodings": enc, "frame": frame(title, desc)}
    if stack:
        spec["mark"] = {"layout": stack}
    return spec


def table(columns, title, desc=None):
    return {
        "version": 2,
        "widgetType": "table",
        "encodings": {"columns": [{"fieldName": c, "displayName": d} for c, d in columns]},
        "frame": frame(title, desc),
    }


def counter(field, label, title, desc=None):
    return {
        "version": 2,
        "widgetType": "counter",
        "encodings": {"value": {"fieldName": field, "displayName": label}},
        "frame": frame(title, desc),
    }


# --------------------------------------------------------------------------
# Datasets
# --------------------------------------------------------------------------
# Model datasets: evaluation rows only (A/B held-out test, Venice unseen), price-v1.
EVAL = "is_evaluation_row AND model_version = 'price-v1'"
POP = "CASE WHEN city_role = 'training' THEN 'Milan + Florence (test)' ELSE concat(city_name, ' (unseen)') END"

ds_city = dataset("city_kpis", "City KPIs", f"""
SELECT city_letter, city_name, city_role, snapshot_date,
       listings, priced_listings, hosts,
       round(median_price_eur, 0)                AS median_price_eur,
       round(100 * open_days_share_365, 1)       AS open_days_pct,
       round(100 * share_blocked, 1)             AS blocked_pct,
       round(avg_review_score, 2)                AS avg_review_score,
       round(100 * share_multi_listing_hosts, 1) AS multi_host_listings_pct
FROM {BI}.city_metrics
ORDER BY city_letter""")

ds_room = dataset("room_mix", "Room-type mix and price", f"""
SELECT city_letter, city_name, city_role, room_type, listings,
       round(100 * room_type_mix, 1) AS share_pct,
       round(median_price_eur, 0)    AS median_price_eur
FROM {BI}.room_type_metrics""")

ds_room_ab = dataset("room_mix_ab", "Room-type price, A vs B", f"""
SELECT city_name, room_type, round(median_price_eur, 0) AS median_price_eur
FROM {BI}.room_type_metrics WHERE city_role = 'training'""")

ds_neigh = dataset("neighbourhood_prices", "Most expensive neighbourhoods", f"""
SELECT city_name, concat(neighbourhood, ' (', city_letter, ')') AS neighbourhood_label,
       listings, priced_listings, round(median_price_eur, 0) AS median_price_eur
FROM {BI}.neighbourhood_metrics
WHERE meets_price_sample_minimum
QUALIFY row_number() OVER (PARTITION BY city ORDER BY median_price_eur DESC) <= 6""")

ds_neigh_count = dataset("neighbourhood_counts", "Listings per neighbourhood", f"""
SELECT city_name, concat(neighbourhood, ' (', city_letter, ')') AS neighbourhood_label, listings,
       round(100 * listings / sum(listings) OVER (PARTITION BY city), 1) AS share_of_city_pct
FROM {BI}.neighbourhood_metrics
QUALIFY row_number() OVER (PARTITION BY city ORDER BY listings DESC) <= 6""")

ds_price_band = dataset("price_bands", "Price distribution", f"""
SELECT city_name,
       CASE WHEN price_eur < 50 THEN '01: <50'
            WHEN price_eur < 100 THEN '02: 50-99'
            WHEN price_eur < 150 THEN '03: 100-149'
            WHEN price_eur < 200 THEN '04: 150-199'
            WHEN price_eur < 300 THEN '05: 200-299'
            WHEN price_eur < 500 THEN '06: 300-499'
            WHEN price_eur < 1000 THEN '07: 500-999'
            ELSE '08: 1000+' END AS price_band,
       round(100 * count(*) / sum(count(*)) OVER (PARTITION BY city_name), 1) AS share_pct
FROM {BI}.listing_facts
WHERE price_eur > 0
GROUP BY ALL""")

ds_compare = dataset("ab_comparison", "Florence vs Milan", f"""
WITH m AS (SELECT * FROM {BI}.city_metrics WHERE city = 'milan'),
     f AS (SELECT * FROM {BI}.city_metrics WHERE city = 'florence')
SELECT metric,
       format_number(milan, d) AS milan,
       format_number(florence, d) AS florence,
       format_number(florence - milan, d) AS difference,
       concat(format_number(100 * (florence - milan) / milan, 1), ' %') AS difference_pct
FROM (
  SELECT 'Listings' AS metric, 1 AS o, 0 AS d, CAST(m.listings AS DOUBLE) AS milan, CAST(f.listings AS DOUBLE) AS florence FROM m, f
  UNION ALL SELECT 'Hosts', 2, 0, m.hosts, f.hosts FROM m, f
  UNION ALL SELECT 'Median price, EUR', 3, 1, round(m.median_price_eur, 1), round(f.median_price_eur, 1) FROM m, f
  UNION ALL SELECT 'Days open for booking, %', 4, 1, round(100 * m.open_days_share_365, 1), round(100 * f.open_days_share_365, 1) FROM m, f
  UNION ALL SELECT 'Blocked all year, %', 5, 1, round(100 * m.share_blocked, 1), round(100 * f.share_blocked, 1) FROM m, f
  UNION ALL SELECT 'Average review score', 6, 2, round(m.avg_review_score, 2), round(f.avg_review_score, 2) FROM m, f
  UNION ALL SELECT 'Listings from multi-listing hosts, %', 7, 1, round(100 * m.share_multi_listing_hosts, 1), round(100 * f.share_multi_listing_hosts, 1) FROM m, f
)
ORDER BY o""")

ds_accom = dataset("price_by_guests", "Median price by guests", f"""
SELECT city_name, least(accommodates, 8) AS guests,
       CASE WHEN accommodates >= 8 THEN '8+' ELSE CAST(accommodates AS STRING) END AS guests_label,
       round(median(price_eur), 0) AS median_price_eur, count(*) AS listings
FROM {BI}.listing_facts
WHERE price_eur > 0 AND room_type = 'Entire home/apt' AND city_role = 'training'
GROUP BY ALL
ORDER BY guests""")

ds_dist = dataset("price_by_distance", "Median price by distance to centre", f"""
SELECT city_name, distance_band, round(median(price_eur), 0) AS median_price_eur, count(*) AS listings
FROM {BI}.listing_facts
WHERE price_eur > 0 AND distance_band NOT IN ('unknown', '8+ km') AND city_role = 'training'
GROUP BY ALL
ORDER BY distance_band""")

ds_score = dataset("model_scorecard", "Model scorecard", f"""
SELECT city_letter, scope, city_role, evaluation_split, n,
       round(model_mae_eur, 2)            AS model_mae_eur,
       round(baseline_mae_eur, 2)         AS baseline_mae_eur,
       round(100 * improvement_share, 1)  AS improvement_pct,
       round(model_median_ae_eur, 1)      AS model_median_ae_eur,
       round(mean_signed_residual_eur, 2) AS mean_signed_residual_eur
FROM {BI}.model_scorecard
WHERE model_version = 'price-v1'
ORDER BY CASE city_letter WHEN 'A' THEN 1 WHEN 'B' THEN 2 WHEN 'A+B' THEN 3 ELSE 4 END""")

ds_headline = dataset("model_headline", "Headline numbers", f"""
SELECT round(max(CASE WHEN city_letter = 'A+B' THEN model_mae_eur END), 1)    AS ab_model_mae_eur,
       round(max(CASE WHEN city_letter = 'C' THEN model_mae_eur END), 1)      AS c_model_mae_eur,
       round(max(CASE WHEN city_letter = 'C' THEN baseline_mae_eur END), 1)   AS c_baseline_mae_eur,
       round(100 * (max(CASE WHEN city_letter = 'C' THEN model_mae_eur END)
                    / max(CASE WHEN city_letter = 'A+B' THEN model_mae_eur END) - 1), 1) AS c_vs_ab_pct
FROM {BI}.model_scorecard
WHERE model_version = 'price-v1'""")

ds_mae_long = dataset("mae_long", "Model vs baseline MAE", f"""
SELECT scope, 'Model' AS predictor, round(model_mae_eur, 1) AS mae_eur FROM {BI}.model_scorecard WHERE model_version = 'price-v1'
UNION ALL
SELECT scope, 'Baseline', round(baseline_mae_eur, 1) FROM {BI}.model_scorecard WHERE model_version = 'price-v1'""")

ds_scatter = dataset("pred_vs_actual", "Predicted vs actual (evaluation rows)", f"""
SELECT city_name, listing_id, room_type,
       round(actual_price_eur, 0) AS actual_price_eur,
       round(model_prediction_eur, 0) AS predicted_price_eur
FROM {BI}.prediction_details
WHERE {EVAL} AND actual_price_eur <= 1000""")

ds_err_room = dataset("error_by_room", "Error by room type", f"""
SELECT city_name, room_type, count(*) AS n,
       round(avg(absolute_error_eur), 1) AS model_mae_eur,
       round(avg(signed_residual_eur), 1) AS mean_signed_residual_eur
FROM {BI}.prediction_details
WHERE {EVAL}
GROUP BY ALL
HAVING count(*) >= 20""")

ds_err_band = dataset("error_by_price_band", "Residual by actual price band", f"""
SELECT price_band, city_name, count(*) AS n,
       round(avg(signed_residual_eur), 0) AS mean_signed_residual_eur,
       round(avg(absolute_error_eur), 0) AS model_mae_eur
FROM {BI}.prediction_details
WHERE {EVAL}
GROUP BY ALL""")

ds_err_share = dataset("error_share_by_band", "Share of listings vs share of error", f"""
SELECT {POP} AS population, price_band,
       count(*) AS n,
       round(100 * count(*) / sum(count(*)) OVER (PARTITION BY {POP}), 1) AS share_of_listings_pct,
       round(avg(absolute_error_eur), 0) AS model_mae_eur,
       round(100 * sum(absolute_error_eur) / sum(sum(absolute_error_eur)) OVER (PARTITION BY {POP}), 1) AS share_of_total_error_pct
FROM {BI}.prediction_details
WHERE {EVAL}
GROUP BY ALL
ORDER BY population, price_band""")

ds_err_dist = dataset("error_by_distance", "Error by distance to centre", f"""
SELECT city_name, distance_band, count(*) AS n,
       round(avg(absolute_error_eur), 1) AS model_mae_eur,
       round(avg(signed_residual_eur), 1) AS mean_signed_residual_eur
FROM {BI}.prediction_details
WHERE {EVAL} AND distance_band <> 'unknown'
GROUP BY ALL
HAVING count(*) >= 20
ORDER BY distance_band""")

ds_err_neigh = dataset("venice_neighbourhood_error", "City C: error by neighbourhood", f"""
SELECT neighbourhood, count(*) AS n,
       round(avg(absolute_error_eur), 1) AS model_mae_eur,
       round(avg(signed_residual_eur), 1) AS mean_signed_residual_eur,
       round(100 * sum(absolute_error_eur) / (SELECT sum(absolute_error_eur) FROM {BI}.prediction_details
                                        WHERE {EVAL} AND city_letter = 'C'), 1) AS share_of_error_pct
FROM {BI}.prediction_details
WHERE {EVAL} AND city_letter = 'C'
GROUP BY neighbourhood
HAVING count(*) >= 20
ORDER BY share_of_error_pct DESC
LIMIT 12""")

ds_worst = dataset("worst_listings", "Most mis-priced listings", f"""
SELECT city_name, listing_id, listing_url, room_type, neighbourhood, accommodates, distance_band,
       round(actual_price_eur, 0) AS actual_eur,
       round(model_prediction_eur, 0) AS predicted_eur,
       round(baseline_prediction_eur, 0) AS baseline_eur,
       round(signed_residual_eur, 0) AS residual_eur,
       pricing_direction
FROM {BI}.prediction_details
WHERE {EVAL}
QUALIFY row_number() OVER (PARTITION BY city ORDER BY abs(signed_residual_eur) DESC) <= 15
ORDER BY abs(signed_residual_eur) DESC""")

# --------------------------------------------------------------------------
# Page 1 — City overview
# --------------------------------------------------------------------------
p1 = Page("city_overview", "1 · City overview")
p1.text([
    "## Venice is the priciest market (median 231 €/night), Florence 197 €, Milan 163 €; Milan is by far the biggest (25.3k listings)",
    "Inside Airbnb detailed listings, prices in EUR per night. Snapshots: Milan and Florence 2026-09-19 (City A, B: training), "
    "Venice 2026-09-16 (City C: new client, never seen by the model). Median price excludes missing and extreme placeholder prices.",
], 0, 0, 6, 2)
p1.chart(ds_city, ["city_letter", "city_name", "snapshot_date", "listings", "priced_listings", "hosts", "median_price_eur",
                   "open_days_pct", "blocked_pct", "avg_review_score", "multi_host_listings_pct"],
         table([("city_letter", "City"), ("city_name", "Name"), ("snapshot_date", "Snapshot"), ("listings", "Listings"),
                ("priced_listings", "Priced listings"), ("hosts", "Hosts"), ("median_price_eur", "Median price, EUR"),
                ("open_days_pct", "Days open, %"), ("blocked_pct", "Blocked all year, %"),
                ("avg_review_score", "Avg review (0–5)"), ("multi_host_listings_pct", "From multi-listing hosts, %")],
               "Key metrics per city: Venice is small but expensive, with the most professional host base",
               "Days open = share of the next 365 days open for booking; it is not occupancy. "
               "Multi-listing hosts = share of listings whose host has 2+ listings."),
         0, 2, 6, 3)
p1.chart(ds_room, ["city_name", "room_type", "share_pct"],
         bar(("room_type", "Room type"), ("share_pct", "Share of listings, %"),
             "Entire homes dominate everywhere; Venice has the most private rooms (22 %)", color=city_color(), stack="group"),
         0, 5, 3, 5)
p1.chart(ds_price_band, ["city_name", "price_band", "share_pct"],
         bar(("price_band", "Price per night, EUR"), ("share_pct", "Share of priced listings, %"),
             "Milan peaks at 100–149 €, Florence and Venice at 200–299 €", color=city_color(), stack="group"),
         3, 5, 3, 5)
p1.chart(ds_neigh, ["city_name", "neighbourhood_label", "median_price_eur"],
         bar(("neighbourhood_label", "Neighbourhood"), ("median_price_eur", "Median price, EUR"),
             "San Marco (Venice) and Duomo (Milan) are the most expensive areas",
             "Top 6 neighbourhoods per city by median price; only areas with ≥ 20 priced listings.",
             color=city_color(), horizontal=True),
         0, 10, 3, 7)
p1.chart(ds_neigh_count, ["city_name", "neighbourhood_label", "listings"],
         bar(("neighbourhood_label", "Neighbourhood"), ("listings", "Listings"),
             "74 % of Florence's listings are in one area; Milan is spread over 87, Venice over 60",
             "Top 6 neighbourhoods per city by number of listings.", color=city_color(), horizontal=True),
         3, 10, 3, 7)

# --------------------------------------------------------------------------
# Page 2 — Cross-city comparison (A vs B, the training cities)
# --------------------------------------------------------------------------
p2 = Page("cross_city", "2 · Milan vs Florence")
p2.text([
    "## Florence looks ~20 % pricier, but at the same distance from the centre Milan costs as much or more: Florence's premium is location",
    "55 % of Florence's priced listings are within 1 km of the Duomo vs 9 % in Milan. Composition, not the city name, explains most of the gap, "
    "so distance to the centre is the feature that should transfer to a new city.",
], 0, 0, 6, 2)
p2.chart(ds_compare, ["metric", "milan", "florence", "difference", "difference_pct"],
         table([("metric", "Metric"), ("milan", "Milan (A)"), ("florence", "Florence (B)"),
                ("difference", "Florence − Milan"), ("difference_pct", "Difference, %")],
               "Side by side: Florence is pricier, more open for booking and has a more professional host base"),
         0, 2, 6, 4)
p2.chart(ds_room_ab, ["city_name", "room_type", "median_price_eur"],
         bar(("room_type", "Room type"), ("median_price_eur", "Median price, EUR"),
             "Florence is pricier in every room type (entire home 208 € vs 169 €), because more of it is central",
             color=city_color(), stack="group"),
         0, 6, 3, 6)
p2.chart(ds_accom, ["city_name", "guests_label", "median_price_eur"],
         bar(("guests_label", "Guests (entire homes)"), ("median_price_eur", "Median price, EUR"),
             "Price grows with guests in both cities; Florence is higher from 2 guests up",
             "Entire homes only; 8 = 8 or more guests.", color=city_color(), stack="group"),
         3, 6, 3, 6)
p2.chart(ds_dist, ["city_name", "distance_band", "median_price_eur"],
         bar(("distance_band", "Distance to the cathedral (Duomo)"), ("median_price_eur", "Median price, EUR"),
             "Within 1 km of the Duomo Milan is the pricier city (299 € vs 229 €); its centre premium is 2.3× vs 1.6× in Florence",
             "Bands 0–1 / 1–2 / 2–4 / 4–8 km, the same as in the model report; 8+ km omitted (111 Milan listings, 1 in Florence).",
             color=city_color(), stack="group"),
         0, 12, 6, 6)

# --------------------------------------------------------------------------
# Page 3 — Model, including the new client (city C)
# --------------------------------------------------------------------------
p3 = Page("model", "3 · Price model and city C")
p3.text([
    "## On Venice the frozen model's error is 40 % higher than on Milan/Florence, because expensive central listings dominate the misses; it still beats the baseline by 25 %",
    "price-v1 was frozen after Week 1 and run unchanged on Venice: no pipeline fix and no model change were needed. "
    "Milan/Florence: held-out test set (20 % per city). Venice: every priced listing (unseen). "
    "Baseline = training median price for the same room type and number of guests. "
    "Residual = predicted − actual; negative = the model under-prices.",
], 0, 0, 6, 2)
p3.chart(ds_headline, ["ab_model_mae_eur"], counter("ab_model_mae_eur", "MAE, EUR", "Model MAE, Milan + Florence test (EUR)"), 0, 2, 2, 2)
p3.chart(ds_headline, ["c_model_mae_eur"], counter("c_model_mae_eur", "MAE, EUR", "Model MAE, Venice unseen (EUR)"), 2, 2, 1, 2)
p3.chart(ds_headline, ["c_baseline_mae_eur"], counter("c_baseline_mae_eur", "MAE, EUR", "Baseline MAE, Venice (EUR)"), 3, 2, 1, 2)
p3.chart(ds_headline, ["c_vs_ab_pct"], counter("c_vs_ab_pct", "%", "Venice model MAE above A/B, %"), 4, 2, 2, 2)
p3.chart(ds_score, ["city_letter", "scope", "evaluation_split", "n", "model_mae_eur", "baseline_mae_eur", "improvement_pct",
                    "model_median_ae_eur", "mean_signed_residual_eur"],
         table([("city_letter", "City"), ("scope", "Scope"), ("evaluation_split", "Rows"), ("n", "Listings"),
                ("model_mae_eur", "Model MAE, EUR"), ("baseline_mae_eur", "Baseline MAE, EUR"),
                ("improvement_pct", "Improvement, %"), ("model_median_ae_eur", "Model median abs. error, EUR"),
                ("mean_signed_residual_eur", "Mean residual, EUR")],
               "The three numbers side by side: baseline on C 142.46 €, model on A+B 75.88 €, model on C 106.07 €",
               "No post-change number exists because no pipeline fix or model change was required."),
         0, 4, 4, 3)
p3.chart(ds_mae_long, ["scope", "predictor", "mae_eur"],
         bar(("scope", "Population"), ("mae_eur", "MAE, EUR"),
             "The model beats the baseline in every city, by the most in Venice",
             color={"fieldName": "predictor", "scale": {"type": "categorical"}, "displayName": "Predictor"}, stack="group"),
         4, 4, 2, 3)
p3.chart(ds_scatter, ["city_name", "actual_price_eur", "predicted_price_eur"],
         {"version": 3, "widgetType": "scatter",
          "encodings": {"x": {"fieldName": "actual_price_eur", "scale": {"type": "quantitative"}, "displayName": "Actual price, EUR"},
                        "y": {"fieldName": "predicted_price_eur", "scale": {"type": "quantitative"}, "displayName": "Predicted price, EUR"},
                        "color": city_color()},
          "frame": frame("Predictions flatten towards the middle: cheap listings are over-priced, expensive ones under-priced",
                         "Evaluation rows with actual price ≤ 1,000 €. A perfect model lies on the diagonal.")},
         0, 7, 3, 7)
p3.chart(ds_err_band, ["price_band", "city_name", "mean_signed_residual_eur"],
         bar(("price_band", "Actual price band, EUR (A/B training quartiles and p95)"), ("mean_signed_residual_eur", "Mean residual, EUR"),
             "Above 513 € the model under-prices by hundreds of euros in every city",
             color=city_color(), stack="group"),
         3, 7, 3, 7)
p3.chart(ds_err_share, ["population", "price_band", "n", "share_of_listings_pct", "model_mae_eur", "share_of_total_error_pct"],
         table([("population", "Population"), ("price_band", "Actual price band, EUR"), ("n", "Listings"),
                ("share_of_listings_pct", "Share of listings, %"), ("model_mae_eur", "Model MAE, EUR"),
                ("share_of_total_error_pct", "Share of total error, %")],
               "In Venice the 513+ € band is 9.9 % of listings but 50.6 % of the error; Venice also has more listings in the expensive bands",
               "Band edges are the frozen A/B training quartiles and p95, so the populations are compared on the same scale."),
         0, 14, 3, 5)
p3.chart(ds_err_dist, ["city_name", "distance_band", "model_mae_eur"],
         bar(("distance_band", "Distance to centre"), ("model_mae_eur", "Model MAE, EUR"),
             "Errors are highest in the historic centres (< 1 km); Venice's mainland (8+ km) is priced well",
             "Groups with at least 20 evaluation listings.", color=city_color(), stack="group"),
         3, 14, 3, 5)
p3.chart(ds_err_neigh, ["neighbourhood", "share_of_error_pct"],
         bar(("neighbourhood", "Venice neighbourhood"), ("share_of_error_pct", "Share of Venice's total error, %"),
             "Cannaregio, San Marco and Castello carry 56 % of Venice's error",
             "Top 12 Venice neighbourhoods by share of total absolute error; at least 20 listings.", horizontal=True),
         0, 19, 3, 6)
p3.chart(ds_err_room, ["city_name", "room_type", "model_mae_eur"],
         bar(("room_type", "Room type"), ("model_mae_eur", "Model MAE, EUR"),
             "Entire homes carry the largest errors in every city; private rooms are priced best",
             "Room types with at least 20 evaluation listings.", color=city_color(), stack="group"),
         3, 19, 3, 6)
p3.chart(ds_worst, ["city_name", "listing_id", "room_type", "neighbourhood", "accommodates", "distance_band", "actual_eur",
                    "predicted_eur", "baseline_eur", "residual_eur", "pricing_direction", "listing_url"],
         table([("city_name", "City"), ("listing_id", "Listing"), ("room_type", "Room type"), ("neighbourhood", "Neighbourhood"),
                ("accommodates", "Guests"), ("distance_band", "Distance"), ("actual_eur", "Actual, EUR"),
                ("predicted_eur", "Model, EUR"), ("baseline_eur", "Baseline, EUR"), ("residual_eur", "Residual, EUR"),
                ("pricing_direction", "Direction"), ("listing_url", "Link")],
               "The largest misses are extreme asking prices the model under-prices; a residual is not proof a listing is mispriced",
               "15 evaluation listings per city with the largest absolute residual."),
         0, 25, 6, 8)

out = Path(__file__).with_name("airbnb_price_analytics.lvdash.json")
out.write_text(json.dumps({"datasets": datasets, "pages": pages}, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"wrote {out} ({len(datasets)} datasets, {sum(len(p['layout']) for p in pages)} widgets)")
