"""NOAA NClimGrid 1991-2020 Monthly Gridded Climate Normals ingestor.

Downloads four NetCDF files (tmax, tmin, tavg, prcp) from the NOAA NClimGrid
monthly public S3 bucket. Each file contains the full monthly record from
1895-01 to present (~1,500+ time steps). This ingestor extracts the 1991-2020
period (360 months) and computes 12 monthly means to produce a 12-band
Cloud-Optimized GeoTIFF per variable.

The NClimGrid dataset provides continuous ~5km gridded normals for the entire
CONUS, substantially improving on the station-based noaa_climate_normals table
which is limited to ~8,000 discrete station locations.

Source:    NOAA NClimGrid Monthly public S3 bucket (no auth required)
           https://noaa-nclimgrid-monthly-pds.s3.amazonaws.com/
Resolution: 1/24° (~5 km) for CONUS
Variables:  tavg (°C), tmax (°C), tmin (°C), prcp (mm)
Refresh:    Decadal (next normals update ~2032 for 2001-2030 period)

Note: Files are ~600MB–1GB each; total download ~3GB. This is expected for a
decadal national raster dataset. Run-time for download + processing is 20–60
minutes depending on network and container I/O.
"""
from __future__ import annotations

from typing import Optional

from plinth.ingest.base import BaseIngestor
from plinth.raster.cog import to_cog
from plinth.raster.minio import upload_cog

_DATASET = "noaa-nclimgrid"
_VERSION = "1991-2020"

# NOAA NClimGrid Monthly public bucket (full monthly history from 1895)
_BASE_URL = "https://noaa-nclimgrid-monthly-pds.s3.amazonaws.com"

# Variable short name → (filename, NetCDF variable name inside the file)
_VARIABLES: dict[str, tuple[str, str]] = {
    "tavg": ("nclimgrid_tavg.nc", "tavg"),
    "tmax": ("nclimgrid_tmax.nc", "tmax"),
    "tmin": ("nclimgrid_tmin.nc", "tmin"),
    "prcp": ("nclimgrid_prcp.nc", "prcp"),
}

# NClimGrid starts in January 1895.
# 1991-2020 normals period:
#   start index (0-based): (1991 - 1895) * 12 = 1152  → Jan 1991
#   end index (0-based, inclusive): 1152 + 359 = 1511   → Dec 2020
_NORMALS_START_YEAR = 1991
_NORMALS_END_YEAR = 2020
_SERIES_START_YEAR = 1895
_IDX_START = (_NORMALS_START_YEAR - _SERIES_START_YEAR) * 12  # 1152
_IDX_END = _IDX_START + (_NORMALS_END_YEAR - _NORMALS_START_YEAR + 1) * 12  # 1512 (exclusive)

_MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


class NoaaNclimgridIngestor(BaseIngestor):
    """Download NOAA NClimGrid monthly history and compute 1991-2020 normals.

    Each variable is stored as a 12-band COG where band N = calendar month N
    (band 1 = January, band 12 = December), containing the 30-year mean value
    for that variable in that calendar month over 1991-2020.

    MinIO key pattern: noaa-nclimgrid/1991-2020/{variable}.tif
    """

    source_name = "noaa-nclimgrid"
    update_frequency = "decadal"

    def download(self, region: Optional[str] = None) -> None:
        """Download all four NClimGrid NetCDF files from NOAA S3."""
        for var, (filename, _) in _VARIABLES.items():
            dest = self.staging_dir / filename
            url = f"{_BASE_URL}/{filename}"
            self._log(f"Checking {var} NetCDF (~600MB–1GB)…")
            fetched = self._download_if_changed(url, dest)
            if not fetched:
                self._log(f"  {var}: up-to-date (ETag matched).")

    def validate(self) -> None:
        """Verify all four NetCDF files are present and readable."""
        import rasterio

        for var, (filename, nc_var) in _VARIABLES.items():
            path = self.staging_dir / filename
            if not path.exists():
                raise ValueError(f"NetCDF file missing: {path.name}")
            if path.stat().st_size < 10_000_000:
                raise ValueError(
                    f"{path.name} suspiciously small ({path.stat().st_size:,} bytes)"
                )
            nc_path = f"NETCDF:{path}:{nc_var}"
            try:
                with rasterio.open(nc_path) as ds:
                    n_bands = ds.count
                    if n_bands < _IDX_END:
                        raise ValueError(
                            f"{var}: need ≥{_IDX_END} bands for 1991-2020, "
                            f"got {n_bands}"
                        )
                    self._log(
                        f"  {var}: {n_bands} bands, CRS={ds.crs}, "
                        f"shape={ds.height}×{ds.width} ✓"
                    )
            except Exception as exc:
                raise ValueError(f"Cannot open {nc_path}: {exc}") from exc
        self._log("Validation passed — all 4 NetCDF files readable with sufficient bands.")

    def load(self) -> None:
        """Compute 30-year monthly means and upload 12-band COGs to MinIO."""
        import numpy as np
        import rasterio
        from plinth.db.connection import get_connection

        for var, (filename, nc_var) in _VARIABLES.items():
            nc_path_str = f"NETCDF:{self.staging_dir / filename}:{nc_var}"
            raw_path = self.staging_dir / f"{var}_raw.tif"
            cog_path = self.staging_dir / f"{var}.tif"

            self._log(f"Processing {var}: extracting 1991-2020 bands and averaging…")

            with rasterio.open(nc_path_str) as src:
                profile = src.profile.copy()
                nodata_in = src.nodata
                height, width = src.height, src.width

                # Build 12 monthly mean arrays (Jan=0 … Dec=11)
                monthly_means: list = []
                for month in range(12):
                    # Collect all 30 bands for this calendar month
                    band_indices = [
                        _IDX_START + year * 12 + month
                        for year in range(_NORMALS_END_YEAR - _NORMALS_START_YEAR + 1)
                    ]
                    # rasterio band indices are 1-based
                    bands_data = np.array(
                        [src.read(i + 1).astype("float32") for i in band_indices]
                    )

                    # Mask nodata before averaging
                    if nodata_in is not None:
                        mask = bands_data == float(nodata_in)
                        bands_data = np.where(mask, np.nan, bands_data)

                    mean = np.nanmean(bands_data, axis=0)
                    # Write -9999.0 where all 30 years were nodata
                    mean = np.where(np.isnan(mean), -9999.0, mean)
                    monthly_means.append(mean.astype("float32"))
                    self._log(
                        f"  {var} month {month + 1:02d} ({_MONTH_NAMES[month]}): "
                        f"mean computed from {len(band_indices)} years"
                    )

            profile.update(
                driver="GTiff",
                count=12,
                dtype="float32",
                nodata=-9999.0,
                compress=None,  # to_cog handles compression
            )
            # Drop any NetCDF-specific driver metadata that GTiff doesn't need
            profile.pop("SUBDATASETS", None)

            with rasterio.open(raw_path, "w", **profile) as dst:
                for i, arr in enumerate(monthly_means, start=1):
                    dst.write(arr, i)
                    dst.update_tags(i, description=f"{var}_{_MONTH_NAMES[i-1]}")

            self._log(f"  Converting to COG: {var}.tif")
            to_cog(raw_path, cog_path)
            raw_path.unlink(missing_ok=True)

            s3_key = f"{_DATASET}/{_VERSION}/{var}.tif"
            self._log(f"  Uploading to MinIO: {s3_key}")
            upload_cog(cog_path, s3_key)

            with rasterio.open(cog_path) as ds:
                bounds = ds.bounds
                res_deg = (ds.res[0] + ds.res[1]) / 2
                res_m = res_deg * 111_320

            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO raster_tiles
                            (dataset, s3_key, bounds, resolution_m, tile_id, dataset_version)
                        VALUES (%(dataset)s, %(s3_key)s,
                                ST_MakeEnvelope(%(minx)s, %(miny)s, %(maxx)s, %(maxy)s, 4326),
                                %(res_m)s, %(tile_id)s, %(version)s)
                        ON CONFLICT (s3_key) DO UPDATE SET
                            bounds          = EXCLUDED.bounds,
                            resolution_m    = EXCLUDED.resolution_m,
                            dataset_version = EXCLUDED.dataset_version
                        """,
                        {
                            "dataset": _DATASET,
                            "s3_key": s3_key,
                            "minx": bounds.left,
                            "miny": bounds.bottom,
                            "maxx": bounds.right,
                            "maxy": bounds.top,
                            "res_m": round(res_m, 1),
                            "tile_id": var,
                            "version": _VERSION,
                        },
                    )
                conn.commit()
            self._log(f"  Registered tile for {var} in raster_tiles (res ~{res_m:.0f} m).")

    def register(self) -> None:
        """Register this source in data_source_registry."""
        self._upsert_registry(
            version=_VERSION,
            coverage_region="national",
            notes=(
                "NOAA NClimGrid 1991-2020 monthly gridded normals (computed from full "
                "monthly history 1895-present in noaa-nclimgrid-monthly-pds S3 bucket). "
                "4 variables (tavg/tmax/tmin/prcp), 12-band COGs, ~5km CONUS coverage. "
                "Pre-computed normals are not available; 30-year means computed on ingest."
            ),
        )
