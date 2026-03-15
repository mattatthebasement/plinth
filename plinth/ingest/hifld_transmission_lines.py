"""HIFLD Electric Power Transmission Lines ingestor.

Downloads the HIFLD Electric Power Transmission Lines dataset from the HIFLD
ArcGIS FeatureServer via paginated JSON queries, writes a merged GeoJSON file,
then loads into electric_transmission_lines via ogr2ogr.

~70,000+ line segments representing US high-voltage transmission (69 kV+).
Enables ST_DWithin queries for nearest transmission line and voltage class.

Source:    HIFLD / Oak Ridge National Laboratory / DOE/DHS
FeatureServer: https://services1.arcgis.com/Hp6G80Pky0om7QvQ/arcgis/rest/
               services/Electric_Power_Transmission_Lines/FeatureServer/0
Refresh:   Annual
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Optional

from plinth.ingest.base import BaseIngestor
from plinth.ingest.hifld_electric_territories import _paginate_feature_server

_FEATURE_SERVER = (
    "https://services1.arcgis.com/Hp6G80Pky0om7QvQ/arcgis/rest/services"
    "/Electric_Power_Transmission_Lines/FeatureServer/0"
)
_PAGE_SIZE = 1000
_OUT_FIELDS = "ID,TYPE,OWNER,VOLTAGE,VOLT_CLASS,STATUS,INFERRED,SUB_1,SUB_2,SOURCEDATE"


class HifldTransmissionLinesIngestor(BaseIngestor):
    """Download HIFLD transmission lines and load into PostGIS."""

    source_name = "hifld-transmission-lines"
    update_frequency = "annual"

    @property
    def _geojson_path(self) -> Path:
        return self.staging_dir / "transmission_lines.geojson"

    def download(self, region: Optional[str] = None) -> None:
        """Paginate HIFLD FeatureServer and write merged GeoJSON to staging."""
        if self._geojson_path.exists():
            import time
            age_days = (time.time() - self._geojson_path.stat().st_size) / 86400
            # Cache is large; refresh only if > 30 days old
            mtime_age = (time.time() - self._geojson_path.stat().st_mtime) / 86400
            if mtime_age < 30:
                self._log(f"GeoJSON cache is fresh ({mtime_age:.0f} days old) — skipping.")
                return

        self._log("Paginating HIFLD Transmission Lines FeatureServer (~70k features)…")
        features = _paginate_feature_server(
            _FEATURE_SERVER, _OUT_FIELDS, _PAGE_SIZE, self._log
        )
        self._log(f"  Fetched {len(features):,} transmission line features.")

        geojson = {"type": "FeatureCollection", "features": features}
        self._geojson_path.write_text(json.dumps(geojson))
        self._log(f"  Wrote {self._geojson_path.name} ({self._geojson_path.stat().st_size / 1e6:.1f} MB)")

    def validate(self) -> None:
        if not self._geojson_path.exists():
            raise ValueError(f"GeoJSON not found: {self._geojson_path}")
        data = json.loads(self._geojson_path.read_text())
        count = len(data.get("features", []))
        if count < 10_000:
            raise ValueError(f"Only {count} features — expected ~70,000. Re-download needed.")
        self._log(f"Validation passed — {count:,} transmission line features.")

    def load(self) -> None:
        """Load GeoJSON into electric_transmission_lines via ogr2ogr."""
        self._log("Loading into electric_transmission_lines via ogr2ogr…")
        s = self.settings
        pg_dsn = (
            f"PG:host={s.postgres_host} port={s.postgres_port} "
            f"dbname={s.postgres_db} user={s.postgres_user} "
            f"password={s.postgres_password}"
        )

        sql = (
            "SELECT "
            "  OWNER AS owner, "
            "  VOLTAGE AS voltage_kv, "
            "  VOLT_CLASS AS voltage_class, "
            "  STATUS AS status, "
            "  SOURCEDATE AS source_date "
            f"FROM \"{self._geojson_path.stem}\""
        )

        cmd = [
            "ogr2ogr",
            "-f", "PostgreSQL", pg_dsn,
            "-overwrite",
            "-nln", "electric_transmission_lines",
            "-t_srs", "EPSG:4326",
            "-nlt", "PROMOTE_TO_MULTI",
            "-lco", "GEOMETRY_NAME=geom",
            "-sql", sql,
            str(self._geojson_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"ogr2ogr failed loading transmission lines.\nstderr: {result.stderr}"
            )
        self._log("  Loaded electric_transmission_lines.")

    def register(self) -> None:
        self._upsert_registry(
            version="2025",
            coverage_region="national",
            notes="HIFLD Electric Power Transmission Lines. ~70k segments, 69kV+.",
        )
