"""USDA Wildfire Hazard Potential — geoplatform.gov ImageServer client (cached)."""

from __future__ import annotations

import json
import math
from typing import Any

import httpx

from plinth.db.cache import get_cached, set_cached

_ENDPOINT = (
    "https://imagery.geoplatform.gov/iipp/rest/services"
    "/Fire_Aviation/USFS_EDW_RMRS_WildfireHazardPotentialContinuous"
    "/ImageServer/getSamples"
)
_DATASET = "usda-whp"
_TTL_DAYS = 365
_NATIONAL_MAX = 144153  # observed national max from ImageServer metadata


def _grid_key(lat: float, lon: float) -> str:
    """Round to 0.01° grid cell (~1km, well within 270m pixel)."""
    lat_r = math.floor(lat * 100) / 100
    lon_r = math.floor(lon * 100) / 100
    return f"{_DATASET}:{lat_r:.2f}:{lon_r:.2f}"


def fetch(lat: float, lon: float) -> dict[str, Any]:
    """
    Return USDA WHP continuous index value at the given point.
    Source: USFS Wildfire Hazard Potential 2023, 270m resolution.
    Checks query_cache first; calls the ImageServer getSamples on miss.
    """
    cache_key = _grid_key(lat, lon)
    cached = get_cached(cache_key)
    if cached is not None:
        return cached

    geometry = json.dumps({
        "x": lon,
        "y": lat,
        "spatialReference": {"wkid": 4326},
    })

    try:
        resp = httpx.get(
            _ENDPOINT,
            params={
                "geometry": geometry,
                "geometryType": "esriGeometryPoint",
                "outFields": "*",
                "f": "json",
            },
            timeout=30,
        )
        resp.raise_for_status()
        raw = resp.json()
    except Exception as exc:
        return {"available": False, "error": str(exc)}

    samples = raw.get("samples", [])
    if not samples:
        return {
            "available": False,
            "flag": "Wildfire hazard data unavailable for this location.",
        }

    raw_value = samples[0].get("value")
    if raw_value is None:
        return {"available": False, "flag": "No WHP value returned for this location."}

    whp_value = int(raw_value)

    result: dict[str, Any] = {
        "available": True,
        "source": "USDA Forest Service Wildfire Hazard Potential 2023 (270m)",
        "citation": (
            "An index of the relative potential for high-intensity, hard-to-control wildfire "
            "based on fire occurrence, burn probability, and LANDFIRE 2020 fuel conditions. "
            "Not a real-time fire risk measure."
        ),
        "whp_value": whp_value,
        "whp_national_max": _NATIONAL_MAX,
        "resolution_m": 270,
    }

    set_cached(cache_key, _DATASET, result, _TTL_DAYS, lat=lat, lon=lon)

    from plinth.db.registry import register_api_source
    register_api_source(
        _DATASET, version="WHP 2023 (270 m)",
        update_frequency="on-demand", notes="Continuous index; LANDFIRE 2020 fuel conditions",
    )

    return result
