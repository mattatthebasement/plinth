"""EPA Air Quality System (AQS) API client (cached)."""

from __future__ import annotations

from datetime import date
from typing import Any

import httpx

from plinth.config import get_settings
from plinth.db.cache import get_cached, set_cached

_BASE = "https://aqs.epa.gov/aqsweb/documents/data_api"
_DATASET = "epa-aqs"
_TTL_DAYS = 365
_NO_MONITOR_RADIUS_MI = 50


def _cache_key(county_fips: str, year: int) -> str:
    return f"{_DATASET}:{county_fips}:{year}"


def _current_year() -> int:
    # AQS data lags 6-18 months; use two years back as the most reliably complete year
    return date.today().year - 2


def _aqs_get(path: str, params: dict) -> dict:
    settings = get_settings()
    if not settings.epa_aqs_key or not settings.epa_aqs_email:
        raise RuntimeError("EPA AQS credentials not configured (EPA_AQS_KEY, EPA_AQS_EMAIL)")
    params = {**params, "email": settings.epa_aqs_email, "key": settings.epa_aqs_key}
    resp = httpx.get(f"{_BASE}/{path}", params=params, timeout=30)
    resp.raise_for_status()
    body = resp.json()
    if body.get("Header", [{}])[0].get("status") == "Failed":
        raise RuntimeError(body["Header"][0].get("error", "AQS API error"))
    return body


def fetch(lat: float, lon: float, county_fips: str) -> dict[str, Any]:
    """
    Return EPA AQS annual summary for PM2.5 and ozone for the given county.

    county_fips is the 5-digit county FIPS (e.g. '40131' for Rogers County OK).
    Checks query_cache first; calls the API on miss.
    """
    year = _current_year()
    cache_key = _cache_key(county_fips, year)
    cached = get_cached(cache_key)
    if cached is not None:
        return cached

    state_fips = county_fips[:2]
    county_fips_short = county_fips[2:]

    pm25_result = _fetch_pollutant(state_fips, county_fips_short, year, param="88101", label="PM2.5")
    ozone_result = _fetch_pollutant(state_fips, county_fips_short, year, param="44201", label="Ozone")

    result: dict[str, Any] = {
        "available": True,
        "source": f"EPA Air Quality System (AQS) Annual Summary {year}",
        "note": "AQS data represents annual summaries and may lag 6–18 months. Not real-time AQI.",
        "county_fips": county_fips,
        "year": year,
        "pm25": pm25_result,
        "ozone": ozone_result,
    }

    set_cached(cache_key, _DATASET, result, _TTL_DAYS, lat=lat, lon=lon)
    return result


def _fetch_pollutant(
    state_fips: str,
    county_fips: str,
    year: int,
    param: str,
    label: str,
) -> dict[str, Any]:
    try:
        data = _aqs_get(
            "annualData/byCounty",
            {
                "param": param,
                "bdate": f"{year}0101",
                "edate": f"{year}1231",
                "state": state_fips,
                "county": county_fips,
            },
        )
    except Exception as exc:
        return {"available": False, "error": str(exc)}

    monitors = data.get("Data", [])
    if not monitors:
        return {
            "available": False,
            "flag": f"No {label} monitor data found for this county in {year}.",
        }

    # Pick the monitor with the highest observation count (most complete record)
    best = max(monitors, key=lambda m: m.get("observation_count", 0))
    return {
        "available": True,
        "monitor_name": best.get("site_name"),
        "monitor_id": f"{best.get('state_code')}-{best.get('county_code')}-{best.get('site_number')}",
        "arithmetic_mean": best.get("arithmetic_mean"),
        "units": best.get("units_of_measure"),
        "observation_count": best.get("observation_count"),
        "observation_pct": best.get("observation_percent"),
        "year": year,
    }
