"""USGS Hydrogeologic Framework ingestor (2025).

Downloads two national datasets from USGS ScienceBase and loads into PostGIS:

  usgs_hydrogeologic_provinces  — 8 broad hydrogeologic provinces covering all CONUS.
      Source: ScienceBase item 6807cab6d4be020d8168d576 (published 2025-07-28)

  usgs_hydrogeologic_regions    — 126 named hydrogeologic regions covering all CONUS.
      57 Principal Aquifer (PA) polygons + 69 Secondary Hydrogeologic Regions (SHR)
      that fill every gap.  Together they tile CONUS without gaps.
      Source: ScienceBase item 6863356fd4be025653d31f4d (published 2025-12-19)

Both datasets are in NAD83(2011) / Conus Albers projection; ogr2ogr reprojects to
EPSG:4326 on load.

Refresh: Decadal (these are stable framework datasets).
"""
from __future__ import annotations

import subprocess
import zipfile
from pathlib import Path
from typing import Optional

from plinth.ingest.base import BaseIngestor

# ScienceBase direct download URLs (stable disk-hash URLs)
_PROVINCES_URL = (
    "https://www.sciencebase.gov/catalog/file/get/"
    "6807cab6d4be020d8168d576?f=__disk__ab%2F2d%2F9f%2F"
    "ab2d9f0696ceeedbaff3d9726079b58664af2cd4"
)
_REGIONS_URL = (
    "https://www.sciencebase.gov/catalog/file/get/"
    "6863356fd4be025653d31f4d?f=__disk__3c%2F3e%2F93%2F"
    "3c3e93e13d05bb5e80284138ea2aced23a56e40d"
)

_PROVINCES_ZIP = "HG_Provinces.zip"
_REGIONS_ZIP = "HydrogeologicRegions.zip"
_PROVINCES_SHP = "HG_Provinces.shp"
_REGIONS_SHP = "HydrogeologicRegions.shp"


class UsgsHydrogeologicFrameworkIngestor(BaseIngestor):
    """Download USGS 2025 hydrogeologic provinces and regions, load into PostGIS."""

    source_name = "usgs-hydrogeologic-framework"
    update_frequency = "decadal"

    def download(self, region: Optional[str] = None) -> None:
        self._log("Downloading hydrogeologic provinces shapefile…")
        self._download_if_changed(_PROVINCES_URL, self.staging_dir / _PROVINCES_ZIP)

        self._log("Downloading hydrogeologic regions shapefile…")
        self._download_if_changed(_REGIONS_URL, self.staging_dir / _REGIONS_ZIP)

    def validate(self) -> None:
        for zip_name in (_PROVINCES_ZIP, _REGIONS_ZIP):
            p = self.staging_dir / zip_name
            if not p.exists():
                raise ValueError(f"ZIP not found: {p}")
            if p.stat().st_size < 100_000:
                raise ValueError(f"ZIP suspiciously small ({p.stat().st_size} bytes): {p}")
            with zipfile.ZipFile(p) as zf:
                names = zf.namelist()
                shp_files = [n for n in names if n.endswith(".shp")]
                if not shp_files:
                    raise ValueError(f"No .shp file found in {zip_name}: {names}")
        self._log("Validation passed.")

    def load(self) -> None:
        self._load_provinces()
        self._load_regions()

    def _load_provinces(self) -> None:
        self._log("Loading hydrogeologic provinces…")
        shp_path = self._extract_shp(self.staging_dir / _PROVINCES_ZIP, _PROVINCES_SHP)
        s = self.settings
        pg_dsn = (
            f"PG:host={s.postgres_host} port={s.postgres_port} "
            f"dbname={s.postgres_db} user={s.postgres_user} "
            f"password={s.postgres_password}"
        )
        sql = f"SELECT HGProvName AS prov_name FROM \"{shp_path.stem}\""
        cmd = [
            "ogr2ogr",
            "-f", "PostgreSQL", pg_dsn,
            "-overwrite",
            "-nln", "usgs_hydrogeologic_provinces",
            "-t_srs", "EPSG:4326",
            "-nlt", "PROMOTE_TO_MULTI",
            "-lco", "GEOMETRY_NAME=geom",
            "-lco", "FID=id",
            "-sql", sql,
            str(shp_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"ogr2ogr failed loading provinces.\nstderr: {result.stderr}"
            )
        self._log("  Hydrogeologic provinces loaded.")

    def _load_regions(self) -> None:
        self._log("Loading hydrogeologic regions…")
        shp_path = self._extract_shp(self.staging_dir / _REGIONS_ZIP, _REGIONS_SHP)
        s = self.settings
        pg_dsn = (
            f"PG:host={s.postgres_host} port={s.postgres_port} "
            f"dbname={s.postgres_db} user={s.postgres_user} "
            f"password={s.postgres_password}"
        )
        sql = (
            f"SELECT HR_Name AS reg_name, HR_Code AS reg_code, "
            f"HR_Type AS reg_type, HR_Litholo AS lithology "
            f"FROM \"{shp_path.stem}\""
        )
        cmd = [
            "ogr2ogr",
            "-f", "PostgreSQL", pg_dsn,
            "-overwrite",
            "-nln", "usgs_hydrogeologic_regions",
            "-t_srs", "EPSG:4326",
            "-nlt", "PROMOTE_TO_MULTI",
            "-lco", "GEOMETRY_NAME=geom",
            "-lco", "FID=id",
            "-sql", sql,
            str(shp_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"ogr2ogr failed loading regions.\nstderr: {result.stderr}"
            )
        self._log("  Hydrogeologic regions loaded.")

    def _extract_shp(self, zip_path: Path, shp_name: str) -> Path:
        """Extract ZIP into a subdirectory and return the .shp path."""
        extract_dir = zip_path.parent / zip_path.stem
        extract_dir.mkdir(exist_ok=True)
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(extract_dir)
        shp = extract_dir / shp_name
        if not shp.exists():
            # Try to find it recursively in case of nested dirs
            matches = list(extract_dir.rglob(shp_name))
            if not matches:
                raise FileNotFoundError(f"{shp_name} not found in {extract_dir}")
            shp = matches[0]
        return shp

    def register(self) -> None:
        self._upsert_registry(
            version="2025",
            coverage_region="national",
            notes=(
                "USGS 2025 hydrogeologic framework. "
                "Provinces (8): ScienceBase 6807cab6d4be020d8168d576. "
                "Regions (126, PA+SHR): ScienceBase 6863356fd4be025653d31f4d. "
                "Full CONUS coverage — PA regions are principal aquifers; "
                "SHR regions fill unmapped gaps."
            ),
        )
