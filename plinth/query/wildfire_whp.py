"""Wildfire Hazard Potential query — reads WHP raster COG from MinIO."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from plinth.db.connection import get_connection
from plinth.raster.minio import download_cog

_DATASET = "usda-whp"
_NATIONAL_MAX = 144153  # observed national max from ImageServer metadata


def query_wildfire_whp(lat: float, lon: float) -> dict[str, Any]:
    """Return USDA WHP 2023 continuous index value from local COG tile."""
    s3_key = _find_tile(lat, lon)
    if s3_key is None:
        return {
            "available": False,
            "flag": "Wildfire hazard raster tile not found for this location.",
        }

    whp_value = _sample_cog(s3_key, lat, lon, band=1)
    if whp_value is None:
        return {
            "available": False,
            "flag": "Wildfire hazard data unavailable for this location.",
        }

    return {
        "available": True,
        "source": "USDA Forest Service Wildfire Hazard Potential 2023 (270m)",
        "citation": (
            "An index of the relative potential for high-intensity, hard-to-control wildfire "
            "based on fire occurrence, burn probability, and LANDFIRE 2020 fuel conditions. "
            "Not a real-time fire risk measure."
        ),
        "whp_value": int(whp_value),
        "whp_national_max": _NATIONAL_MAX,
        "resolution_m": 270,
    }


def _find_tile(lat: float, lon: float) -> str | None:
    """Return the s3_key of the WHP tile that contains (lat, lon)."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT s3_key FROM raster_tiles
                WHERE dataset = %s
                  AND ST_Contains(bounds, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
                ORDER BY resolution_m
                LIMIT 1
                """,
                (_DATASET, lon, lat),
            )
            row = cur.fetchone()
    return row[0] if row else None


def _sample_cog(s3_key: str, lat: float, lon: float, band: int) -> float | None:
    """Download the COG and read the pixel value at (lat, lon)."""
    import rasterio

    with tempfile.TemporaryDirectory() as tmp:
        local = Path(tmp) / "tile.tif"
        download_cog(s3_key, local)
        with rasterio.open(local) as ds:
            row_idx, col_idx = ds.index(lon, lat)
            window = rasterio.windows.Window(col_idx, row_idx, 1, 1)
            data = ds.read(band, window=window)
            val = float(data[0, 0])
            nodata = ds.nodata
    if nodata is not None and val == nodata:
        return None
    return val

