"""Bounding-box clip helper for COG rasters.

Always buffer the clip by at least one grid cell beyond the AOI before
running slope or other edge-sensitive operations (see Phase 3 notes).
"""
import subprocess
from pathlib import Path


def clip_to_bbox(
    src: Path,
    dst: Path,
    *,
    minx: float,
    miny: float,
    maxx: float,
    maxy: float,
    buffer_m: float = 0.0,
) -> Path:
    """Clip *src* raster to the given bounding box and write to *dst*.

    *buffer_m* expands the clip extent by approximately this many metres on
    each side (converted to degrees at mid-latitude ≈ 0.00001° per metre).
    Use ≥ one grid cell (~10 m for 3DEP) when computing slope to avoid
    incorrect edge values.

    Returns *dst*.  Raises subprocess.CalledProcessError on failure.
    """
    if buffer_m > 0:
        # Approx degrees: 1 m ≈ 0.000009° at mid-latitudes (conservative)
        buf_deg = buffer_m * 0.000009
        minx -= buf_deg
        miny -= buf_deg
        maxx += buf_deg
        maxy += buf_deg

    subprocess.run(
        [
            "gdalwarp",
            "-te", str(minx), str(miny), str(maxx), str(maxy),
            "-te_srs", "EPSG:4326",
            str(src),
            str(dst),
        ],
        check=True,
        capture_output=True,
    )
    return dst
