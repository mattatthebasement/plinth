"""USGS Earthquake Catalog (FDSN) API client (cached)."""

from __future__ import annotations

import math
from datetime import date
from typing import Any

import httpx

from plinth.db.cache import get_cached, set_cached

_ENDPOINT = "https://earthquake.usgs.gov/fdsnws/event/1/query"
_DATASET = "usgs-eq"
_TTL_DAYS = 30
_RADIUS_KM = 80.0     # ~50 miles
_YEARS = 50
_MIN_MAG = 3.0


def _grid_key(lat: float, lon: float) -> str:
    """Round to ~100km grid cell (1° ≈ 111km)."""
    lat_r = math.floor(lat)
    lon_r = math.floor(lon)
    start_year = date.today().year - _YEARS
    return f"{_DATASET}:{lat_r}:{lon_r}:{start_year}"


def fetch(lat: float, lon: float) -> dict[str, Any]:
    """
    Return earthquake catalog summary for M3+ events within 50 mi, last 50 years.
    Checks query_cache first; calls the USGS FDSN API on miss.
    """
    cache_key = _grid_key(lat, lon)
    cached = get_cached(cache_key)
    if cached is not None:
        return cached

    start_year = date.today().year - _YEARS
    start_date = f"{start_year}-01-01"
    end_date = date.today().isoformat()

    try:
        resp = httpx.get(
            _ENDPOINT,
            params={
                "format": "geojson",
                "latitude": lat,
                "longitude": lon,
                "maxradiuskm": _RADIUS_KM,
                "minmagnitude": _MIN_MAG,
                "starttime": start_date,
                "endtime": end_date,
                "orderby": "magnitude",
            },
            timeout=30,
        )
        resp.raise_for_status()
        raw = resp.json()
    except Exception as exc:
        return {"available": False, "error": str(exc)}

    features = raw.get("features", [])
    count = len(features)

    if count == 0:
        result: dict[str, Any] = {
            "available": True,
            "source": "USGS Earthquake Catalog (FDSN)",
            "search_radius_mi": 50,
            "search_years": _YEARS,
            "min_magnitude": _MIN_MAG,
            "event_count": 0,
            "max_magnitude": None,
            "largest_event": None,
        }
    else:
        largest = features[0]["properties"]  # ordered by magnitude desc
        result = {
            "available": True,
            "source": "USGS Earthquake Catalog (FDSN)",
            "search_radius_mi": 50,
            "search_years": _YEARS,
            "min_magnitude": _MIN_MAG,
            "note": f"Events M{_MIN_MAG}+ within 50 miles, {start_year}–{date.today().year}. Reported count only; not a seismic risk assessment.",
            "event_count": count,
            "max_magnitude": largest.get("mag"),
            "largest_event": {
                "magnitude": largest.get("mag"),
                "place": largest.get("place"),
                "time": largest.get("time"),
                "depth_km": features[0]["geometry"]["coordinates"][2] if features else None,
            },
        }

    set_cached(cache_key, _DATASET, result, _TTL_DAYS, lat=lat, lon=lon)

    from plinth.db.registry import register_api_source
    register_api_source(
        _DATASET, version=f"{start_year}–{date.today().year}",
        update_frequency="on-demand", notes=f"M{_MIN_MAG}+ within 50 mi, last {_YEARS} yr",
    )

    return result
