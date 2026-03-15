"""USGS Principal Aquifers ingestor.

Downloads the USGS Principal Aquifers of the United States shapefile from the
USGS data server, loads into usgs_principal_aquifers via ogr2ogr.

~70 polygon features representing the major aquifer systems underlying the
conterminous US at 1:2,500,000 national scale. Enables ST_Intersects queries
to identify the principal aquifer(s) underlying any CONUS site.

Note on scale: This is a 1:2.5M national dataset that shows general geological
aquifer formations. A site "within" an aquifer polygon is in the general
geological formation; local variations (well yields, water quality, depth) vary
considerably within each formation.

Source:  USGS Ground Water Atlas of the United States
         https://water.usgs.gov/GIS/dsdl/aquifers_us.zip
Refresh: Decadal (USGS 2025 Hydrogeologic Regions update available as future upgrade)
"""
from __future__ import annotations

import subprocess
import zipfile
from pathlib import Path
from typing import Optional

from plinth.ingest.base import BaseIngestor

_DOWNLOAD_URL = "https://water.usgs.gov/GIS/dsdl/aquifers_us.zip"
_ZIP_FILE = "aquifers_us.zip"
_SHAPEFILE_NAME = "aquifers_us.shp"


class UsgsAquifersIngestor(BaseIngestor):
    """Download USGS principal aquifer polygons and load into PostGIS."""

    source_name = "usgs-aquifers"
    update_frequency = "decadal"

    @property
    def _zip_path(self) -> Path:
        return self.staging_dir / _ZIP_FILE

    @property
    def _shp_path(self) -> Path:
        return self.staging_dir / _SHAPEFILE_NAME

    def download(self, region: Optional[str] = None) -> None:
        """Download USGS principal aquifers shapefile ZIP."""
        self._log("Checking USGS principal aquifers shapefile…")
        fetched = self._download_if_changed(_DOWNLOAD_URL, self._zip_path)
        if not fetched:
            self._log("ZIP is up-to-date (ETag matched).")
            return
        # Extract shapefile components
        self._log("Extracting shapefile…")
        with zipfile.ZipFile(self._zip_path) as zf:
            zf.extractall(self.staging_dir)

    def validate(self) -> None:
        """Verify the shapefile is present and non-trivial."""
        if not self._zip_path.exists():
            raise ValueError(f"ZIP not found: {self._zip_path}")
        if self._zip_path.stat().st_size < 100_000:
            raise ValueError(f"ZIP suspiciously small: {self._zip_path.stat().st_size} bytes")

        # Find the .shp file (may be in a subdirectory)
        shp_files = list(self.staging_dir.rglob("*.shp"))
        if not shp_files:
            raise ValueError(f"No .shp file found under {self.staging_dir}")
        self._log(f"Validation passed — shapefile found: {shp_files[0].name}")

    def load(self) -> None:
        """Load aquifer shapefile into usgs_principal_aquifers via ogr2ogr."""
        # Find shapefile
        shp_files = list(self.staging_dir.rglob("*.shp"))
        if not shp_files:
            raise RuntimeError("No .shp file found — run download() first")
        shp_path = shp_files[0]

        self._log(f"Loading {shp_path.name} into usgs_principal_aquifers via ogr2ogr…")
        s = self.settings
        pg_dsn = (
            f"PG:host={s.postgres_host} port={s.postgres_port} "
            f"dbname={s.postgres_db} user={s.postgres_user} "
            f"password={s.postgres_password}"
        )

        # Actual shapefile fields: AQ_NAME, AQ_CODE, ROCK_TYPE (int), ROCK_NAME
        # ROCK_NAME is the descriptive formation type (maps to aquifer_type column)
        # ROCK_TYPE is an integer code; ogr2ogr coerces int→text on load
        sql = (
            "SELECT "
            "  AQ_NAME   AS aq_name, "
            "  AQ_CODE   AS aq_code, "
            "  ROCK_TYPE AS rock_type, "
            "  ROCK_NAME AS aquifer_type "
            f"FROM \"{shp_path.stem}\""
        )

        cmd = [
            "ogr2ogr",
            "-f", "PostgreSQL", pg_dsn,
            "-overwrite",
            "-nln", "usgs_principal_aquifers",
            "-t_srs", "EPSG:4326",
            "-nlt", "PROMOTE_TO_MULTI",
            "-lco", "GEOMETRY_NAME=geom",
            "-sql", sql,
            str(shp_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"ogr2ogr failed loading aquifers.\nstderr: {result.stderr}"
            )
        self._log("  Loaded usgs_principal_aquifers.")

    def register(self) -> None:
        self._upsert_registry(
            version="2003",
            coverage_region="national",
            notes=(
                "USGS Ground Water Atlas principal aquifer polygons. "
                "~70 formations at 1:2,500,000 national scale. "
                "Future upgrade: USGS 2025 Hydrogeologic Regions dataset."
            ),
        )
