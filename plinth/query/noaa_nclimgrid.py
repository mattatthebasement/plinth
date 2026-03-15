"""NOAA NClimGrid gridded climate normals query.

Samples monthly tmax, tmin, tavg, and prcp at a given lat/lon from the
12-band COGs stored in MinIO (one band per calendar month, Jan=1..Dec=12).

NClimGrid native units: temperature in °C, precipitation in mm.
This function converts to °F and inches to match the report's expected units.

Each COG covers the full CONUS at ~5km (~1/24°) resolution. A single tile
per variable is registered in raster_tiles with tile_id = variable name.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from plinth.db.connection import get_connection
from plinth.raster.minio import download_cog

_DATASET = "noaa-nclimgrid"
_NODATA = -9999.0
_MONTH_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                 "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _c_to_f(c: float) -> float:
    return c * 9.0 / 5.0 + 32.0


def _mm_to_in(mm: float) -> float:
    return mm / 25.4


def _find_tile(var: str) -> str | None:
    """Return s3_key for the given NClimGrid variable tile, or None."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT s3_key FROM raster_tiles
                WHERE dataset = %s AND tile_id = %s
                LIMIT 1
                """,
                (_DATASET, var),
            )
            row = cur.fetchone()
    return row[0] if row else None


def _sample_12band_cog(s3_key: str, lat: float, lon: float) -> list[float | None]:
    """Download a 12-band COG and return the 12 pixel values at (lat, lon)."""
    import rasterio

    with tempfile.TemporaryDirectory() as tmpdir:
        local = Path(tmpdir) / Path(s3_key).name
        download_cog(s3_key, local)

        with rasterio.open(local) as ds:
            row_idx, col_idx = ds.index(lon, lat)
            window = rasterio.windows.Window(col_idx, row_idx, 1, 1)
            data = ds.read(list(range(1, 13)), window=window)  # shape (12,1,1)
            nodata = ds.nodata or _NODATA

    result: list[float | None] = []
    for band_val in data[:, 0, 0]:
        v = float(band_val)
        result.append(None if abs(v - nodata) < 1.0 else v)
    return result


def query_noaa_nclimgrid(lat: float, lon: float) -> dict[str, Any]:
    """
    Return NOAA NClimGrid 1991-2020 gridded climate normals at the given point.

    Samples tmax, tmin, tavg, and prcp from the 12-band COGs stored in MinIO.
    Temperature returned in °F; precipitation returned in inches/month.

    Falls back gracefully if tiles are unavailable.
    """
    tiles: dict[str, str | None] = {
        var: _find_tile(var) for var in ("tmax", "tmin", "tavg", "prcp")
    }

    if not any(tiles.values()):
        return {
            "available": False,
            "flag": "NClimGrid tiles not found in raster_tiles.",
        }

    try:
        tmax_raw = _sample_12band_cog(tiles["tmax"], lat, lon) if tiles["tmax"] else [None] * 12
        tmin_raw = _sample_12band_cog(tiles["tmin"], lat, lon) if tiles["tmin"] else [None] * 12
        tavg_raw = _sample_12band_cog(tiles["tavg"], lat, lon) if tiles["tavg"] else [None] * 12
        prcp_raw = _sample_12band_cog(tiles["prcp"], lat, lon) if tiles["prcp"] else [None] * 12
    except Exception as exc:
        return {
            "available": False,
            "flag": f"NClimGrid sampling error: {exc}",
        }

    def _monthly_f(raw: list[float | None]) -> list[dict]:
        return [
            {"month": _MONTH_LABELS[i], "value": round(_c_to_f(v), 1) if v is not None else None}
            for i, v in enumerate(raw)
        ]

    def _monthly_in(raw: list[float | None]) -> list[dict]:
        return [
            {"month": _MONTH_LABELS[i], "value": round(_mm_to_in(v), 2) if v is not None else None}
            for i, v in enumerate(raw)
        ]

    return {
        "available": True,
        "source": "NOAA NClimGrid 1991–2020 gridded normals (~5 km)",
        "tmax_f": _monthly_f(tmax_raw),
        "tmin_f": _monthly_f(tmin_raw),
        "tavg_f": _monthly_f(tavg_raw),
        "prcp_in": _monthly_in(prcp_raw),
    }
