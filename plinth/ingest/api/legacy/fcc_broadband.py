"""FCC National Broadband Map API client (cached).

Authentication: FCC BDC requires `username` and `hash_value` request headers.
- username: FCC registered email (FCC_USERNAME in .env)
- hash_value: API token from broadbandmap.fcc.gov → Manage API Access (FCC_API_TOKEN)

Status (2026-03): The `listAsOfDates` endpoint is confirmed working. All data
retrieval endpoints (listLocations, listAvailability, listAvailabilityData)
return HTTP 405 "Method Not Available" regardless of auth or method. This
appears to be an access-tier restriction — the data API may be gated to
registered ISP filers only. The bulk state CSV download via the FCC data
download portal (broadbandmap.fcc.gov/data-download) is the planned path for
Phase 2 ingest; this client serves as a placeholder until that is implemented.
"""

from __future__ import annotations

from typing import Any

import httpx

from plinth.config import get_settings
from plinth.db.cache import get_cached, set_cached

_BASE = "https://bdc.fcc.gov/api/public/map"
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
    """Return auth headers for FCC BDC API (username + hash_value)."""
    settings = get_settings()
    token = getattr(settings, "fcc_api_token", "")
    username = getattr(settings, "fcc_username", "")
    headers: dict[str, str] = {"Accept": "application/json"}
    if token and username:
        headers["username"] = username
        headers["hash_value"] = token
    return headers


def check_connectivity() -> dict[str, Any]:
    """
    Verify FCC API credentials by calling listAsOfDates.
    Returns the list of available data periods on success.
    """
    settings = get_settings()
    token = getattr(settings, "fcc_api_token", "")
    username = getattr(settings, "fcc_username", "")

    if not token or not username:
        return {"ok": False, "flag": "FCC_API_TOKEN and FCC_USERNAME both required."}

    try:
        resp = httpx.get(
            f"{_BASE}/listAsOfDates",
            headers=_get_headers(),
            timeout=15,
        )
        data = resp.json()
        if data.get("status_code") == 200:
            dates = [d["as_of_date"] for d in data.get("data", []) if d.get("data_type") == "availability"]
            return {"ok": True, "availability_periods": dates, "latest": dates[-1] if dates else None}
        return {"ok": False, "status_code": data.get("status_code"), "message": data.get("message")}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def fetch(lat: float, lon: float) -> dict[str, Any]:
    """
    Return FCC broadband availability for the nearest fabric location.
    Checks query_cache first; calls the FCC BDC API on miss.

    Requires FCC_API_TOKEN and FCC_USERNAME in environment. Returns a graceful
    flag if not configured or if data endpoints return 405 (access gated).

    NOTE: As of 2026-03, the per-location data endpoints return HTTP 405
    regardless of credentials. This will be replaced with a PostGIS spatial
    query once the Phase 2 bulk ingestor is implemented.
    """
    settings = get_settings()
    token = getattr(settings, "fcc_api_token", "")
    username = getattr(settings, "fcc_username", "")

    if not token or not username:
        return {
            "available": False,
            "flag": "FCC broadband data not configured (FCC_API_TOKEN and FCC_USERNAME required).",
            "disclaimer": DISCLAIMER,
        }

    # Step 1: find the fabric location_id nearest to this lat/lon
    try:
        location_id, address = _lookup_location(lat, lon)
    except FccAccessGated:
        return {
            "available": False,
            "flag": (
                "FCC broadband data temporarily unavailable: per-location API endpoints "
                "are access-gated (HTTP 405). Pending Phase 2 bulk ingest."
            ),
            "disclaimer": DISCLAIMER,
        }
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
            f"{_BASE}/listBSLAvailability",
            params={
                "latitude": lat,
                "longitude": lon,
                "location_id": location_id,
                "unit": "mi",
                "radius": 0.1,
                "category": "residential",
                "addr_type": "B",
            },
            headers=_get_headers(),
            timeout=30,
        )
        raw = resp.json()
        if raw.get("status_code") == 405:
            raise FccAccessGated()
    except FccAccessGated:
        return {
            "available": False,
            "flag": (
                "FCC broadband data temporarily unavailable: per-location API endpoints "
                "are access-gated (HTTP 405). Pending Phase 2 bulk ingest."
            ),
            "disclaimer": DISCLAIMER,
        }
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
    raw = resp.json()
    if raw.get("status_code") == 405:
        raise FccAccessGated()
    data = raw.get("data", [])
    if not data:
        return None, None
    loc = data[0]
    return str(loc.get("location_id", "")), loc.get("address_full")


class FccAccessGated(Exception):
    """Raised when FCC API returns 405 Method Not Available."""
