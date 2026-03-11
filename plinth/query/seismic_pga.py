"""Seismic hazard PGA query — reads design-value raster COG from MinIO."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from plinth.db.connection import get_connection
from plinth.raster.minio import download_cog

_DATASET = "usgs-seismic"


def query_seismic_pga(lat: float, lon: float) -> dict[str, Any]:
    """Return USGS NEHRP 2020 seismic design values from local COG tile.

    The 3-band COG stores: band 1 = PGA (g), band 2 = Ss (g), band 3 = S1 (g).
    Risk category II, site class C.
    """
    s3_key = _find_tile(lat, lon)
    if s3_key is None:
        return {
            "available": False,
            "flag": "Seismic hazard raster tile not found for this location.",
        }

    values = _sample_cog_3band(s3_key, lat, lon)
    if values is None:
        return {
            "available": False,
            "flag": "Seismic hazard data unavailable for this location.",
        }

    pga, ss, s1 = values
    return {
        "available": True,
        "source": "USGS NEHRP 2020 Seismic Hazard Model",
        "note": "Raw design values only. No Seismic Design Category determination is provided.",
        "risk_category": "II",
        "site_class": "C",
        "pgam_g": pga,
        "ss_g": ss,
        "s1_g": s1,
    }


def _find_tile(lat: float, lon: float) -> str | None:
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


def _sample_cog_3band(
    s3_key: str, lat: float, lon: float
) -> tuple[float, float, float] | None:
    """Download the 3-band seismic COG and read PGA/Ss/S1 at (lat, lon)."""
    import rasterio

    with tempfile.TemporaryDirectory() as tmp:
        local = Path(tmp) / "tile.tif"
        download_cog(s3_key, local)
        with rasterio.open(local) as ds:
            row_idx, col_idx = ds.index(lon, lat)
            window = rasterio.windows.Window(col_idx, row_idx, 1, 1)
            bands = ds.read([1, 2, 3], window=window)
            nodata = ds.nodata

    vals = [float(bands[i, 0, 0]) for i in range(3)]
    if nodata is not None and any(v == nodata for v in vals):
        return None
    return (vals[0], vals[1], vals[2])

