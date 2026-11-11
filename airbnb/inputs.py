"""Runtime input metadata, independent of the frozen pipeline's source code."""
import json
import math
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.parse import urlparse


def identifier(value, name):
    value = value.strip()
    pattern = r"[a-z][a-z0-9_-]*" if name == "city" else r"[A-Za-z_][A-Za-z0-9_]*"
    if not re.fullmatch(pattern, value):
        raise ValueError(f"Invalid {name} identifier.")
    return value


def iso_date(value):
    if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
        raise ValueError("snapshot_date must be YYYY-MM-DD.")
    return value


def load_sources(root, catalog, sources_config_path=""):
    """Read repo defaults or a JSON input manifest from the raw-file volume.

    After the A/B freeze a new city's manifest can be uploaded as runtime input,
    without changing the code/config at the frozen Git revision.
    """
    catalog = identifier(catalog, "catalog")
    config_path = sources_config_path.strip()
    if config_path:
        allowed = f"/Volumes/{catalog}/airbnb_bronze/raw_files/config/"
        if not config_path.startswith(allowed) or ".." in Path(config_path).parts or not config_path.endswith(".json"):
            raise ValueError(f"sources_config_path must be a JSON file under {allowed}")
        path = Path(config_path)
    else:
        path = Path(root) / "config/sources.json"
    try:
        sources = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Cannot read source configuration {path}: {error}") from error
    if not isinstance(sources, dict) or not sources:
        raise ValueError("Source configuration must be a nonempty object keyed by city.")
    return sources


@dataclass(frozen=True)
class CitySnapshot:
    catalog: str
    city: str
    snapshot_date: str
    source_url: str
    centre: tuple | None


def resolve_snapshot(sources, catalog, city, snapshot_date):
    catalog = identifier(catalog, "catalog")
    city = identifier(city.strip().lower(), "city")
    entry = sources.get(city)
    if not isinstance(entry, dict):
        raise ValueError(f"City '{city}' is not configured. Supply its input metadata; no notebook copy is needed.")
    configured_date = iso_date(entry.get("snapshot_date"))
    snapshot_date = iso_date(snapshot_date.strip() or configured_date)
    if snapshot_date != configured_date:
        raise ValueError("snapshot_date differs from source configuration; reconcile the input manifest first.")
    lat, lon = entry.get("centre_latitude"), entry.get("centre_longitude")
    centre = None
    if lat is not None or lon is not None:
        try:
            lat, lon = float(lat), float(lon)
        except (TypeError, ValueError) as error:
            raise ValueError("Configure both centre coordinates as numbers, or omit both.") from error
        if not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
            raise ValueError("City centre coordinates are outside valid ranges.")
        centre = (lat, lon)
    configured_url = entry.get("source_url") or ""
    if not isinstance(configured_url, str):
        raise ValueError("source_url must be a string or null.")
    return CitySnapshot(catalog, city, snapshot_date, configured_url.strip(), centre)


def resolve_source(snapshot, source_path="", source_url=""):
    expected = (
        f"/Volumes/{snapshot.catalog}/airbnb_bronze/raw_files/"
        f"{snapshot.city}/{snapshot.snapshot_date}/listings.csv.gz"
    )
    source_path = source_path.strip() or expected
    if source_path != expected:
        raise ValueError(f"Upload the original file and set source_path to {expected}")
    source_url = source_url.strip() or snapshot.source_url
    if snapshot.source_url and source_url != snapshot.source_url:
        raise ValueError("source_url differs from source configuration; reconcile provenance before loading.")
    url = urlparse(source_url)
    if (
        url.scheme != "https" or url.netloc != "data.insideairbnb.com"
        or not url.path.endswith(f"/{snapshot.snapshot_date}/data/listings.csv.gz")
        or f"/{snapshot.city}/" not in url.path or url.query or url.fragment
    ):
        raise ValueError("Copy the matching city's dated detailed listings.csv.gz link from Inside Airbnb.")
    return source_path, source_url
