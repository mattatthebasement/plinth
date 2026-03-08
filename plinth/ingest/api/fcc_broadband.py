"""FCC National Broadband Map API client (cached)."""

from __future__ import annotations

from typing import Any

import httpx

from plinth.config import get_settings
from plinth.db.cache import get_cached, set_cached

_BASE = "https://broadbandmap.fcc.gov/api/public/map"
_DATASET = "fcc-broadband"
_TTL_DAYS = 90

DISCLAIMER = (
    "Broadband availability data is self-reported by ISPs to the FCC and may "
    "significantly overstate actual service availability and speeds."
)

# Technology type codes from FCC BDC
_TECH_LABELS = {
    10: "DSL",
    40: "Cable",
    50: "Fiber",
    60: "Satellite",
    70: "Fixed Wireless",
    300: "Licensed Fixed Wireless",
    400: "Unlicensed Fixed Wireless",
    0: "Other",
}


def _cache_key(location_id: str) -> str:
    return f"{_DATASET}:{location_id}"


def _get_headers() -> dict[str, str]:
    settings = get_settings()
    token = getattr(settings, "fcc_api_token", "")
    headers: dict[str, str] = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def fetch(lat: float, lon: float) -> dict[str, Any]:
    """
    Return FCC broadband availability for the nearest fabric location.
    Checks query_cache first; calls the FCC BDC API on miss.

    Requires FCC_API_TOKEN in environment. Returns a graceful flag if
    not configured or if no location is found.
    """
    settings = get_settings()
    token = getattr(settings, "fcc_api_token", "")

    if not token:
        return {
            "available": False,
            "flag": "FCC broadband data not configured (FCC_API_TOKEN required).",
            "disclaimer": DISCLAIMER,
        }

    # Step 1: find the fabric location_id nearest to this lat/lon
    try:
        location_id, address = _lookup_location(lat, lon)
    except Exception as exc:
        return {"available": False, "error": str(exc), "disclaimer": DISCLAIMER}

    if not location_id:
        return {
            "available": False,
            "flag": "No FCC fabric location found near this coordinate.",
            "disclaimer": DISCLAIMER,
        }

    cache_key = _cache_key(location_id)
    cached = get_cached(cache_key)
    if cached is not None:
        return cached

    # Step 2: fetch availability for that location
    try:
        resp = httpx.get(
            f"{_BASE}/listAvailability",
            params={
                "latitude": lat,
                "longitude": lon,
                "location_id": location_id,
                "unit": "mbps",
            },
            headers=_get_headers(),
            timeout=30,
        )
        resp.raise_for_status()
        raw = resp.json()
    except Exception as exc:
        return {"available": False, "error": str(exc), "disclaimer": DISCLAIMER}

    providers = raw.get("data", [])
    if not providers:
        result: dict[str, Any] = {
            "available": True,
            "location_id": location_id,
            "address": address,
            "providers": [],
            "best_download_mbps": None,
            "best_upload_mbps": None,
            "technologies": [],
            "disclaimer": DISCLAIMER,
        }
    else:
        best_down = max((p.get("max_download_speed", 0) or 0 for p in providers), default=0)
        best_up = max((p.get("max_upload_speed", 0) or 0 for p in providers), default=0)
        tech_codes = sorted({p.get("technology_code") for p in providers if p.get("technology_code")})
        result = {
            "available": True,
            "location_id": location_id,
            "address": address,
            "provider_count": len(providers),
            "best_download_mbps": best_down,
            "best_upload_mbps": best_up,
            "technologies": [_TECH_LABELS.get(t, str(t)) for t in tech_codes],
            "disclaimer": DISCLAIMER,
        }

    set_cached(cache_key, _DATASET, result, _TTL_DAYS, lat=lat, lon=lon)
    return result


def _lookup_location(lat: float, lon: float) -> tuple[str | None, str | None]:
    """Find the FCC fabric location_id nearest to a lat/lon."""
    resp = httpx.get(
        f"{_BASE}/listLocations",
        params={"latitude": lat, "longitude": lon},
        headers=_get_headers(),
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json().get("data", [])
    if not data:
        return None, None
    loc = data[0]
    return str(loc.get("location_id", "")), loc.get("address_full")
