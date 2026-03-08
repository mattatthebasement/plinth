"""USGS Design Maps API client — Seismic Hazard PGA (cached)."""

from __future__ import annotations

import math
from typing import Any

import httpx

from plinth.db.cache import get_cached, set_cached

_ENDPOINT = "https://earthquake.usgs.gov/ws/designmaps/nehrp-2020.json"
_DATASET = "usgs-seismic"
_TTL_DAYS = 365  # NSHM model updates on ~5-year cycles


def _grid_key(lat: float, lon: float) -> str:
    """Round to 0.1° grid cell."""
    lat_r = math.floor(lat * 10) / 10
    lon_r = math.floor(lon * 10) / 10
    return f"{_DATASET}:{lat_r:.1f}:{lon_r:.1f}"


def fetch(lat: float, lon: float) -> dict[str, Any]:
    """
    Return USGS NEHRP 2020 seismic design values for the site.
    Reports raw PGA only — no Seismic Design Category derivation.
    Checks query_cache first; calls the Design Maps API on miss.
    """
    cache_key = _grid_key(lat, lon)
    cached = get_cached(cache_key)
    if cached is not None:
        return cached

    try:
        resp = httpx.get(
            _ENDPOINT,
            params={
                "latitude": lat,
                "longitude": lon,
                "riskCategory": "II",
                "siteClass": "C",
                "title": "Plinth Site Query",
            },
            timeout=30,
        )
        resp.raise_for_status()
        raw = resp.json()
    except Exception as exc:
        return {"available": False, "error": str(exc)}

    output = raw.get("response", {}).get("data", {})
    if not output:
        return {"available": False, "error": "unexpected response structure"}

    pga = output.get("pgam")
    ss = output.get("ss")
    s1 = output.get("s1")

    if pga is None:
        return {
            "available": False,
            "flag": "Seismic hazard data unavailable for this location.",
        }

    result: dict[str, Any] = {
        "available": True,
        "source": "USGS NEHRP 2020 Seismic Hazard Model",
        "note": "Raw design values only. No Seismic Design Category determination is provided.",
        "risk_category": "II",
        "site_class": "C",
        "pgam_g": pga,   # MCE_R PGA (g)
        "ss_g": ss,       # MCE_R spectral acceleration at 0.2s (g)
        "s1_g": s1,       # MCE_R spectral acceleration at 1.0s (g)
    }

    set_cached(cache_key, _DATASET, result, _TTL_DAYS, lat=lat, lon=lon)
    return result
