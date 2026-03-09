"""Seismic hazard PGA query — delegates to USGS Design Maps API client."""

from __future__ import annotations

from typing import Any


def query_seismic_pga(lat: float, lon: float) -> dict[str, Any]:
    """Return USGS NEHRP 2020 seismic design values (cached)."""
    from plinth.ingest.api.usgs_seismic import fetch
    return fetch(lat, lon)
