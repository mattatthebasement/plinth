"""Mapbox Static Images API helpers for report map generation."""

from __future__ import annotations

import base64
import logging
import urllib.parse
from typing import NamedTuple

import httpx

from plinth.config import get_settings

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.mapbox.com/styles/v1/mapbox"


class MapSpec(NamedTuple):
    style: str
    zoom: int
    width: int
    height: int
    retina: bool = True


# Map configurations for each report map slot
COVER_MAP = MapSpec(style="streets-v12", zoom=13, width=800, height=400)
TERRAIN_MAP = MapSpec(style="outdoors-v12", zoom=13, width=800, height=400)
SOLAR_MAP = MapSpec(style="light-v11", zoom=10, width=800, height=350)


def _marker(lon: float, lat: float, color: str = "D4553E") -> str:
    """Build a Mapbox marker overlay string."""
    return f"pin-l+{color}({lon},{lat})"


def fetch_map_png(
    lat: float,
    lon: float,
    spec: MapSpec,
    *,
    token: str | None = None,
) -> bytes | None:
    """Fetch a Mapbox Static Image and return raw PNG bytes, or None on failure."""
    if token is None:
        token = get_settings().mapbox_token
    if not token:
        logger.warning("MAPBOX_TOKEN not configured — skipping map fetch")
        return None

    overlay = _marker(lon, lat)
    retina = "@2x" if spec.retina else ""
    path = (
        f"{_BASE_URL}/{spec.style}/static/{overlay}"
        f"/{lon},{lat},{spec.zoom}"
        f"/{spec.width}x{spec.height}{retina}"
    )
    params = {"access_token": token, "logo": "false", "attribution": "false"}
    url = f"{path}?{urllib.parse.urlencode(params)}"

    try:
        with httpx.Client(timeout=20.0) as client:
            resp = client.get(url)
            resp.raise_for_status()
            return resp.content
    except httpx.HTTPStatusError as exc:
        logger.warning("Mapbox API error %s: %s", exc.response.status_code, url)
        return None
    except Exception as exc:
        logger.warning("Mapbox map fetch failed: %s", exc)
        return None


def fetch_map_b64(
    lat: float,
    lon: float,
    spec: MapSpec,
    *,
    token: str | None = None,
) -> str | None:
    """Return a data URI string (data:image/png;base64,...) or None."""
    png = fetch_map_png(lat, lon, spec, token=token)
    if png is None:
        return None
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def fetch_all_maps(lat: float, lon: float) -> dict[str, str | None]:
    """
    Fetch all three report maps. Returns a dict with keys:
    - cover: cover page context map
    - terrain: physical context hillshade/outdoors map
    - solar: solar/climate overview map

    Values are data URI strings or None if unavailable.
    """
    settings = get_settings()
    token = settings.mapbox_token

    results = {}
    for key, spec in [("cover", COVER_MAP), ("terrain", TERRAIN_MAP), ("solar", SOLAR_MAP)]:
        logger.info("Fetching %s map from Mapbox...", key)
        results[key] = fetch_map_b64(lat, lon, spec, token=token)
        if results[key] is None:
            logger.warning("Map '%s' unavailable — placeholder will be shown", key)

    return results
