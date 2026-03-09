"""NASA POWER climatology query — delegates to NASA POWER API client."""

from __future__ import annotations

from typing import Any


def query_nasa_power(lat: float, lon: float) -> dict[str, Any]:
    """Return NASA POWER monthly climatology (cached, 0.5° grid)."""
    from plinth.ingest.api.nasa_power import fetch
    return fetch(lat, lon)
