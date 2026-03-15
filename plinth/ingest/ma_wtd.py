"""Ma et al. (2025) CONUS Water Table Depth — COG raster ingestor.

Downloads the single-file national water table depth raster from Zenodo,
converts to a Cloud-Optimized GeoTIFF, stores in MinIO, and registers the
tile in ``raster_tiles``.

Reference
---------
Ma, Y. et al. (2026). High resolution US water table depth estimates.
Commun Earth Environ 7, 45. https://doi.org/10.1038/s43247-025-03094-3

Dataset  : Zenodo record 18504963
File     : wtd_mean_estimate_RF_additional_inputs_dummy_drop0LP_1s_CONUS2_m_v_20240813.tif
Size     : ~36.6 GB (raw GeoTIFF)
MD5      : ffb3476a1134e61c9039530e27d5d409
Units    : meters depth (positive = deeper below surface)
Resolution: 1 arcsecond (~30 m) across CONUS

Storage
-------
MinIO key : ``ma-wtd/2025/wtd_mean_conus.tif``
Dataset   : ``ma-wtd`` in ``raster_tiles``

Query time: point-sample the single CONUS COG via ``plinth.query.water_infrastructure``
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional

from plinth.ingest.base import BaseIngestor

_DATASET = "ma-wtd"
_VERSION = "2025"
_ZENODO_RECORD = "18504963"
_REMOTE_FILENAME = (
    "wtd_mean_estimate_RF_additional_inputs_dummy_drop0LP_1s_CONUS2_m_v_20240813.tif"
)
_ZENODO_URL = f"https://zenodo.org/records/{_ZENODO_RECORD}/files/{_REMOTE_FILENAME}"
_EXPECTED_MD5 = "ffb3476a1134e61c9039530e27d5d409"
_S3_KEY = f"{_DATASET}/{_VERSION}/wtd_mean_conus.tif"
_TILE_ID = "wtd_mean_conus"


class MaWtdIngestor(BaseIngestor):
    """Download Ma et al. WTD GeoTIFF → COG → MinIO → raster_tiles."""

    source_name = "ma-wtd"
    update_frequency = "decadal"

    def download(self, region: Optional[str] = None) -> None:
        """Download the 36.6 GB GeoTIFF from Zenodo using curl (resumable)."""
        dest = self.staging_dir / _REMOTE_FILENAME
        md5_file = self.staging_dir / f"{_REMOTE_FILENAME}.md5"

        # Skip if already downloaded and MD5 matches
        if dest.exists() and md5_file.exists():
            stored_md5 = md5_file.read_text().strip()
            if stored_md5 == _EXPECTED_MD5:
                self._log(f"Already downloaded and verified: {dest.name}")
                return
            else:
                self._log(f"MD5 mismatch on existing file — re-downloading.")
                dest.unlink(missing_ok=True)

        self._log(f"Downloading {_REMOTE_FILENAME} from Zenodo (~36.6 GB)…")
        self._log("This download may take 30-90 minutes depending on connection speed.")
        self._log(f"URL: {_ZENODO_URL}")

        # Use curl for large-file download: supports resume (-C -), shows progress
        result = subprocess.run(
            [
                "curl",
                "--location",          # follow redirects
                "--continue-at", "-",  # resume partial download
                "--retry", "3",
                "--retry-delay", "10",
                "--output", str(dest),
                "--progress-bar",
                _ZENODO_URL,
            ],
            check=True,
        )

        self._log(f"Download complete: {dest.name} ({dest.stat().st_size / 1e9:.2f} GB)")
        md5_file.write_text(_compute_md5(dest))
        self._log(f"MD5 computed and saved.")

    def validate(self) -> None:
        """Verify file integrity (MD5) and that rasterio can open the file."""
        import rasterio

        raw = self.staging_dir / _REMOTE_FILENAME
        if not raw.exists():
            raise FileNotFoundError(f"Downloaded file not found: {raw}")

        self._log("Verifying MD5…")
        actual_md5 = _compute_md5(raw)
        if actual_md5 != _EXPECTED_MD5:
            raise ValueError(
                f"MD5 mismatch for {raw.name}: "
                f"expected {_EXPECTED_MD5}, got {actual_md5}"
            )
        self._log("MD5 OK.")

        self._log("Checking rasterio can open file…")
        with rasterio.open(raw) as ds:
            if ds.count < 1:
                raise ValueError(f"Expected ≥1 band, got {ds.count}")
            w, h = ds.width, ds.height
            crs = ds.crs
            self._log(f"  {w}×{h} px, 1 band, CRS: {crs.to_epsg() or crs.to_string()}")

    def load(self) -> None:
        """Reproject + convert to COG in one gdalwarp pass, upload to MinIO, register tile."""
        import subprocess
        import rasterio
        from plinth.raster.minio import upload_cog
        from plinth.db.connection import get_connection

        raw = self.staging_dir / _REMOTE_FILENAME
        cog_path = self.staging_dir / "wtd_mean_conus_cog.tif"

        # Check if already uploaded to MinIO
        if _tile_exists_in_db(_S3_KEY):
            self._log(f"Tile already registered in raster_tiles: {_S3_KEY} — skipping COG and upload.")
            return

        # Clean up any stale intermediate file from a prior run
        stale = self.staging_dir / "wtd_mean_conus_cog.reprojected.tif"
        if stale.exists():
            self._log(f"Removing stale intermediate file: {stale.name}")
            stale.unlink()

        # Single-pass: reproject LCC → WGS84 and write COG directly via gdalwarp -of COG.
        # This avoids a ~110-180 GB uncompressed intermediate file.
        # GDAL 3.6+ supports COG output from gdalwarp.
        self._log("Reprojecting to EPSG:4326 and converting to COG in one pass…")
        self._log("  (gdalwarp -of COG — expect 2–4 hours for 36.6 GB input)")
        subprocess.run(
            [
                "gdalwarp",
                "-t_srs", "EPSG:4326",
                "-r", "bilinear",
                "-of", "COG",
                "-co", "COMPRESS=DEFLATE",
                "-co", "PREDICTOR=2",
                "-co", "BIGTIFF=YES",
                "-co", "OVERVIEWS=AUTO",
                "-co", "RESAMPLING=AVERAGE",
                "-wo", "NUM_THREADS=ALL_CPUS",
                str(raw),
                str(cog_path),
            ],
            check=True,
        )
        size_gb = cog_path.stat().st_size / 1e9
        self._log(f"  COG written: {cog_path.name} ({size_gb:.2f} GB)")

        self._log(f"Uploading to MinIO: {_S3_KEY}")
        upload_cog(cog_path, _S3_KEY)
        self._log("  Upload complete.")

        with rasterio.open(cog_path) as ds:
            bounds = ds.bounds
            res_deg = (ds.res[0] + ds.res[1]) / 2
            res_m = res_deg * 111_320  # approx degrees → meters at mid-lat

        self._log("Registering tile in raster_tiles…")
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO raster_tiles
                        (dataset, s3_key, bounds, resolution_m, tile_id, dataset_version)
                    VALUES (%(dataset)s, %(s3_key)s,
                            ST_MakeEnvelope(%(minx)s,%(miny)s,%(maxx)s,%(maxy)s, 4326),
                            %(res_m)s, %(tile_id)s, %(version)s)
                    ON CONFLICT (s3_key) DO UPDATE SET
                        bounds           = EXCLUDED.bounds,
                        resolution_m     = EXCLUDED.resolution_m,
                        dataset_version  = EXCLUDED.dataset_version
                    """,
                    {
                        "dataset":  _DATASET,
                        "s3_key":   _S3_KEY,
                        "minx":     bounds.left,
                        "miny":     bounds.bottom,
                        "maxx":     bounds.right,
                        "maxy":     bounds.top,
                        "res_m":    round(res_m, 1),
                        "tile_id":  _TILE_ID,
                        "version":  _VERSION,
                    },
                )
            conn.commit()
        self._log(f"  Tile registered (res ~{res_m:.0f} m).")

    def register(self) -> None:
        """Upsert a row in data_source_registry."""
        self._upsert_registry(
            version=_VERSION,
            coverage_region="national",
            notes=(
                "Ma et al. (2026) 1-arcsecond (~30 m) CONUS water table depth model. "
                "CC-BY 4.0. DOI: 10.1038/s43247-025-03094-3. "
                "Model: random forest, r=0.79, RMSE=14.94 m (~49 ft). "
                "Use for site-context planning only — not a substitute for site investigation. "
                f"Zenodo record {_ZENODO_RECORD}. MinIO key: {_S3_KEY}."
            ),
        )


# ── Helpers ────────────────────────────────────────────────────────────────────

def _compute_md5(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    """Compute MD5 of a (potentially very large) file."""
    h = hashlib.md5()
    with open(path, "rb") as fh:
        while chunk := fh.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


def _tile_exists_in_db(s3_key: str) -> bool:
    from plinth.db.connection import get_connection
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM raster_tiles WHERE s3_key = %s", (s3_key,)
            )
            return cur.fetchone() is not None
