"""Mapbox Static Images API helpers for report map generation."""

from __future__ import annotations

import base64
import io
import logging
import math
import urllib.parse
from typing import NamedTuple

import httpx
from PIL import Image, ImageDraw, ImageFont

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


# ── Demographics radius map ──────────────────────────────────────────────

_EARTH_CIRCUMFERENCE_M = 40_075_016.686
_MILES_TO_METERS = 1_609.34
_FONT_PATHS = [
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "LiberationSans-Bold.ttf",
]


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in _FONT_PATHS:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


# Mapbox GL uses 512px base tiles (not the classic 256px web tiles).
_MAPBOX_TILE_GL = 512


def _miles_to_retina_px(miles: float, zoom: float, lat_rad: float) -> float:
    """Convert a ground distance in miles to retina (2×) pixel radius."""
    meters_per_logical_px = (
        _EARTH_CIRCUMFERENCE_M * math.cos(lat_rad) / (_MAPBOX_TILE_GL * 2**zoom)
    )
    return miles * _MILES_TO_METERS / meters_per_logical_px * 2


def _fetch_radius_map(
    lat: float,
    lon: float,
    *,
    viewport_miles: float,
    circles: list[tuple[int, str]],
    token: str,
) -> str | None:
    """Fetch a street basemap and overlay labeled radius circles.

    Args:
        viewport_miles: Total width of the map viewport in miles.
        circles: List of (radius_miles, label) drawn largest-first.
        token: Mapbox access token.
    """
    img_logical = 800
    lat_rad = math.radians(lat)

    zoom = math.log2(
        img_logical
        * _EARTH_CIRCUMFERENCE_M
        * math.cos(lat_rad)
        / (_MAPBOX_TILE_GL * viewport_miles * _MILES_TO_METERS)
    )
    zoom = round(zoom, 2)

    retina = "@2x"
    path = (
        f"{_BASE_URL}/streets-v12/static"
        f"/{lon},{lat},{zoom}"
        f"/{img_logical}x{img_logical}{retina}"
    )
    params = {"access_token": token, "logo": "false", "attribution": "false"}
    url = f"{path}?{urllib.parse.urlencode(params)}"

    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(url)
            resp.raise_for_status()
            png_bytes = resp.content
    except Exception as exc:
        logger.warning("Radius map fetch failed: %s", exc)
        return None

    # ── Draw overlays with Pillow ────────────────────────────────────
    base = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    cx, cy = base.width // 2, base.height // 2
    font = _load_font(32)

    circle_color = (30, 80, 180, 200)
    label_color = (30, 80, 180, 255)
    pill_bg = (255, 255, 255, 210)

    for r_miles, label in circles:
        r_px = _miles_to_retina_px(r_miles, zoom, lat_rad)
        draw.ellipse(
            [cx - r_px, cy - r_px, cx + r_px, cy + r_px],
            outline=circle_color,
            width=3,
        )

        bbox = draw.textbbox((0, 0), label, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        tx = cx - tw // 2
        ty = int(cy - r_px - th - 10)
        pad = 5
        draw.rounded_rectangle(
            [tx - pad, ty - pad, tx + tw + pad, ty + th + pad],
            radius=5,
            fill=pill_bg,
        )
        draw.text((tx, ty), label, fill=label_color, font=font)

    # Center marker dot
    mr = 10
    draw.ellipse(
        [cx - mr, cy - mr, cx + mr, cy + mr],
        fill=(212, 85, 62, 255),
        outline=(255, 255, 255, 255),
        width=3,
    )

    result = Image.alpha_composite(base, overlay).convert("RGB")
    buf = io.BytesIO()
    result.save(buf, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def fetch_demographics_map_b64(
    lat: float, lon: float, *, token: str | None = None
) -> str | None:
    """22-mile wide map with 1 / 5 / 10-mile radius circles."""
    if token is None:
        token = get_settings().mapbox_token
    if not token:
        logger.warning("MAPBOX_TOKEN not set — skipping demographics map")
        return None
    return _fetch_radius_map(
        lat, lon,
        viewport_miles=22.0,
        circles=[(10, "10 mi"), (5, "5 mi"), (1, "1 mi")],
        token=token,
    )


def fetch_demographics_closeup_map_b64(
    lat: float, lon: float, *, token: str | None = None
) -> str | None:
    """11-mile wide map with 1 / 5-mile radius circles."""
    if token is None:
        token = get_settings().mapbox_token
    if not token:
        logger.warning("MAPBOX_TOKEN not set — skipping demographics close-up map")
        return None
    return _fetch_radius_map(
        lat, lon,
        viewport_miles=11.0,
        circles=[(5, "5 mi"), (1, "1 mi")],
        token=token,
    )
