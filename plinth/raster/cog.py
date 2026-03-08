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
    Returns *dst*.
    """
    work = src

    if reproject_epsg is not None:
        reprojected = dst.with_suffix(".reprojected.tif")
        subprocess.run(
            [
                "gdalwarp",
                "-t_srs", f"EPSG:{reproject_epsg}",
                "-r", "bilinear",
                "-co", "TILED=YES",
                str(work),
                str(reprojected),
            ],
            check=True,
            capture_output=True,
        )
        work = reprojected

    subprocess.run(
        [
            "gdal_translate",
            "-of", "COG",
            "-co", "COMPRESS=DEFLATE",
            "-co", "PREDICTOR=2",
            "-co", "TILED=YES",
            "-co", "BLOCKXSIZE=512",
            "-co", "BLOCKYSIZE=512",
            "-co", "OVERVIEWS=AUTO",
            "-co", "RESAMPLING=AVERAGE",
            str(work),
            str(dst),
        ],
        check=True,
        capture_output=True,
    )

    if reproject_epsg is not None and work != src:
        work.unlink(missing_ok=True)

    return dst
