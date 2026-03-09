"""Wildfire Hazard Potential query — delegates to USDA WHP API client."""

from __future__ import annotations

from typing import Any


def query_wildfire_whp(lat: float, lon: float) -> dict[str, Any]:
    """Return USDA Wildfire Hazard Potential index value (cached)."""
    from plinth.ingest.api.usda_whp import fetch
    return fetch(lat, lon)
