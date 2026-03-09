"""NLCD land cover classification query from MinIO COG tiles."""

from __future__ import annotations

import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from plinth.db.connection import get_connection
from plinth.raster.clip import clip_to_bbox
from plinth.raster.minio import download_cog

_DATASET = "nlcd"
_DEG_PER_M = 0.000009

# NLCD 2019/2021 legend
_NLCD_CLASSES: dict[int, str] = {
    11: "Open Water",
    12: "Perennial Ice/Snow",
    21: "Developed, Open Space",
    22: "Developed, Low Intensity",
    23: "Developed, Medium Intensity",
    24: "Developed, High Intensity",
    31: "Barren Land",
    41: "Deciduous Forest",
    42: "Evergreen Forest",
    43: "Mixed Forest",
    52: "Shrub/Scrub",
    71: "Grassland/Herbaceous",
    81: "Pasture/Hay",
    82: "Cultivated Crops",
    90: "Woody Wetlands",
    95: "Emergent Herbaceous Wetlands",
}

_DEVELOPED_CLASSES = {21, 22, 23, 24}


def _find_tile(lat: float, lon: float) -> str | None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT s3_key
                FROM raster_tiles
                WHERE dataset = %s
                  AND ST_Contains(bounds, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
                ORDER BY dataset_version DESC NULLS LAST
                LIMIT 1
                """,
                (_DATASET, lon, lat),
            )
            row = cur.fetchone()
    return row[0] if row else None


def query_land_cover(lat: float, lon: float, radius_m: float = 500.0) -> dict[str, Any]:
    """
    Return NLCD land cover classification within *radius_m* metres of the point.

    Clips the NLCD COG, counts pixel classes, and returns the modal
    (most common) class, the pixel distribution, and an impervious surface
    percentage based on developed-class pixel fraction.

    Args:
        lat: Latitude (WGS84)
        lon: Longitude (WGS84)
        radius_m: Radius of the AOI in metres (default 500 m)
    """
    s3_key = _find_tile(lat, lon)
    if s3_key is None:
        return {
            "available": False,
            "flag": "No NLCD land cover tile found for this location.",
        }

    buf_deg = radius_m * _DEG_PER_M

    try:
        import numpy as np
        import rasterio

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            raw_path = tmpdir / "nlcd_raw.tif"
            clipped_path = tmpdir / "nlcd_clip.tif"

            download_cog(s3_key, raw_path)

            clip_to_bbox(
                raw_path, clipped_path,
                minx=lon - buf_deg, miny=lat - buf_deg,
                maxx=lon + buf_deg, maxy=lat + buf_deg,
            )

            with rasterio.open(str(clipped_path)) as ds:
                nodata = ds.nodata
                arr = ds.read(1)

        if arr is None or arr.size == 0:
            return {"available": False, "flag": "Empty clip — point may be outside tile."}

        flat = arr.flatten()
        if nodata is not None:
            flat = flat[flat != int(nodata)]

        if flat.size == 0:
            return {"available": False, "flag": "All pixels are nodata."}

        counts = Counter(int(v) for v in flat)
        total = flat.size

        dominant_code = counts.most_common(1)[0][0]
        dominant_label = _NLCD_CLASSES.get(dominant_code, f"Class {dominant_code}")

        developed_pixels = sum(counts.get(c, 0) for c in _DEVELOPED_CLASSES)
        impervious_pct = round(developed_pixels / total * 100, 1)

        distribution = {
            _NLCD_CLASSES.get(code, f"Class {code}"): round(count / total * 100, 1)
            for code, count in counts.most_common()
        }

        return {
            "available": True,
            "source": "USGS National Land Cover Database (NLCD)",
            "radius_m": radius_m,
            "tile_key": s3_key,
            "dominant_class_code": dominant_code,
            "dominant_class": dominant_label,
            "impervious_pct_estimate": impervious_pct,
            "class_distribution_pct": distribution,
        }

    except ImportError:
        return {"available": False, "flag": "rasterio/numpy not available in this environment."}
    except Exception as exc:
        return {"available": False, "flag": f"Land cover query failed: {exc}"}
