"""SoilGrids 250m depth-to-bedrock ingestor.

Downloads two layers from the ISRIC SoilGrids v1.0 data archive for the globe,
clips to CONUS, converts to Cloud-Optimized GeoTIFFs, stores in MinIO, and
registers in raster_tiles:

  BDRICM  — Depth to bedrock (R horizon), absolute (cm)
              MinIO key: soilgrids-bedrock/v2017/bdricm_conus.tif
  BDRLOG  — Probability of having bedrock within 200 cm (fraction 0–1)
              MinIO key: soilgrids-bedrock/v2017/bdrlog_conus.tif

Source: ISRIC SoilGrids 250m v2017 archive
  https://files.isric.org/soilgrids/former/2017-03-10/data/

BDRICM global: ~1.4 GB; BDRLOG global: ~2.6 GB (WGS84 geographic coordinates)
CONUS clip reduces size significantly before COG conversion.

Citation: Hengl T et al. (2017) SoilGrids250m: Global gridded soil information based
on machine learning. PLOS ONE 12(2):e0169748. https://doi.org/10.1371/journal.pone.0169748
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

import rasterio

from plinth.ingest.base import BaseIngestor
from plinth.raster.minio import upload_cog

_DATASET = "soilgrids-bedrock"
_VERSION = "v2017"

_BASE_URL = "https://files.isric.org/soilgrids/former/2017-03-10/data"

_LAYERS = {
    "bdricm": {
        "url": f"{_BASE_URL}/BDRICM_M_250m_ll.tif",
        "description": "Depth to bedrock (absolute, cm)",
        "s3_key": "soilgrids-bedrock/v2017/bdricm_conus.tif",
        "tile_id": "bdricm_conus",
    },
    "bdrlog": {
        "url": f"{_BASE_URL}/BDRLOG_M_250m_ll.tif",
        "description": "Probability of bedrock within 200 cm (0–1)",
        "s3_key": "soilgrids-bedrock/v2017/bdrlog_conus.tif",
        "tile_id": "bdrlog_conus",
    },
}

# CONUS bounding box (WGS84)
_CONUS_WEST = -125.0
_CONUS_SOUTH = 24.0
_CONUS_EAST = -66.0
_CONUS_NORTH = 50.0


class SoilgridsBedrockIngestor(BaseIngestor):
    """Download SoilGrids 250m depth-to-bedrock global rasters, clip to CONUS, store as COGs."""

    source_name = "soilgrids-bedrock"
    update_frequency = "decadal"

    def download(self, region: Optional[str] = None) -> None:
        for name, layer in _LAYERS.items():
            dest = self.staging_dir / f"{name}_global.tif"
            self._log(f"  Downloading {layer['description']} (~{self._expected_gb(name):.1f} GB)…")
            self._download_if_changed(layer["url"], dest)
            self._log(f"  {name}: {dest.stat().st_size / 1e9:.2f} GB on disk.")

    def _expected_gb(self, name: str) -> float:
        return 1.4 if name == "bdricm" else 2.6

    def validate(self) -> None:
        for name in _LAYERS:
            dest = self.staging_dir / f"{name}_global.tif"
            if not dest.exists():
                raise ValueError(f"Global GeoTIFF not found: {dest}")
            if dest.stat().st_size < 500_000_000:
                raise ValueError(
                    f"Global GeoTIFF suspiciously small ({dest.stat().st_size / 1e6:.0f} MB): {dest}"
                )
            try:
                with rasterio.open(dest) as ds:
                    if ds.count == 0:
                        raise ValueError(f"No bands in {dest}")
            except Exception as exc:
                raise ValueError(f"Cannot open {dest} with rasterio: {exc}") from exc
        self._log("Validation passed.")

    def load(self) -> None:
        from plinth.db.connection import get_connection

        for name, layer in _LAYERS.items():
            s3_key = layer["s3_key"]
            tile_id = layer["tile_id"]

            if _tile_exists_in_db(s3_key):
                self._log(f"  {name}: already in raster_tiles ({s3_key}) — skipping.")
                continue

            global_tif = self.staging_dir / f"{name}_global.tif"
            conus_tif = self.staging_dir / f"{name}_conus.tif"
            cog = self.staging_dir / f"{name}_conus_cog.tif"

            # Step 1: Clip global → CONUS
            self._log(f"  Clipping {name} to CONUS bounding box…")
            result = subprocess.run(
                [
                    "gdal_translate",
                    "-of", "GTiff",
                    "-projwin",
                    str(_CONUS_WEST),
                    str(_CONUS_NORTH),
                    str(_CONUS_EAST),
                    str(_CONUS_SOUTH),
                    str(global_tif),
                    str(conus_tif),
                ],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"gdal_translate clip failed for {name}.\nstderr: {result.stderr}"
                )
            self._log(f"  CONUS clip: {conus_tif.stat().st_size / 1e6:.1f} MB")

            # Step 2: Convert CONUS clip → COG
            self._log(f"  Converting {name} CONUS clip to COG…")
            result = subprocess.run(
                [
                    "gdal_translate",
                    "-of", "COG",
                    "-co", "COMPRESS=DEFLATE",
                    "-co", "PREDICTOR=2",
                    "-co", "OVERVIEWS=AUTO",
                    "-co", "RESAMPLING=AVERAGE",
                    str(conus_tif),
                    str(cog),
                ],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"gdal_translate COG failed for {name}.\nstderr: {result.stderr}"
                )
            conus_tif.unlink()  # free disk space
            self._log(f"  COG written: {cog.name} ({cog.stat().st_size / 1e6:.1f} MB)")

            # Step 3: Upload to MinIO
            self._log(f"  Uploading to MinIO: {s3_key}")
            upload_cog(cog, s3_key)
            self._log("  Upload complete.")

            # Step 4: Register tile
            with rasterio.open(cog) as ds:
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
                                ST_MakeEnvelope(%(minx)s,%(miny)s,%(maxx)s,%(maxy)s, 4326),
                                %(res_m)s, %(tile_id)s, %(version)s)
                        ON CONFLICT (s3_key) DO UPDATE SET
                            bounds           = EXCLUDED.bounds,
                            resolution_m     = EXCLUDED.resolution_m,
                            dataset_version  = EXCLUDED.dataset_version
                        """,
                        {
                            "dataset":  _DATASET,
                            "s3_key":   s3_key,
                            "minx":     bounds.left,
                            "miny":     bounds.bottom,
                            "maxx":     bounds.right,
                            "maxy":     bounds.top,
                            "res_m":    round(res_m, 1),
                            "tile_id":  tile_id,
                            "version":  _VERSION,
                        },
                    )
                conn.commit()
            self._log(f"  {name}: tile registered (res ~{res_m:.0f} m).")

    def register(self) -> None:
        self._upsert_registry(
            version=_VERSION,
            coverage_region="national",
            notes=(
                "SoilGrids 250m v2017 depth-to-bedrock for CONUS. "
                "BDRICM: absolute depth to bedrock (cm). "
                "BDRLOG: probability of bedrock within 200 cm (0–1 fraction). "
                "Source: ISRIC files.isric.org/soilgrids/former/2017-03-10/data/. "
                "Resolution: ~250 m. "
                "Citation: Hengl et al. (2017) PLOS ONE 12(2):e0169748."
            ),
        )


def _tile_exists_in_db(s3_key: str) -> bool:
    from plinth.db.connection import get_connection

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM raster_tiles WHERE s3_key = %s", (s3_key,))
            return cur.fetchone() is not None
