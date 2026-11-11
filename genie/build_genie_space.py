"""Build the Genie Agent (Genie space) definition from code.

Usage:  python genie/build_genie_space.py
Writes  genie/genie_space.json  (the `serialized_space` payload of the Genie API)

Deploy (new space):
  databricks genie create-space <warehouse_id> "$(cat genie/genie_space.json)" \
      --title "Airbnb Northern Italy - price analyst" --parent-path /Users/<me>/airbnb
Update an existing one: `databricks genie update-space <space_id> --json ...`.

Every table is a read-only view in workspace.airbnb_bi (sql/bi_views.sql).
Owner: Matseliukh Maksym.
"""
import json
import uuid
from pathlib import Path

BI = "workspace.airbnb_bi"
NS = uuid.UUID("6f1d3c52-4b1e-4b8e-9d0a-2a7c1f0e9b11")


def gid(text):
    """Deterministic 32-hex id so regenerating the file gives a stable diff."""
    return uuid.uuid5(NS, text).hex


def lines(text):
    out = text.strip("\n").split("\n")
    return [l + "\n" for l in out[:-1]] + [out[-1]]


TABLES = {
    "city_roles": ["city", "city_letter", "city_name", "city_role"],
    "city_metrics": ["city_letter", "city_name"],
    "room_type_metrics": ["city_letter", "city_name", "room_type"],
    "neighbourhood_metrics": ["city_letter", "city_name", "neighbourhood"],
    "listing_facts": ["city_letter", "city_name", "room_type", "property_type", "distance_band"],
    "prediction_details": ["city_letter", "city_name", "room_type", "distance_band", "evaluation_split", "pricing_direction"],
    "model_scorecard": ["city_letter", "scope", "evaluation_split"],
}

INSTRUCTIONS = """
You answer questions about short-term rentals (Inside Airbnb, detailed listings) in Northern Italy for an analytics start-up.

CITIES
- "City A" = Milan, "City B" = Florence: the two training cities. "City C" = Venice, the new client (unseen by the model).
- Filter cities with city_letter ('A', 'B', 'C') or city_name ('Milan', 'Florence', 'Venice'). city_roles maps them.
- If a question is about City C / Venice and there are no rows for it, say that Venice has not been loaded or scored yet. Never substitute another city.
- Every table has snapshot_date. Snapshot is 2026-09-19 for Milan and Florence. If several snapshots exist, use the latest per city unless asked otherwise.

PRICES
- price is the advertised price per night in EUR (all cities share the currency, no conversion).
- For median price per city, use city_metrics.median_price_eur. Per city and room type, use room_type_metrics.median_price_eur. Per neighbourhood, use neighbourhood_metrics.median_price_eur (NULL when fewer than 20 priced listings; say so instead of computing your own).
- Only for filters these tables cannot answer (e.g. number of guests, distance, property type) compute MEDIAN(price_eur) from listing_facts with price_eur IS NOT NULL (listings without a valid price have price_eur NULL). Use the median, never the average price: a few listings advertise placeholder prices of thousands of euros.
- Never average medians across groups and never sum distinct host counts across groups.
- "Entire home" / "whole apartment" means room_type = 'Entire home/apt'. "Private room", "Hotel room", "Shared room" are the other room types.

AVAILABILITY AND HOSTS
- open_days_share_365 is the share of the next 365 days that are open for booking. It is NOT occupancy and NOT demand. share_blocked = share of listings with no open day in the next year.
- share_multi_listing_hosts is the share of LISTINGS whose host has 2 or more listings (not a share of hosts).
- "How many listings" uses the listings column of the metrics tables (all listings, including those without a price).

MODEL
- The model is version price-v1; it predicts the nightly price. The baseline is the training median price for the same room type and number of guests (accommodates).
- Errors are only meaningful on evaluation rows: always filter prediction_details with is_evaluation_row = true (held-out test rows for Milan/Florence, all priced rows for an unseen city). Never report errors from training rows.
- signed_residual_eur = predicted - actual. Negative = the model UNDER-prices the listing, positive = OVER-prices. pricing_direction holds the same as text.
- MAE = AVG(absolute_error_eur). For headline MAE per city or for A+B together use model_scorecard (scope 'Milan', 'Florence', 'Milan + Florence', later 'Venice').
- "Where does the model under-price the most" = group evaluation rows by a dimension (room_type, distance_band, accommodates, city) and rank by AVG(signed_residual_eur) ascending; only groups with at least 20 rows; show the count. Neighbourhood is not available on predictions.
- Always show the number of listings behind an average, and round money to whole euros.
""".strip()

EXAMPLES = [
    ("What is the median price of entire homes in City A?",
     f"""SELECT city_letter, city_name, room_type, listings, ROUND(median_price_eur, 0) AS median_price_eur
FROM {BI}.room_type_metrics
WHERE city_letter = 'A' AND room_type = 'Entire home/apt'"""),
    ("Which neighbourhoods in City B have the most listings?",
     f"""SELECT neighbourhood, listings, priced_listings, ROUND(median_price_eur, 0) AS median_price_eur
FROM {BI}.neighbourhood_metrics
WHERE city_letter = 'B'
ORDER BY listings DESC
LIMIT 10"""),
    ("Where does the model under-price listings the most?",
     f"""SELECT city_name, room_type, distance_band, COUNT(*) AS listings,
       ROUND(AVG(signed_residual_eur), 0) AS mean_residual_eur,
       ROUND(AVG(absolute_error_eur), 0) AS mae_eur
FROM {BI}.prediction_details
WHERE is_evaluation_row AND model_version = 'price-v1'
GROUP BY city_name, room_type, distance_band
HAVING COUNT(*) >= 20
ORDER BY mean_residual_eur ASC
LIMIT 10"""),
    ("What is the model's MAE compared with the baseline in each city?",
     f"""SELECT scope, evaluation_split, n AS listings, ROUND(model_mae_eur, 1) AS model_mae_eur,
       ROUND(baseline_mae_eur, 1) AS baseline_mae_eur, ROUND(100 * improvement_share, 1) AS improvement_pct
FROM {BI}.model_scorecard
WHERE model_version = 'price-v1'
ORDER BY scope"""),
    ("Compare median price and share of entire homes between Milan and Florence",
     f"""SELECT c.city_name, c.listings, ROUND(c.median_price_eur, 0) AS median_price_eur,
       ROUND(100 * r.room_type_mix, 1) AS entire_home_pct
FROM {BI}.city_metrics c
JOIN {BI}.room_type_metrics r
  ON r.city = c.city AND r.snapshot_date = c.snapshot_date AND r.room_type = 'Entire home/apt'
WHERE c.city_role = 'training'"""),
    ("What is the median price of a 4-guest entire home in Florence?",
     f"""SELECT city_name, COUNT(*) AS listings, ROUND(MEDIAN(price_eur), 0) AS median_price_eur
FROM {BI}.listing_facts
WHERE city_name = 'Florence' AND room_type = 'Entire home/apt' AND accommodates = 4
  AND price_eur IS NOT NULL
GROUP BY city_name"""),
]

SAMPLE_QUESTIONS = [
    "What is the median price of entire homes in City A?",
    "Which neighbourhoods in City B have the most listings?",
    "Where does the model under-price listings the most?",
    "How much better is the model than the baseline?",
    "Which city has more listings from multi-listing hosts?",
]

space = {
    "version": 2,
    "config": {"sample_questions": [{"id": gid("sq:" + q), "question": [q]} for q in SAMPLE_QUESTIONS]},
    "data_sources": {
        "tables": [
            {
                "identifier": f"{BI}.{t}",
                "column_configs": [
                    {"column_name": c, "enable_format_assistance": True, "enable_entity_matching": True}
                    for c in sorted(cols)
                ],
            }
            for t, cols in sorted(TABLES.items())
        ]
    },
    "instructions": {
        "text_instructions": [{"id": gid("instructions"), "content": lines(INSTRUCTIONS)}],
        "example_question_sqls": [
            {"id": gid("ex:" + q), "question": [q], "sql": lines(sql)} for q, sql in EXAMPLES
        ],
    },
}

# The Genie API requires every id-bearing list to be sorted by id.
space["config"]["sample_questions"].sort(key=lambda x: x["id"])
space["instructions"]["example_question_sqls"].sort(key=lambda x: x["id"])

out = Path(__file__).with_name("genie_space.json")
out.write_text(json.dumps(space, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"wrote {out}")
