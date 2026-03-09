"""EPA AQS air quality query — delegates to EPA AQS API client."""

from __future__ import annotations

from typing import Any


def query_epa_aqs(lat: float, lon: float, county_fips: str = "40143") -> dict[str, Any]:
    """Return EPA AQS annual PM2.5 and ozone summary (cached by county+year)."""
    from plinth.ingest.api.epa_aqs import fetch
    return fetch(lat, lon, county_fips=county_fips)
