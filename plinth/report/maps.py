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


# ── Electric infrastructure map ──────────────────────────────────────────────

# Voltage class label tuples (must match electric_infrastructure.py ordering)
_VOLTAGE_CLASSES: list[tuple[str, int, int]] = [
    ("500kV+",    500, 9999),
    ("345kV",     300,  499),
    ("230kV",     200,  299),
    ("138–161kV", 100,  199),
    ("69–115kV",   60,   99),
    ("<69kV",       0,   59),
]

# Voltage class → (R, G, B) line color
_TX_COLORS: dict[str, tuple[int, int, int]] = {
    "500kV+":    (180,  30,  30),   # dark red
    "345kV":     (220,  90,   0),   # orange
    "230kV":     (200, 160,   0),   # amber-yellow
    "138–161kV": (100, 150,  50),   # olive green
    "69–115kV":  ( 80, 120, 200),   # medium blue
    "<69kV":     (150, 150, 150),   # gray
    "Other":     (180, 180, 180),   # light gray
}

# Fuel color palette → (R, G, B)
_FUEL_COLORS_RGB: dict[str, tuple[int, int, int]] = {
    "Natural Gas":   (245, 158,  11),
    "Solar":         (234, 179,   8),
    "Wind":          ( 16, 185, 129),
    "Hydro":         ( 59, 130, 246),
    "Nuclear":       (139,  92, 246),
    "Coal":          (107, 114, 128),
    "Landfill Gas":  (132, 204,  22),
    "Oil/Petroleum": (146,  64,  14),
    "Geothermal":    (239,  68,  68),
}
_DEFAULT_PLANT_COLOR = (148, 163, 184)


def _web_mercator(lat: float, lon: float) -> tuple[float, float]:
    """Convert (lat, lon) to normalized [0,1] Web Mercator coordinates."""
    x = lon / 360.0 + 0.5
    sin_lat = math.sin(math.radians(lat))
    # Clamp to avoid log(0)
    sin_lat = max(-0.9999, min(0.9999, sin_lat))
    y = 0.5 - math.log((1 + sin_lat) / (1 - sin_lat)) / (4 * math.pi)
    return x, y


def _latlon_to_px(
    lat: float, lon: float,
    center_lat: float, center_lon: float,
    zoom: float,
    img_px: int,
    scale: int = 2,
) -> tuple[float, float]:
    """Convert (lat, lon) to retina pixel coordinates in a Mapbox static image."""
    tile_size = 512  # Mapbox GL uses 512px logical tiles
    tiles = 2 ** zoom
    cx, cy = _web_mercator(center_lat, center_lon)
    px, py = _web_mercator(lat, lon)
    dx = (px - cx) * tiles * tile_size * scale
    dy = (py - cy) * tiles * tile_size * scale
    img_center = img_px * scale / 2
    return img_center + dx, img_center + dy


def _compute_zoom_for_extent(
    min_lon: float, max_lon: float, min_lat: float, max_lat: float,
    img_px: int = 800, scale: int = 2,
) -> float:
    """Compute the maximum zoom level that fits the given bounding box."""
    tile_size = 512
    cx = (min_lon + max_lon) / 2
    cy_merc = (_web_mercator(min_lat, 0)[1] + _web_mercator(max_lat, 0)[1]) / 2
    # Span in normalized mercator units
    span_x = abs(_web_mercator(0, max_lon)[0] - _web_mercator(0, min_lon)[0])
    span_y = abs(_web_mercator(min_lat, 0)[1] - _web_mercator(max_lat, 0)[1])
    span = max(span_x, span_y)
    if span <= 0:
        return 12.0
    zoom = math.log2(img_px * scale / (tile_size * span))
    return zoom


def _draw_geojson_polygon(
    draw: "ImageDraw.Draw",
    geojson: dict,
    center_lat: float, center_lon: float,
    zoom: float, img_px: int,
    color: tuple[int, int, int, int],
    fill: tuple[int, int, int, int] | None = None,
    width: int = 2,
) -> None:
    """Draw a GeoJSON Polygon or MultiPolygon onto a Pillow ImageDraw."""
    gtype = geojson.get("type", "")
    if gtype == "Polygon":
        rings = geojson["coordinates"]
    elif gtype == "MultiPolygon":
        rings = [ring for poly in geojson["coordinates"] for ring in poly]
    else:
        return
    for ring in rings:
        pts = [
            _latlon_to_px(lat, lon, center_lat, center_lon, zoom, img_px)
            for lon, lat in ring
        ]
        if len(pts) < 3:
            continue
        if fill:
            draw.polygon(pts, fill=fill)
        draw.line(pts + [pts[0]], fill=color, width=width)


def _draw_geojson_linestring(
    draw: "ImageDraw.Draw",
    geojson: dict,
    center_lat: float, center_lon: float,
    zoom: float, img_px: int,
    color: tuple[int, int, int, int],
    width: int = 3,
) -> None:
    """Draw a GeoJSON LineString or MultiLineString onto a Pillow ImageDraw."""
    gtype = geojson.get("type", "")
    if gtype == "LineString":
        lines = [geojson["coordinates"]]
    elif gtype == "MultiLineString":
        lines = geojson["coordinates"]
    else:
        return
    for line in lines:
        pts = [
            _latlon_to_px(lat, lon, center_lat, center_lon, zoom, img_px)
            for lon, lat in line
        ]
        if len(pts) < 2:
            continue
        draw.line(pts, fill=color, width=width)


def fetch_electric_map_b64(
    lat: float,
    lon: float,
    elec_q: dict,
    *,
    token: str | None = None,
) -> str | None:
    """
    Generate an electrical infrastructure map with Pillow overlays on a Mapbox basemap.

    Shows: service territory boundary, transmission lines (colored by voltage class),
    substations, power plants (colored by fuel type), and the site marker.
    Dynamic bounding box fits all features with 20% padding, capped at 30-mile radius.
    """
    if token is None:
        token = get_settings().mapbox_token
    if not token:
        logger.warning("MAPBOX_TOKEN not set — skipping electric map")
        return None

    # ── Compute dynamic bounding box ────────────────────────────────────────
    all_lats = [lat]
    all_lons = [lon]
    for s in elec_q.get("substations", []):
        all_lats.append(s["lat"]); all_lons.append(s["lon"])
    for p in elec_q.get("nearby_plants", []):
        all_lats.append(p["lat"]); all_lons.append(p["lon"])

    if all_lats:
        lat_span = max(all_lats) - min(all_lats)
        lon_span = max(all_lons) - min(all_lons)
        pad_lat = max(lat_span * 0.2, 0.05)  # ~3 miles minimum padding
        pad_lon = max(lon_span * 0.2, 0.07)
        min_lat = min(all_lats) - pad_lat
        max_lat = max(all_lats) + pad_lat
        min_lon = min(all_lons) - pad_lon
        max_lon = max(all_lons) + pad_lon
    else:
        # Default ±0.3° (~20 miles) box
        min_lat, max_lat = lat - 0.3, lat + 0.3
        min_lon, max_lon = lon - 0.4, lon + 0.4

    # Cap at 30-mile radius (~0.44° lat, ~0.52° lon at 36°N)
    center_lat = (min_lat + max_lat) / 2
    center_lon = (min_lon + max_lon) / 2
    MAX_SPAN_LAT = 0.88   # ~60 miles
    MAX_SPAN_LON = 1.04
    if (max_lat - min_lat) > MAX_SPAN_LAT:
        min_lat = center_lat - MAX_SPAN_LAT / 2
        max_lat = center_lat + MAX_SPAN_LAT / 2
    if (max_lon - min_lon) > MAX_SPAN_LON:
        min_lon = center_lon - MAX_SPAN_LON / 2
        max_lon = center_lon + MAX_SPAN_LON / 2

    img_px = 800
    zoom = _compute_zoom_for_extent(min_lon, max_lon, min_lat, max_lat, img_px=img_px)
    zoom = max(7.0, min(zoom * 0.92, 14.0))  # slight zoom-out for breathing room

    # ── Fetch basemap ────────────────────────────────────────────────────────
    retina = "@2x"
    path = (
        f"{_BASE_URL}/light-v11/static"
        f"/{center_lon},{center_lat},{zoom:.2f}"
        f"/{img_px}x{img_px}{retina}"
    )
    params = {"access_token": token, "logo": "false", "attribution": "false"}
    url = f"{path}?{urllib.parse.urlencode(params)}"

    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(url)
            resp.raise_for_status()
            png_bytes = resp.content
    except Exception as exc:
        logger.warning("Electric map basemap fetch failed: %s", exc)
        return None

    base = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    scale = 2  # retina

    def to_px(plat: float, plon: float) -> tuple[float, float]:
        return _latlon_to_px(plat, plon, center_lat, center_lon, zoom, img_px, scale)

    # ── Draw service territory boundaries ────────────────────────────────────
    territory_palette = [
        (59, 130, 246, 180),   # blue
        (249, 115, 22, 180),   # orange
    ]
    for i, territory in enumerate(elec_q.get("service_territories", [])):
        if not territory.get("geojson"):
            continue
        color = territory_palette[i % len(territory_palette)]
        fill_color = (*color[:3], 18)
        _draw_geojson_polygon(draw, territory["geojson"], center_lat, center_lon,
                               zoom, img_px, color=color, fill=fill_color, width=3)

    # ── Draw transmission lines ──────────────────────────────────────────────
    for tx in elec_q.get("tx_map_lines", []):
        rgb = _TX_COLORS.get(tx["voltage_class"], _TX_COLORS["Other"])
        color = (*rgb, 220)
        _draw_geojson_linestring(draw, tx["geojson"], center_lat, center_lon,
                                  zoom, img_px, color=color, width=4)

    # ── Draw substations ─────────────────────────────────────────────────────
    for stn in elec_q.get("substations", []):
        x, y = to_px(stn["lat"], stn["lon"])
        r = 12
        draw.rectangle([x - r, y - r, x + r, y + r],
                        fill=(255, 220, 0, 230), outline=(100, 80, 0, 255), width=2)

    # ── Draw power plants ────────────────────────────────────────────────────
    font = _load_font(24)
    for plant in elec_q.get("nearby_plants", []):
        x, y = to_px(plant["lat"], plant["lon"])
        rgb = _FUEL_COLORS_RGB.get(plant["fuel_label"], _DEFAULT_PLANT_COLOR)
        r = 16
        draw.ellipse([x - r, y - r, x + r, y + r],
                      fill=(*rgb, 230), outline=(255, 255, 255, 200), width=2)

    # ── Draw site marker (5-pointed star) ────────────────────────────────────
    import math as _math
    cx, cy = to_px(lat, lon)
    outer_r, inner_r = 22, 10
    star_pts: list[tuple[float, float]] = []
    for i in range(10):
        angle = _math.radians(-90 + i * 36)  # start at top
        r_use = outer_r if i % 2 == 0 else inner_r
        star_pts.append((cx + r_use * _math.cos(angle), cy + r_use * _math.sin(angle)))
    # White halo
    draw.polygon([(x + 3, y + 3) for x, y in star_pts], fill=(0, 0, 0, 60))
    draw.polygon(star_pts, fill=(212, 85, 62, 255), outline=(255, 255, 255, 255))

    # ── Draw legend ──────────────────────────────────────────────────────────
    legend_items: list[tuple[str, tuple[int, int, int], str]] = []  # (label, rgb, shape)

    # Territory entries — patch color, labeled by utility name
    for i, territory in enumerate(elec_q.get("service_territories", [])):
        rgb_full = [(59, 130, 246), (249, 115, 22)]
        rgb = rgb_full[i % len(rgb_full)]
        name = territory.get("utility_name", f"Utility {i + 1}")
        short = name[:28] + "…" if len(name) > 28 else name
        legend_items.append((short, rgb, "territory"))

    # Transmission line voltage classes
    seen_classes = {tx["voltage_class"] for tx in elec_q.get("tx_map_lines", [])}
    for label, _, _ in _VOLTAGE_CLASSES:
        if label in seen_classes:
            legend_items.append((label, _TX_COLORS[label], "line"))

    # Power plant fuel types
    seen_fuels = {p["fuel_label"] for p in elec_q.get("nearby_plants", [])}
    for fuel in seen_fuels:
        legend_items.append((fuel, _FUEL_COLORS_RGB.get(fuel, _DEFAULT_PLANT_COLOR), "circle"))

    # Site marker entry
    legend_items.append(("Site", (212, 85, 62), "star"))

    if legend_items:
        lx, ly = 20 * scale, 20 * scale
        pad, row_h, swatch = 8 * scale, 22 * scale, 16 * scale
        total_h = len(legend_items) * row_h + pad * 2
        max_w = max(draw.textbbox((0, 0), item[0], font=font)[2] for item in legend_items)
        total_w = swatch + pad + max_w + pad * 2
        draw.rounded_rectangle(
            [lx - pad, ly - pad, lx + total_w, ly + total_h],
            radius=6, fill=(255, 255, 255, 200),
        )
        for i, (label, rgb, shape) in enumerate(legend_items):
            item_y = ly + i * row_h
            sx, sy = lx, item_y + 2
            if shape == "line":
                mid_y = sy + swatch // 2
                draw.line([(sx, mid_y), (sx + swatch, mid_y)], fill=(*rgb, 220), width=4)
            elif shape == "star":
                scx, scy = sx + swatch // 2, sy + swatch // 2
                sr_out, sr_in = 22, 10  # match map marker size
                spts: list[tuple[float, float]] = []
                for k in range(10):
                    ang = _math.radians(-90 + k * 36)
                    sr = sr_out if k % 2 == 0 else sr_in
                    spts.append((scx + sr * _math.cos(ang), scy + sr * _math.sin(ang)))
                draw.polygon(spts, fill=(*rgb, 255), outline=(255, 255, 255, 200))
            elif shape == "territory":
                draw.rectangle([sx, sy, sx + swatch, sy + swatch - 2],
                                fill=(*rgb, 50), outline=(*rgb, 200), width=2)
            else:  # circle or generic swatch
                cr = swatch // 2
                draw.ellipse([sx, sy, sx + swatch, sy + swatch],
                              fill=(*rgb, 220))
            draw.text((lx + swatch + pad, item_y), label,
                       fill=(40, 40, 40, 255), font=font)

    result = Image.alpha_composite(base, overlay).convert("RGB")
    buf = io.BytesIO()
    result.save(buf, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _draw_star(
    draw: "ImageDraw.Draw",
    cx: float,
    cy: float,
    r: int = 22,
    fill: tuple[int, int, int, int] = (212, 85, 62, 255),
) -> None:
    """Draw a 5-pointed star on a Pillow ImageDraw at (cx, cy) with outer radius r."""
    import math as _math
    outer_r = r
    inner_r = r * 0.45
    pts: list[tuple[float, float]] = []
    for i in range(10):
        angle = _math.radians(-90 + i * 36)
        rad = outer_r if i % 2 == 0 else inner_r
        pts.append((cx + rad * _math.cos(angle), cy + rad * _math.sin(angle)))
    # Drop-shadow
    draw.polygon([(x + 2, y + 2) for x, y in pts], fill=(0, 0, 0, 60))
    draw.polygon(pts, fill=fill, outline=(255, 255, 255, 255))


def fetch_water_service_map_b64(
    lat: float,
    lon: float,
    water: dict,
    *,
    token: str | None = None,
) -> str | None:
    """
    Generate a drinking water service area map with Pillow overlays on a Mapbox basemap.

    Accepts the processed water context dict (output of _build_water) which
    has service_geojsons as pre-parsed GeoJSON dicts.
    Shows: service area boundaries (semi-transparent blue) and the site marker.
    """
    if token is None:
        token = get_settings().mapbox_token
    if not token:
        logger.warning("MAPBOX_TOKEN not set — skipping water service map")
        return None

    geojsons = water.get("service_geojsons", []) or []

    # Default ~10 mi radius
    min_lat, max_lat = lat - 0.15, lat + 0.15
    min_lon, max_lon = lon - 0.20, lon + 0.20

    img_px = 800
    zoom = _compute_zoom_for_extent(min_lon, max_lon, min_lat, max_lat, img_px=img_px)
    zoom = max(8.0, min(zoom * 0.90, 13.0))
    center_lat = (min_lat + max_lat) / 2
    center_lon = (min_lon + max_lon) / 2

    retina = "@2x"
    path = (
        f"{_BASE_URL}/light-v11/static"
        f"/{center_lon},{center_lat},{zoom:.2f}"
        f"/{img_px}x{img_px}{retina}"
    )
    params = {"access_token": token, "logo": "false", "attribution": "false"}
    url = f"{path}?{urllib.parse.urlencode(params)}"

    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(url)
            resp.raise_for_status()
            png_bytes = resp.content
    except Exception as exc:
        logger.warning("Water service map basemap fetch failed: %s", exc)
        return None

    base = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    scale = 2

    def to_px(plat: float, plon: float) -> tuple[float, float]:
        return _latlon_to_px(plat, plon, center_lat, center_lon, zoom, img_px, scale)

    # Service area polygons (blue palette)
    palette = [
        (59, 130, 246, 60),    # blue tint fill
        (249, 115, 22, 60),    # orange tint fill
        (16, 185, 129, 60),    # green tint fill
        (139, 92, 246, 60),    # purple tint fill
    ]
    border_palette = [
        (59, 130, 246, 220),
        (249, 115, 22, 220),
        (16, 185, 129, 220),
        (139, 92, 246, 220),
    ]
    for i, gj in enumerate(geojsons[:4]):
        fill = palette[i % len(palette)]
        border = border_palette[i % len(border_palette)]
        _draw_geojson_polygon(draw, gj, center_lat, center_lon, zoom, img_px,
                              color=border, fill=fill, width=2)

    # Site marker (red star)
    sx, sy = to_px(lat, lon)
    _draw_star(draw, sx, sy, r=14, fill=(212, 85, 62, 255))

    result = Image.alpha_composite(base, overlay).convert("RGB")
    buf = io.BytesIO()
    result.save(buf, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def fetch_groundwater_map_b64(
    lat: float,
    lon: float,
    water: dict,
    *,
    token: str | None = None,
) -> str | None:
    """
    Generate a groundwater context map with Pillow overlays on a Mapbox basemap.

    Accepts the processed water context dict (output of _build_water) which
    has aquifer.geom_json as a pre-parsed GeoJSON dict and wells with lat/lon.
    Shows: principal aquifer boundary (teal), USGS monitoring wells colored by
    DTW data availability, and the site marker.
    """
    if token is None:
        token = get_settings().mapbox_token
    if not token:
        logger.warning("MAPBOX_TOKEN not set — skipping groundwater map")
        return None

    wells = water.get("wells", []) or []
    aquifer = water.get("aquifer") or {}

    # ~15 mi radius
    min_lat, max_lat = lat - 0.22, lat + 0.22
    min_lon, max_lon = lon - 0.30, lon + 0.30

    img_px = 800
    zoom = _compute_zoom_for_extent(min_lon, max_lon, min_lat, max_lat, img_px=img_px)
    zoom = max(7.0, min(zoom * 0.90, 13.0))
    center_lat = (min_lat + max_lat) / 2
    center_lon = (min_lon + max_lon) / 2

    retina = "@2x"
    path = (
        f"{_BASE_URL}/outdoors-v12/static"
        f"/{center_lon},{center_lat},{zoom:.2f}"
        f"/{img_px}x{img_px}{retina}"
    )
    params = {"access_token": token, "logo": "false", "attribution": "false"}
    url = f"{path}?{urllib.parse.urlencode(params)}"

    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(url)
            resp.raise_for_status()
            png_bytes = resp.content
    except Exception as exc:
        logger.warning("Groundwater map basemap fetch failed: %s", exc)
        return None

    base = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    scale = 2

    def to_px(plat: float, plon: float) -> tuple[float, float]:
        return _latlon_to_px(plat, plon, center_lat, center_lon, zoom, img_px, scale)

    # Aquifer boundary (teal)
    aq_geom = aquifer.get("geom_json")
    if aq_geom:
        _draw_geojson_polygon(draw, aq_geom, center_lat, center_lon, zoom, img_px,
                              color=(20, 184, 166, 200), fill=(20, 184, 166, 35), width=2)

    # Monitoring wells
    for w in wells:
        wlat, wlon = w.get("lat"), w.get("lon")
        if wlat is None or wlon is None:
            continue
        wx, wy = to_px(wlat, wlon)
        has_dtw = w.get("dtw_typical_ft") is not None
        color = (37, 99, 235, 220) if has_dtw else (156, 163, 175, 200)
        r = 8
        draw.ellipse([wx - r, wy - r, wx + r, wy + r], fill=color, outline=(255, 255, 255, 200), width=2)

    # Site marker (red star)
    sx, sy = to_px(lat, lon)
    _draw_star(draw, sx, sy, r=14, fill=(212, 85, 62, 255))

    result = Image.alpha_composite(base, overlay).convert("RGB")
    buf = io.BytesIO()
    result.save(buf, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
