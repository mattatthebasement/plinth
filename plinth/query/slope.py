"""Slope query from USGS 3DEP DEM using gdaldem + rasterio."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Any

from plinth.db.connection import get_connection
from plinth.raster.clip import clip_to_bbox
from plinth.raster.minio import download_cog

_DATASET = "usgs-3dep"
_BUFFER_M = 20.0        # ≥ one 3DEP grid cell to avoid gdaldem edge artefacts
_DEG_PER_M = 0.000009   # approx degrees per metre at mid-latitudes


def _find_tile(lat: float, lon: float) -> tuple[str, float | None] | None:
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
    return (row[0], float(row[1]) if row[1] else None) if row else None


def query_slope(lat: float, lon: float, radius_m: float = 100.0) -> dict[str, Any]:
    """
    Return mean and max slope (%) within *radius_m* metres of the point.

    Clips a buffered AOI from the 3DEP DEM (with an additional edge margin
    of ≥ one grid cell), runs ``gdaldem slope``, then computes statistics
    over the unpadded AOI.

    Args:
        lat: Latitude (WGS84)
        lon: Longitude (WGS84)
        radius_m: Radius of the AOI in metres (default 100 m)
    """
    tile = _find_tile(lat, lon)
    if tile is None:
        return {
            "available": False,
            "flag": "No USGS 3DEP elevation tile found for this location.",
        }

    s3_key, resolution_m = tile

    total_buf_deg = (radius_m + _BUFFER_M) * _DEG_PER_M
    aoi_buf_deg = radius_m * _DEG_PER_M

    try:
        import numpy as np
        import rasterio

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            raw_path = tmpdir / "dem_raw.tif"
            clipped_path = tmpdir / "dem_clipped.tif"
            slope_path = tmpdir / "slope.tif"
            aoi_slope_path = tmpdir / "slope_aoi.tif"

            download_cog(s3_key, raw_path)

            # Clip DEM with edge buffer
            clip_to_bbox(
                raw_path, clipped_path,
                minx=lon - total_buf_deg, miny=lat - total_buf_deg,
                maxx=lon + total_buf_deg, maxy=lat + total_buf_deg,
            )

            # Compute percent slope using gdaldem.
            # -s 111120 converts horizontal units (degrees) to metres so
            # that the rise/run ratio produces correct percent values.
            subprocess.run(
                ["gdaldem", "slope", str(clipped_path), str(slope_path), "-p", "-s", "111120"],
                check=True, capture_output=True,
            )

            # Clip slope raster to actual AOI (no edge padding)
            clip_to_bbox(
                slope_path, aoi_slope_path,
                minx=lon - aoi_buf_deg, miny=lat - aoi_buf_deg,
                maxx=lon + aoi_buf_deg, maxy=lat + aoi_buf_deg,
            )

            with rasterio.open(str(aoi_slope_path)) as ds:
                nodata = ds.nodata
                arr = ds.read(1).astype(float)

        # Mask nodata
        if nodata is not None:
            arr = arr[arr != nodata]

        valid = arr[np.isfinite(arr)]
        if valid.size == 0:
            return {"available": False, "flag": "No valid slope pixels in AOI."}

        mean_pct = round(float(np.mean(valid)), 2)
        max_pct = round(float(np.max(valid)), 2)

        result: dict[str, Any] = {
            "available": True,
            "source": "USGS 3D Elevation Program (3DEP)",
            "radius_m": radius_m,
            "resolution_m": resolution_m,
            "mean_slope_pct": mean_pct,
            "max_slope_pct": max_pct,
        }

        if max_pct > 15:
            result["flag"] = (
                f"Maximum slope of {max_pct}% within {radius_m}m radius. "
                "Slopes >15% may require engineering review for grading and drainage."
            )

        return result

    except ImportError:
        return {"available": False, "flag": "rasterio/numpy not available in this environment."}
    except Exception as exc:
        return {"available": False, "flag": f"Slope query failed: {exc}"}
