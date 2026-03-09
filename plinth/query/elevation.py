"""USGS 3DEP elevation point query from MinIO COG tiles."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from plinth.db.connection import get_connection
from plinth.raster.minio import download_cog

_DATASET = "usgs-3dep"


def _find_tile(lat: float, lon: float) -> tuple[str, float | None] | None:
    """Return (s3_key, resolution_m) for the 3DEP tile that covers the point."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT s3_key, resolution_m
                FROM raster_tiles
                WHERE dataset = %s
                  AND ST_Contains(bounds, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
                ORDER BY resolution_m ASC
                LIMIT 1
                """,
                (_DATASET, lon, lat),
            )
            row = cur.fetchone()
    if row is None:
        return None
    return row[0], float(row[1]) if row[1] is not None else None


def query_elevation(lat: float, lon: float) -> dict[str, Any]:
    """
    Return ground elevation (metres) at the given point from USGS 3DEP.

    Downloads the covering COG tile from MinIO, extracts the pixel value at
    (lat, lon) using rasterio, and returns the result.
    """
    tile = _find_tile(lat, lon)
    if tile is None:
        return {
            "available": False,
            "flag": "No USGS 3DEP elevation tile found for this location.",
        }

    s3_key, resolution_m = tile

    try:
        import rasterio
        from rasterio.windows import from_bounds

        with tempfile.TemporaryDirectory() as tmpdir:
            local_path = Path(tmpdir) / "dem.tif"
            download_cog(s3_key, local_path)

            with rasterio.open(str(local_path)) as ds:
                nodata = ds.nodata
                # Sample the single pixel at the point
                values = list(ds.sample([(lon, lat)]))

        if not values:
            return {"available": False, "flag": "Failed to sample elevation raster."}

        elev_m = float(values[0][0])

        if nodata is not None and abs(elev_m - nodata) < 1e-6:
            return {
                "available": False,
                "flag": "No elevation data at this location (nodata pixel).",
            }

        return {
            "available": True,
            "source": "USGS 3D Elevation Program (3DEP)",
            "elevation_m": round(elev_m, 2),
            "elevation_ft": round(elev_m * 3.28084, 1),
            "resolution_m": resolution_m,
            "tile_key": s3_key,
        }

    except ImportError:
        return {"available": False, "flag": "rasterio not available in this environment."}
    except Exception as exc:
        return {"available": False, "flag": f"Elevation query failed: {exc}"}
