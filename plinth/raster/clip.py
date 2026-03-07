"""Bounding-box clip helper for COG rasters.

Always buffer the clip by at least one grid cell beyond the AOI before
running slope or other edge-sensitive operations (see Phase 3 notes).
"""
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
    """Clip *src* COG to the given bounding box and write to *dst*.

    *buffer_m* expands the clip extent by this many metres on each side.
    Use ≥ one grid cell (~10 m for 3DEP) when computing slope.

    Raises NotImplementedError until Phase 3.
    """
    raise NotImplementedError("Raster clipping — Phase 3")
