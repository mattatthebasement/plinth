"""HIFLD Electric Power Substations ingestor.

Downloads the Electric Power Substations dataset from NOAA's Marine Cadastre,
which redistributes the HIFLD/ORNL national substations data as a file
geodatabase. Loads ~10,900 major transmission substations (69 kV+) into
PostGIS for nearest-substation spatial queries.

Source:    NOAA Office for Coastal Management / Marine Cadastre (HIFLD data)
Download:  https://marinecadastre.gov/downloads/data/mc/ElectricPowerSubstation.zip
Refresh:   Annual (NOAA typically refreshes annually)
"""
from __future__ import annotations

import subprocess
import zipfile
from pathlib import Path
from typing import Optional

from plinth.ingest.base import BaseIngestor

_DOWNLOAD_URL = (
    "https://marinecadastre.gov/downloads/data/mc/ElectricPowerSubstation.zip"
)


class HifldSubstationsIngestor(BaseIngestor):
    """Download NOAA/HIFLD electric power substations and load into PostGIS."""

    source_name = "hifld-substations"
    update_frequency = "annual"

    @property
    def _zip_path(self) -> Path:
        return self.staging_dir / "ElectricPowerSubstation.zip"

    @property
    def _gdb_path(self) -> Path:
        return self.staging_dir / "Substations.gdb"

    def download(self, region: Optional[str] = None) -> None:
        self._log("Downloading NOAA Electric Power Substations FileGDB…")
        self._download_if_changed(_DOWNLOAD_URL, self._zip_path)

        if not self._gdb_path.exists():
            self._log("  Extracting FileGDB from ZIP…")
            with zipfile.ZipFile(self._zip_path) as zf:
                zf.extractall(self.staging_dir)
            self._log(f"  Extracted to {self._gdb_path}")

    def validate(self) -> None:
        if not self._gdb_path.exists():
            raise ValueError(f"FileGDB not found: {self._gdb_path}")
        result = subprocess.run(
            ["ogrinfo", "-al", "-so", str(self._gdb_path)],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            raise RuntimeError(f"ogrinfo failed: {result.stderr}")
        # Extract feature count from ogrinfo output
        count = 0
        for line in result.stdout.splitlines():
            if "Feature Count:" in line:
                count = int(line.split(":")[1].strip())
                break
        if count < 5_000:
            raise ValueError(f"Only {count} features — expected ~10,000+.")
        self._log(f"Validation passed — {count:,} substation features.")

    def load(self) -> None:
        """Load FileGDB into electric_substations via ogr2ogr."""
        self._log("Loading into electric_substations via ogr2ogr…")
        s = self.settings
        pg_dsn = (
            f"PG:host={s.postgres_host} port={s.postgres_port} "
            f"dbname={s.postgres_db} user={s.postgres_user} "
            f"password={s.postgres_password}"
        )

        sql = (
            "SELECT "
            "  NAME AS substation_name, "
            "  MAX_VOLT AS max_voltage_kv, "
            "  MIN_VOLT AS min_voltage_kv, "
            "  LINES AS line_count, "
            "  STATE AS state, "
            "  CITY AS city, "
            "  ZIPCODE AS zip "
            "FROM \"Substations\""
        )

        cmd = [
            "ogr2ogr",
            "-f", "PostgreSQL", pg_dsn,
            "-overwrite",
            "-nln", "electric_substations",
            "-t_srs", "EPSG:4326",
            "-nlt", "POINT",
            "-lco", "GEOMETRY_NAME=geom",
            "-sql", sql,
            str(self._gdb_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"ogr2ogr failed loading substations.\nstderr: {result.stderr}"
            )
        self._log("  Loaded electric_substations.")

    def register(self) -> None:
        self._upsert_registry(
            version="2018",
            coverage_region="national",
            notes=(
                "Electric Power Substations (CONUS, 69 kV+). Source: NOAA Marine Cadastre "
                "redistribution of HIFLD/ORNL data. ~10,900 major transmission substations."
            ),
        )
