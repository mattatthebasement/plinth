"""NASA POWER climatology API client (cached)."""

from __future__ import annotations

import math
from typing import Any

import httpx

from plinth.db.cache import get_cached, set_cached

_ENDPOINT = "https://power.larc.nasa.gov/api/temporal/climatology/point"
_DATASET = "nasa-power"
_TTL_DAYS = 30

_PARAMETERS = ",".join([
    "T2M",          # Air temperature at 2m (°C)
    "T2M_MAX",      # Max air temperature at 2m
    "T2M_MIN",      # Min air temperature at 2m
    "T2MDEW",       # Dew point at 2m
    "PRECTOTCORR",  # Precipitation (mm/day)
    "ALLSKY_SFC_SW_DWN",  # All-sky insolation (kWh/m²/day)
    "ALLSKY_KT",    # Insolation clearness index
    "WS10M",        # Wind speed at 10m (m/s)
    "RH2M",         # Relative humidity at 2m (%)
    "HDD18_3",      # Heating degree days (base 18.3°C)
    "CDD18_3",      # Cooling degree days (base 18.3°C)
])


def _grid_key(lat: float, lon: float) -> str:
    """Round to POWER ~0.5° grid cell."""
    lat_r = math.floor(lat / 0.5) * 0.5
    lon_r = math.floor(lon / 0.5) * 0.5
    return f"{_DATASET}:{lat_r:.1f}:{lon_r:.1f}"


def fetch(lat: float, lon: float) -> dict[str, Any]:
    """
    Return NASA POWER monthly climatology for the nearest 0.5° grid cell.
    Checks query_cache first; calls the API on miss.
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
                "community": "RE",
                "parameters": _PARAMETERS,
                "format": "JSON",
                "start": "2001",
                "end": "2020",
                "header": "false",
            },
            timeout=30,
        )
        resp.raise_for_status()
        raw = resp.json()
    except Exception as exc:
        return {"available": False, "error": str(exc)}

    params_data = raw.get("properties", {}).get("parameter", {})
    if not params_data:
        return {"available": False, "error": "unexpected response structure"}

    # Each parameter maps to {"ANN": value, "JAN": val, ...}
    # Normalise to {"t2m": {"annual": x, "monthly": [jan..dec]}}
    month_keys = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN",
                  "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]

    def _extract(param: str) -> dict:
        p = params_data.get(param, {})
        return {
            "annual": p.get("ANN"),
            "monthly": [p.get(m) for m in month_keys],
        }

    result: dict[str, Any] = {
        "available": True,
        "source": "NASA POWER Climatology 2001-2020",
        "grid_lat": raw.get("geometry", {}).get("coordinates", [None, None])[1],
        "grid_lon": raw.get("geometry", {}).get("coordinates", [None, None])[0],
        "t2m": _extract("T2M"),
        "t2m_max": _extract("T2M_MAX"),
        "t2m_min": _extract("T2M_MIN"),
        "t2m_dew": _extract("T2MDEW"),
        "precip_mm_day": _extract("PRECTOTCORR"),
        "solar_kwh_m2_day": _extract("ALLSKY_SFC_SW_DWN"),
        "solar_clearness": _extract("ALLSKY_KT"),
        "wind_speed_10m": _extract("WS10M"),
        "rel_humidity": _extract("RH2M"),
        "hdd_18_3c": _extract("HDD18_3"),
        "cdd_18_3c": _extract("CDD18_3"),
    }

    set_cached(cache_key, _DATASET, result, _TTL_DAYS, lat=lat, lon=lon)

    from plinth.db.registry import register_api_source
    register_api_source(
        _DATASET, version="Climatology 2001–2020",
        update_frequency="on-demand", notes="0.5° grid; monthly/annual climatology",
    )

    return result
