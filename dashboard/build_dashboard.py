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
SELECT city_name, room_type, listings,
       round(100 * room_type_mix, 1) AS share_pct,
       round(median_price_eur, 0)    AS median_price_eur
FROM {BI}.room_type_metrics""")

ds_neigh = dataset("neighbourhood_prices", "Most expensive neighbourhoods", f"""
SELECT city_name, concat(neighbourhood, ' (', city_letter, ')') AS neighbourhood_label,
       listings, priced_listings, round(median_price_eur, 0) AS median_price_eur
FROM {BI}.neighbourhood_metrics
WHERE meets_price_sample_minimum
QUALIFY row_number() OVER (PARTITION BY city ORDER BY median_price_eur DESC) <= 8""")

ds_neigh_count = dataset("neighbourhood_counts", "Listings per neighbourhood", f"""
SELECT city_name, concat(neighbourhood, ' (', city_letter, ')') AS neighbourhood_label, listings,
       round(100 * listings / sum(listings) OVER (PARTITION BY city), 1) AS share_of_city_pct
FROM {BI}.neighbourhood_metrics
QUALIFY row_number() OVER (PARTITION BY city ORDER BY listings DESC) <= 8""")

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
WHERE price_eur > 0 AND city_role = 'training'
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
WHERE price_eur > 0 AND distance_band <> 'unknown' AND city_role = 'training'
GROUP BY ALL
ORDER BY distance_band""")

ds_score = dataset("model_scorecard", "Model scorecard", f"""
SELECT city_letter, scope, city_role, evaluation_split, n,
       round(model_mae_eur, 1)            AS model_mae_eur,
       round(baseline_mae_eur, 1)         AS baseline_mae_eur,
       round(100 * improvement_share, 1)  AS improvement_pct,
       round(model_median_ae_eur, 1)      AS model_median_ae_eur,
       round(mean_signed_residual_eur, 1) AS mean_signed_residual_eur
FROM {BI}.model_scorecard
WHERE model_version = 'price-v1'
ORDER BY CASE city_letter WHEN 'A' THEN 1 WHEN 'B' THEN 2 WHEN 'A+B' THEN 3 ELSE 4 END""")

ds_headline = dataset("model_headline", "Model headline (A+B)", f"""
SELECT round(model_mae_eur, 1) AS model_mae_eur, round(baseline_mae_eur, 1) AS baseline_mae_eur,
       round(100 * improvement_share, 1) AS improvement_pct, n
FROM {BI}.model_scorecard
WHERE model_version = 'price-v1' AND city_letter = 'A+B'""")

ds_mae_long = dataset("mae_long", "Model vs baseline MAE", f"""
SELECT scope, 'Model' AS predictor, round(model_mae_eur, 1) AS mae_eur FROM {BI}.model_scorecard WHERE model_version = 'price-v1'
UNION ALL
SELECT scope, 'Baseline (median by room type x guests)', round(baseline_mae_eur, 1) FROM {BI}.model_scorecard WHERE model_version = 'price-v1'""")

ds_scatter = dataset("pred_vs_actual", "Predicted vs actual (evaluation rows)", f"""
SELECT city_name, listing_id, room_type,
       round(actual_price_eur, 0) AS actual_price_eur,
       round(model_prediction_eur, 0) AS predicted_price_eur
FROM {BI}.prediction_details
WHERE is_evaluation_row AND model_version = 'price-v1' AND actual_price_eur <= 1000""")

ds_err_room = dataset("error_by_room", "Error by room type", f"""
SELECT city_name, room_type, count(*) AS n,
       round(avg(absolute_error_eur), 1) AS model_mae_eur,
       round(avg(signed_residual_eur), 1) AS mean_signed_residual_eur
FROM {BI}.prediction_details
WHERE is_evaluation_row AND model_version = 'price-v1'
GROUP BY ALL
HAVING count(*) >= 20""")

ds_err_band = dataset("error_by_price_band", "Error by actual price band", f"""
SELECT CASE WHEN actual_price_eur < 100 THEN '1: <100'
            WHEN actual_price_eur < 200 THEN '2: 100-199'
            WHEN actual_price_eur < 400 THEN '3: 200-399'
            WHEN actual_price_eur < 1000 THEN '4: 400-999'
            ELSE '5: 1000+' END AS actual_price_band,
       city_name,
       count(*) AS n,
       round(avg(signed_residual_eur), 0) AS mean_signed_residual_eur,
       round(avg(absolute_error_eur), 0) AS model_mae_eur
FROM {BI}.prediction_details
WHERE is_evaluation_row AND model_version = 'price-v1'
GROUP BY ALL""")

ds_err_share = dataset("error_share_by_band", "Share of total error by price band", f"""
SELECT CASE WHEN actual_price_eur < 100 THEN '1: <100'
            WHEN actual_price_eur < 200 THEN '2: 100-199'
            WHEN actual_price_eur < 400 THEN '3: 200-399'
            WHEN actual_price_eur < 1000 THEN '4: 400-999'
            ELSE '5: 1000+' END AS actual_price_band,
       round(100 * count(*) / sum(count(*)) OVER (), 1) AS share_of_listings_pct,
       round(100 * sum(absolute_error_eur) / sum(sum(absolute_error_eur)) OVER (), 1) AS share_of_total_error_pct
FROM {BI}.prediction_details
WHERE is_evaluation_row AND model_version = 'price-v1' AND city_role = 'training'
GROUP BY 1
ORDER BY 1""")

ds_err_dist = dataset("error_by_distance", "Error by distance to centre", f"""
SELECT city_name, distance_band, count(*) AS n,
       round(avg(absolute_error_eur), 1) AS model_mae_eur,
       round(avg(signed_residual_eur), 1) AS mean_signed_residual_eur
FROM {BI}.prediction_details
WHERE is_evaluation_row AND model_version = 'price-v1' AND distance_band <> 'unknown'
GROUP BY ALL
ORDER BY distance_band""")

ds_worst = dataset("worst_listings", "Most mis-priced listings", f"""
SELECT city_name, listing_id, listing_url, room_type, accommodates, distance_band,
       round(actual_price_eur, 0) AS actual_eur,
       round(model_prediction_eur, 0) AS predicted_eur,
       round(baseline_prediction_eur, 0) AS baseline_eur,
       round(signed_residual_eur, 0) AS residual_eur,
       pricing_direction
FROM {BI}.prediction_details
WHERE is_evaluation_row AND model_version = 'price-v1'
ORDER BY abs(signed_residual_eur) DESC
LIMIT 40""")

# --------------------------------------------------------------------------
# Page 1 — City overview
# --------------------------------------------------------------------------
p1 = Page("city_overview", "1 · City overview")
p1.text([
    "## Florence is the pricier market (median 197 € vs 163 €/night), Milan the bigger one (25.3k vs 13.6k listings)",
    "Inside Airbnb detailed listings, snapshot 2026-09-19, prices in EUR per night. "
    "City A = Milan, City B = Florence (training cities). Median price excludes missing and extreme placeholder prices.",
], 0, 0, 6, 2)
p1.chart(ds_city, ["city_letter", "city_name", "snapshot_date", "listings", "priced_listings", "hosts", "median_price_eur",
                   "open_days_pct", "blocked_pct", "avg_review_score", "multi_host_listings_pct"],
         table([("city_letter", "City"), ("city_name", "Name"), ("snapshot_date", "Snapshot"), ("listings", "Listings"),
                ("priced_listings", "Priced listings"), ("hosts", "Hosts"), ("median_price_eur", "Median price, EUR"),
                ("open_days_pct", "Days open, %"), ("blocked_pct", "Blocked all year, %"),
                ("avg_review_score", "Avg review (0–5)"), ("multi_host_listings_pct", "From multi-listing hosts, %")],
               "Key metrics per city",
               "Days open = share of the next 365 days open for booking; it is not occupancy."),
         0, 2, 6, 3)
p1.chart(ds_room, ["city_name", "room_type", "share_pct"],
         bar(("room_type", "Room type"), ("share_pct", "Share of listings, %"),
             "Entire homes dominate both cities (88 % Milan, 83 % Florence)", color=city_color(), stack="group"),
         0, 5, 3, 5)
p1.chart(ds_price_band, ["city_name", "price_band", "share_pct"],
         bar(("price_band", "Price per night, EUR"), ("share_pct", "Share of priced listings, %"),
             "Milan's most common price band is 100–149 €, Florence's 200–299 €", color=city_color(), stack="group"),
         3, 5, 3, 5)
p1.chart(ds_neigh, ["city_name", "neighbourhood_label", "median_price_eur"],
         bar(("neighbourhood_label", "Neighbourhood"), ("median_price_eur", "Median price, EUR"),
             "Duomo and Brera are the most expensive areas; Florence's Centro Storico leads its city",
             "Top 8 neighbourhoods per city by median price; only areas with ≥ 20 priced listings.",
             color=city_color(), horizontal=True),
         0, 10, 3, 7)
p1.chart(ds_neigh_count, ["city_name", "neighbourhood_label", "listings"],
         bar(("neighbourhood_label", "Neighbourhood"), ("listings", "Listings"),
             "74 % of Florence's listings are in one area; Milan is spread over 87",
             "Top 8 neighbourhoods per city by number of listings.", color=city_color(), horizontal=True),
         3, 10, 3, 7)

# --------------------------------------------------------------------------
# Page 2 — Cross-city comparison
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
p2.chart(ds_room, ["city_name", "room_type", "median_price_eur"],
         bar(("room_type", "Room type"), ("median_price_eur", "Median price, EUR"),
             "Florence is pricier in every room type (entire home 208 € vs 169 €), because more of it is central", color=city_color(), stack="group"),
         0, 6, 3, 6)
p2.chart(ds_accom, ["city_name", "guests_label", "median_price_eur"],
         bar(("guests_label", "Guests (entire homes)"), ("median_price_eur", "Median price, EUR"),
             "Price grows with guests in both cities; Florence is higher from 2 guests up",
             "Entire homes only; 8 = 8 or more guests.", color=city_color(), stack="group"),
         3, 6, 3, 6)
p2.chart(ds_dist, ["city_name", "distance_band", "median_price_eur"],
         bar(("distance_band", "Distance to the cathedral (Duomo)"), ("median_price_eur", "Median price, EUR"),
             "Within 1 km of the Duomo Milan is the pricier city (299 € vs 229 €); its centre premium is 2.3× vs 1.6× in Florence",
             "dist_center_km is computed from coordinates; it is the location feature that can transfer to a new city.",
             color=city_color(), stack="group"),
         0, 12, 6, 6)

# --------------------------------------------------------------------------
# Page 3 — Model
# --------------------------------------------------------------------------
p3 = Page("model", "3 · Price model")
p3.text([
    "## The model beats the baseline by 20.5 % (MAE 75.9 € vs 95.5 €), but systematically under-prices luxury listings",
    "Held-out test set (20 % of listings per city, never used for training or model choice). "
    "Baseline = training median price for the same room type and number of guests. "
    "Negative residual = model price below the actual price (under-pricing). City C is added here after its run.",
], 0, 0, 6, 2)
p3.chart(ds_headline, ["model_mae_eur"], counter("model_mae_eur", "MAE, EUR", "Model MAE, A+B test set (EUR)"), 0, 2, 2, 2)
p3.chart(ds_headline, ["baseline_mae_eur"], counter("baseline_mae_eur", "MAE, EUR", "Baseline MAE, A+B test set (EUR)"), 2, 2, 2, 2)
p3.chart(ds_headline, ["improvement_pct"], counter("improvement_pct", "%", "Error reduction vs baseline, %"), 4, 2, 2, 2)
p3.chart(ds_score, ["city_letter", "scope", "evaluation_split", "n", "model_mae_eur", "baseline_mae_eur", "improvement_pct",
                    "model_median_ae_eur", "mean_signed_residual_eur"],
         table([("city_letter", "City"), ("scope", "Scope"), ("evaluation_split", "Rows"), ("n", "Listings"),
                ("model_mae_eur", "Model MAE, EUR"), ("baseline_mae_eur", "Baseline MAE, EUR"),
                ("improvement_pct", "Improvement, %"), ("model_median_ae_eur", "Model median abs. error, EUR"),
                ("mean_signed_residual_eur", "Mean residual, EUR")],
               "Same improvement in both cities; the typical error (median 34 €) is far below the mean",
               "Rows = test (held out, A/B) or unseen (new city, every priced listing)."),
         0, 4, 6, 3)
p3.chart(ds_scatter, ["city_name", "actual_price_eur", "predicted_price_eur"],
         {"version": 3, "widgetType": "scatter",
          "encodings": {"x": {"fieldName": "actual_price_eur", "scale": {"type": "quantitative"}, "displayName": "Actual price, EUR"},
                        "y": {"fieldName": "predicted_price_eur", "scale": {"type": "quantitative"}, "displayName": "Predicted price, EUR"},
                        "color": city_color()},
          "frame": frame("Predictions flatten towards the middle: cheap listings are over-priced, expensive ones under-priced",
                         "Test rows with actual price ≤ 1,000 € (98.8 % of them). A perfect model lies on the diagonal.")},
         0, 7, 3, 7)
p3.chart(ds_err_band, ["actual_price_band", "city_name", "mean_signed_residual_eur"],
         bar(("actual_price_band", "Actual price band, EUR"), ("mean_signed_residual_eur", "Mean residual (predicted − actual), EUR"),
             "Above 400 € the model under-prices by ~200 € on average, above 1,000 € by ~1,600 €",
             color=city_color(), stack="group"),
         3, 7, 3, 7)
p3.chart(ds_err_share, ["actual_price_band", "share_of_listings_pct", "share_of_total_error_pct"],
         table([("actual_price_band", "Actual price band, EUR"), ("share_of_listings_pct", "Share of test listings, %"),
                ("share_of_total_error_pct", "Share of total absolute error, %")],
               "1 % of listings (≥ 1,000 €) cause a quarter of the total error"),
         0, 14, 3, 4)
p3.chart(ds_err_room, ["city_name", "room_type", "model_mae_eur"],
         bar(("room_type", "Room type"), ("model_mae_eur", "Model MAE, EUR"),
             "Entire homes carry the largest errors; private rooms are priced best",
             "Room types with at least 20 test listings.", color=city_color(), stack="group"),
         3, 14, 3, 4)
p3.chart(ds_err_dist, ["city_name", "distance_band", "model_mae_eur"],
         bar(("distance_band", "Distance to centre"), ("model_mae_eur", "Model MAE, EUR"),
             "Errors are highest in the historic centres (< 1 km), where prices vary most",
             color=city_color(), stack="group"),
         0, 18, 6, 5)
p3.chart(ds_worst, ["city_name", "listing_id", "room_type", "accommodates", "distance_band", "actual_eur",
                    "predicted_eur", "baseline_eur", "residual_eur", "pricing_direction", "listing_url"],
         table([("city_name", "City"), ("listing_id", "Listing"), ("room_type", "Room type"), ("accommodates", "Guests"),
                ("distance_band", "Distance"), ("actual_eur", "Actual, EUR"), ("predicted_eur", "Model, EUR"),
                ("baseline_eur", "Baseline, EUR"), ("residual_eur", "Residual, EUR"),
                ("pricing_direction", "Direction"), ("listing_url", "Link")],
               "The most mis-priced listings are almost all extreme asking prices the model under-prices",
               "40 test listings with the largest absolute residual."),
         0, 23, 6, 8)

out = Path(__file__).with_name("airbnb_price_analytics.lvdash.json")
out.write_text(json.dumps({"datasets": datasets, "pages": pages}, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"wrote {out} ({len(datasets)} datasets, {sum(len(p['layout']) for p in pages)} widgets)")
