"""Split, required baseline and MAE evaluation for the price model.

pandas/numpy/standard library only, so it can be imported and tested without
PySpark. Notebooks convert Spark frames with ``toPandas()`` and back.

Rules encoded here (see docs/model_feature_review.md):
- The split depends only on ``(city, listing_id)`` and a fixed salt; never on
  price, row order or other rows.
- The baseline is fitted on ``evaluation_split == "train"`` rows only.
- Headline MAE uses every test row with a valid positive actual price.
"""

import hashlib
import math
from numbers import Integral, Real

import numpy as np
import pandas as pd

SPLIT_SALT = "airbnb-v1"
SPLIT_TEST_SHARE = 0.20
TRAINING_CITIES = ("milan", "florence")

PRICE_COL = "price_eur"
SPLIT_COL = "evaluation_split"
SPLIT_REASON_COL = "split_exclusion_reason"
ELIGIBLE_COL = "eligible_for_training"

LEVEL_CELL = "room_type_x_accommodates"
LEVEL_ROOM = "room_type"
LEVEL_OVERALL = "overall"
BASELINE_LEVELS = (LEVEL_CELL, LEVEL_ROOM, LEVEL_OVERALL)
LOOKUP_COLUMNS = ("baseline_level", "room_type", "accommodates", "median_price_eur", "n_train")

HEADLINE_POPULATION = "test_all_valid_positive_price"


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #

def _require_columns(df, columns, what):
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise ValueError(f"{what}: missing required columns {missing}")


def _canonical_city(value):
    return str(value).strip().lower()


def _canonical_listing_id(value):
    """Stable text form of a listing id: 123, 123.0, '123' and np.int64(123) agree."""
    if isinstance(value, (bool, np.bool_)):
        raise ValueError(f"listing_id must not be boolean: {value!r}")
    if isinstance(value, Integral):
        return str(int(value))
    if isinstance(value, Real):
        if not math.isfinite(value) or not float(value).is_integer():
            raise ValueError(f"listing_id is not an integer: {value!r}")
        return str(int(value))
    text = str(value).strip()
    if not text:
        raise ValueError("listing_id is empty")
    return text


def _valid_positive(series):
    values = pd.to_numeric(series, errors="coerce").astype("float64")
    return values.where(np.isfinite(values) & (values > 0))


# --------------------------------------------------------------------------- #
# MODEL-02: deterministic split
# --------------------------------------------------------------------------- #

def split_hash_unit(city, listing_id, salt=SPLIT_SALT):
    """Map ``(city, listing_id, salt)`` to a stable number in [0, 1) using SHA-256."""
    key = f"{salt}|{_canonical_city(city)}|{_canonical_listing_id(listing_id)}"
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / 2.0**64


def assign_split(df, test_share=SPLIT_TEST_SHARE, salt=SPLIT_SALT, eligible_col=ELIGIBLE_COL):
    """Return a copy of ``df`` with ``evaluation_split`` and ``split_exclusion_reason``.

    Eligible rows get ``train`` or ``test`` from a per-listing hash, so each city
    receives about ``test_share`` test rows independently of every other row.
    Ineligible rows keep a null split and a reason. Prices are never read.
    """
    if not 0 < test_share < 1:
        raise ValueError("test_share must be between 0 and 1")
    if not isinstance(salt, str) or not salt:
        raise ValueError("salt must be a non-empty string")
    _require_columns(df, ["city", "listing_id", eligible_col], "assign_split")

    if df["city"].isna().any() or df["listing_id"].isna().any():
        raise ValueError("assign_split: city and listing_id must be non-null (silver key contract)")
    cities = df["city"].map(_canonical_city)
    listing_ids = df["listing_id"].map(_canonical_listing_id)
    duplicated = pd.DataFrame({"city": cities, "listing_id": listing_ids}).duplicated(keep=False)
    if duplicated.any():
        examples = sorted(set(zip(cities[duplicated], listing_ids[duplicated])))[:5]
        raise ValueError(
            f"assign_split: {int(duplicated.sum())} rows share a (city, listing_id) key, e.g. {examples}. "
            "Pass one snapshot per city."
        )

    eligible_raw = df[eligible_col]
    eligible = eligible_raw.astype("boolean").fillna(False).astype(bool)
    reasons = pd.Series(None, index=df.index, dtype="object")
    reasons[eligible_raw.isna()] = "eligibility_unknown"
    reasons[~eligible & eligible_raw.notna()] = "not_eligible_for_training"
    if "exclusion_reasons" in df.columns:
        # Expose silver's structural reasons when they are available.
        detailed = df["exclusion_reasons"].map(
            lambda v: ",".join(str(x) for x in v) if isinstance(v, (list, tuple, np.ndarray)) and len(v) else None
        )
        reasons = detailed.where(~eligible & detailed.notna(), reasons)

    units = pd.Series(
        [split_hash_unit(c, i, salt) for c, i in zip(cities, listing_ids)], index=df.index, dtype="float64"
    )
    split = pd.Series(None, index=df.index, dtype="object")
    split[eligible & (units < test_share)] = "test"
    split[eligible & (units >= test_share)] = "train"

    out = df.copy()
    # Plain None (not NaN) so the columns become SQL NULLs in Delta.
    out[SPLIT_COL] = split.astype("object").where(split.notna(), None)
    out[SPLIT_REASON_COL] = reasons.astype("object").where(reasons.notna(), None)
    return out


def split_summary(split_df):
    """Counts per city of train / test / excluded rows and the realised test share."""
    _require_columns(split_df, ["city", SPLIT_COL], "split_summary")
    labels = split_df[SPLIT_COL].fillna("excluded")
    table = pd.crosstab(split_df["city"], labels).reindex(columns=["train", "test", "excluded"], fill_value=0)
    eligible = table["train"] + table["test"]
    table["test_share"] = (table["test"] / eligible.where(eligible > 0)).astype("float64")
    return table.reset_index()


# --------------------------------------------------------------------------- #
# MODEL-03: required baseline with fallback chain
# --------------------------------------------------------------------------- #

def _baseline_keys(df):
    """Normalised room type (string or None) and accommodates (int or None)."""
    room = df["room_type"].map(lambda v: None if pd.isna(v) or not str(v).strip() else str(v).strip())
    acc = pd.to_numeric(df["accommodates"], errors="coerce").astype("float64")
    valid_acc = np.isfinite(acc) & (acc > 0) & (acc == np.floor(acc))
    acc = acc.where(valid_acc).map(lambda v: None if pd.isna(v) else int(v))
    return room.astype("object"), acc.astype("object")


def fit_baseline(df, price_col=PRICE_COL, split_col=SPLIT_COL):
    """Fit the pooled baseline lookup on ``train`` rows only.

    Levels: median by ``room_type x accommodates``; median by ``room_type``;
    overall median. Rows with a missing room type or invalid accommodates only
    contribute to the levels they can define. Returns a long-format frame with
    ``LOOKUP_COLUMNS`` that can be written to a Delta table as is.
    """
    _require_columns(df, [split_col, "room_type", "accommodates", price_col], "fit_baseline")
    train = df[df[split_col] == "train"]
    price = _valid_positive(train[price_col])
    keep = price.notna()
    if not keep.any():
        raise ValueError("fit_baseline: no training rows with a valid positive price")
    room, acc = _baseline_keys(train[keep])
    rows = pd.DataFrame({"room_type": room, "accommodates": acc, "price": price[keep]})

    cells = rows.dropna(subset=["room_type", "accommodates"])
    cells = cells.groupby(["room_type", "accommodates"], sort=True)["price"].agg(["median", "size"]).reset_index()
    cells["baseline_level"] = LEVEL_CELL
    rooms = rows.dropna(subset=["room_type"]).groupby("room_type", sort=True)["price"].agg(["median", "size"]).reset_index()
    rooms["baseline_level"] = LEVEL_ROOM
    rooms["accommodates"] = None
    overall = pd.DataFrame({
        "baseline_level": [LEVEL_OVERALL], "room_type": [None], "accommodates": [None],
        "median": [float(rows["price"].median())], "size": [len(rows)],
    })
    lookup = pd.concat([cells, rooms, overall], ignore_index=True)
    lookup = lookup.rename(columns={"median": "median_price_eur", "size": "n_train"})
    lookup["room_type"] = lookup["room_type"].astype("object").where(lookup["room_type"].notna(), None)
    lookup["accommodates"] = pd.array(lookup["accommodates"].tolist(), dtype="Int64")
    lookup["median_price_eur"] = lookup["median_price_eur"].astype("float64")
    lookup["n_train"] = lookup["n_train"].astype("int64")
    return lookup[list(LOOKUP_COLUMNS)]


def predict_baseline(df, lookup, prediction_col="baseline_prediction_eur", level_col="baseline_level"):
    """Return a copy of ``df`` with a baseline prediction and the level used for every row."""
    _require_columns(df, ["room_type", "accommodates"], "predict_baseline")
    _require_columns(lookup, LOOKUP_COLUMNS, "predict_baseline lookup")
    overall = lookup.loc[lookup["baseline_level"] == LEVEL_OVERALL, "median_price_eur"]
    if len(overall) != 1:
        raise ValueError("predict_baseline: lookup must contain exactly one overall median")

    cell_rows = lookup[lookup["baseline_level"] == LEVEL_CELL]
    cell_map = {
        (r, int(a)): float(m)
        for r, a, m in zip(cell_rows["room_type"], cell_rows["accommodates"], cell_rows["median_price_eur"])
    }
    room_rows = lookup[lookup["baseline_level"] == LEVEL_ROOM]
    room_map = {r: float(m) for r, m in zip(room_rows["room_type"], room_rows["median_price_eur"])}
    overall_value = float(overall.iloc[0])

    room, acc = _baseline_keys(df)
    predictions, levels = [], []
    for r, a in zip(room, acc):
        if r is not None and a is not None and (r, a) in cell_map:
            predictions.append(cell_map[(r, a)])
            levels.append(LEVEL_CELL)
        elif r is not None and r in room_map:
            predictions.append(room_map[r])
            levels.append(LEVEL_ROOM)
        else:
            predictions.append(overall_value)
            levels.append(LEVEL_OVERALL)

    out = df.copy()
    out[prediction_col] = pd.Series(predictions, index=df.index, dtype="float64")
    out[level_col] = pd.Series(levels, index=df.index, dtype="object")
    return out


# --------------------------------------------------------------------------- #
# MODEL-05 utility: MAE on held-out rows
# --------------------------------------------------------------------------- #

def fit_upper_price_threshold(df, quantile=0.99, price_col=PRICE_COL, split_col=SPLIT_COL):
    """Optional supplementary cut-off, fitted on ``train`` rows only. Never used for the headline."""
    _require_columns(df, [split_col, price_col], "fit_upper_price_threshold")
    price = _valid_positive(df.loc[df[split_col] == "train", price_col]).dropna()
    if price.empty:
        raise ValueError("fit_upper_price_threshold: no training rows with a valid positive price")
    return float(price.quantile(quantile))


def mae_table(
    df,
    prediction_col,
    actual_col=PRICE_COL,
    split_col=SPLIT_COL,
    split_value="test",
    cities=TRAINING_CITIES,
    upper_price_threshold=None,
    threshold_source=None,
):
    """MAE in EUR per city and for all ``cities`` together, on identical rows.

    ``prediction_col`` may be one column or a list; every listed prediction is
    scored on exactly the same rows. The headline population is every
    ``split_value`` row in ``cities`` with a valid positive actual price; a
    missing prediction on such a row raises instead of being dropped.

    ``upper_price_threshold`` adds a separately labelled supplementary
    population (actual <= threshold). It must have been fitted on training rows
    (for example with ``fit_upper_price_threshold``) and ``threshold_source``
    must say how; it never changes the headline rows.
    """
    predictions = [prediction_col] if isinstance(prediction_col, str) else list(prediction_col)
    if not predictions:
        raise ValueError("mae_table: at least one prediction column is required")
    _require_columns(df, ["city", actual_col, split_col, *predictions], "mae_table")
    if upper_price_threshold is not None:
        if not threshold_source:
            raise ValueError("mae_table: pass threshold_source describing how the threshold was fitted on training rows")
        if not (isinstance(upper_price_threshold, Real) and math.isfinite(upper_price_threshold) and upper_price_threshold > 0):
            raise ValueError("mae_table: upper_price_threshold must be a positive finite number")

    city_names = [_canonical_city(c) for c in cities]
    city = df["city"].map(lambda v: None if pd.isna(v) else _canonical_city(v))
    selected = (df[split_col] == split_value) & city.isin(city_names)
    actual = _valid_positive(df[actual_col])
    headline = selected & actual.notna()

    populations = [(HEADLINE_POPULATION, f"{split_value} rows with a valid positive actual price", headline)]
    if upper_price_threshold is not None:
        populations.append((
            "test_actual_le_train_threshold",
            f"supplementary: {split_value} rows with valid positive actual <= {upper_price_threshold:.2f} EUR "
            f"(threshold fitted on training rows: {threshold_source})",
            headline & (actual <= upper_price_threshold),
        ))

    pred_values = {}
    for col in predictions:
        values = pd.to_numeric(df[col], errors="coerce").astype("float64")
        bad = headline & ~np.isfinite(values)
        if bad.any():
            raise ValueError(f"mae_table: {int(bad.sum())} headline rows have no valid '{col}' prediction")
        pred_values[col] = values

    groups = [(name, city == name) for name in city_names] + [("+".join(city_names), city.isin(city_names))]
    excluded_invalid = selected & actual.isna()
    records = []
    for population, description, mask in populations:
        for group, group_mask in groups:
            rows = mask & group_mask
            n = int(rows.sum())
            for col in predictions:
                errors = (pred_values[col][rows] - actual[rows]).abs()
                records.append({
                    "evaluation_population": population,
                    "population_description": description,
                    "city_group": group,
                    "prediction": col,
                    "n": n,
                    "mae_eur": float(errors.mean()) if n else float("nan"),
                    "n_excluded_invalid_actual": int((excluded_invalid & group_mask).sum()),
                })
    return pd.DataFrame.from_records(records)
