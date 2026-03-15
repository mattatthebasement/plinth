"""EPA Community Water System Service Area Boundaries ingestor.

Downloads the EPA CWS Service Area Boundaries dataset from the EPA ArcGIS
FeatureServer via paginated JSON queries, writes a merged GeoJSON file, then
loads into water_system_boundaries via ogr2ogr.

~44,000 polygon boundaries representing community water system service areas.
Provides ~99% coverage of US consumers served by CWS. Boundaries are either
state/utility-supplied or EPA-modeled for national completeness.

Enables ST_Contains queries to identify the serving water utility for any site.
Join on pwsid to sdwis_water_systems for system metadata (name, source type, etc.)

Source:    EPA Office of Water / ArcGIS
FeatureServer: https://services.arcgis.com/cJ9YHowT8TU7DUyn/ArcGIS/rest/
               services/Water_System_Boundaries/FeatureServer/0
Refresh:   Annual (EPA updates approximately annually)
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Optional

from plinth.ingest.base import BaseIngestor
from plinth.ingest.hifld_electric_territories import _paginate_feature_server

_FEATURE_SERVER = (
    "https://services.arcgis.com/cJ9YHowT8TU7DUyn/ArcGIS/rest/services"
    "/Water_System_Boundaries/FeatureServer/0"
)
_PAGE_SIZE = 500
_OUT_FIELDS = "PWSID,PWS_Name,Original_Data_Provider,Service_Area_Type"


class EpaWaterBoundariesIngestor(BaseIngestor):
    """Download EPA CWS boundary polygons and load into PostGIS."""

    source_name = "epa-water-boundaries"
    update_frequency = "annual"

    @property
    def _geojson_path(self) -> Path:
        return self.staging_dir / "water_system_boundaries.geojson"

    def download(self, region: Optional[str] = None) -> None:
        """Paginate EPA FeatureServer and write merged GeoJSON to staging."""
        if self._geojson_path.exists():
            import time
            age_days = (time.time() - self._geojson_path.stat().st_mtime) / 86400
            if age_days < 30:
                self._log(f"GeoJSON cache is fresh ({age_days:.0f} days old) — skipping.")
                return

        self._log("Paginating EPA CWS Service Area Boundaries FeatureServer (~44k features)…")
        features = _paginate_feature_server(
            _FEATURE_SERVER, _OUT_FIELDS, _PAGE_SIZE, self._log
        )
        self._log(f"  Fetched {len(features):,} water system boundary features.")

        geojson = {"type": "FeatureCollection", "features": features}
        self._geojson_path.write_text(json.dumps(geojson))
        self._log(f"  Wrote {self._geojson_path.name}")

    def validate(self) -> None:
        if not self._geojson_path.exists():
            raise ValueError(f"GeoJSON not found: {self._geojson_path}")
        data = json.loads(self._geojson_path.read_text())
        count = len(data.get("features", []))
        if count < 10_000:
            raise ValueError(f"Only {count} features — expected ~44,000. Re-download needed.")
        self._log(f"Validation passed — {count:,} water system boundary features.")

    def load(self) -> None:
        """Load GeoJSON into water_system_boundaries via ogr2ogr."""
        self._log("Loading into water_system_boundaries via ogr2ogr…")
        s = self.settings
        pg_dsn = (
            f"PG:host={s.postgres_host} port={s.postgres_port} "
            f"dbname={s.postgres_db} user={s.postgres_user} "
            f"password={s.postgres_password}"
        )

        sql = (
            "SELECT "
            "  PWSID AS pwsid, "
            "  PWS_Name AS pws_name, "
            "  Original_Data_Provider AS boundary_source, "
            "  Service_Area_Type AS service_area_type "
            f"FROM \"{self._geojson_path.stem}\""
        )

        cmd = [
            "ogr2ogr",
            "-f", "PostgreSQL", pg_dsn,
            "-overwrite",
            "-nln", "water_system_boundaries",
            "-t_srs", "EPSG:4326",
            "-nlt", "PROMOTE_TO_MULTI",
            "-lco", "GEOMETRY_NAME=geom",
            "-sql", sql,
            str(self._geojson_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"ogr2ogr failed loading water system boundaries.\nstderr: {result.stderr}"
            )
        self._log("  Loaded water_system_boundaries.")

    def register(self) -> None:
        self._upsert_registry(
            version="2026-02",
            coverage_region="national",
            notes=(
                "EPA Community Water System Service Area Boundaries. "
                "~44k polygons, ~99% consumer coverage. "
                "Mix of state/utility-supplied and EPA-modeled boundaries."
            ),
        )
