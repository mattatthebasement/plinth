"""COG (Cloud-Optimized GeoTIFF) conversion helpers.

Wraps gdal_translate to produce tiled, overviewed COGs suitable for
efficient range-request access in MinIO.
"""
import subprocess
from pathlib import Path


def to_cog(src: Path, dst: Path, *, reproject_epsg: int | None = None) -> Path:
    """Convert *src* raster to a Cloud-Optimized GeoTIFF at *dst*.

    If *reproject_epsg* is given, the source is first reprojected using
    gdalwarp before COG conversion.

    Raises subprocess.CalledProcessError on failure.
    """
    raise NotImplementedError("COG conversion — Phase 3")
