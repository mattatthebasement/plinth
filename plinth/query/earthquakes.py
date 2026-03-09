"""USGS earthquake catalog query — delegates to USGS FDSN API client."""

from __future__ import annotations

from typing import Any


def query_earthquakes(lat: float, lon: float) -> dict[str, Any]:
    """Return USGS M3+ earthquake summary within 50 mi, last 50 years (cached)."""
    from plinth.ingest.api.usgs_earthquakes import fetch
    return fetch(lat, lon)
