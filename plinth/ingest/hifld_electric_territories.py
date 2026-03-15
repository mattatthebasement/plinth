"""HIFLD Electric Retail Service Territories ingestor.

Downloads the HIFLD Electric Retail Service Territories dataset from the
HIFLD ArcGIS FeatureServer via paginated JSON queries, writes a merged
GeoJSON file, then loads into electric_service_territories via ogr2ogr.

~3,200 utility service territory polygons covering the entire US. Enables
ST_Contains queries to identify the serving electric utility for any site.

Source:    HIFLD / Oak Ridge National Laboratory / DOE/DHS
FeatureServer: https://services3.arcgis.com/OYP7N6mAJJCyH6hd/arcgis/rest/
               services/Electric_Retail_Service_Territories_HIFLD/FeatureServer/0
Refresh:   Annual
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Optional

import httpx

from plinth.ingest.base import BaseIngestor

_FEATURE_SERVER = (
    "https://services3.arcgis.com/OYP7N6mAJJCyH6hd/arcgis/rest/services"
    "/Electric_Retail_Service_Territories_HIFLD/FeatureServer/0"
)
_PAGE_SIZE = 500
_OUT_FIELDS = "ID,NAME,ADDRESS,CITY,STATE,ZIP,TELEPHONE,TYPE,NAICS_CODE,SOURCE,SOURCEDATE"


class HifldElectricTerritoriesIngestor(BaseIngestor):
    """Download HIFLD service territory polygons and load into PostGIS."""

    source_name = "hifld-electric-territories"
    update_frequency = "annual"

    @property
    def _geojson_path(self) -> Path:
        return self.staging_dir / "electric_service_territories.geojson"

    def download(self, region: Optional[str] = None) -> None:
        """Paginate HIFLD FeatureServer and write merged GeoJSON to staging."""
        if self._geojson_path.exists():
            import time
            age_days = (time.time() - self._geojson_path.stat().st_mtime) / 86400
            if age_days < 30:
                self._log(f"GeoJSON cache is fresh ({age_days:.0f} days old) — skipping download.")
                return

        self._log("Paginating HIFLD Electric Retail Service Territories FeatureServer…")
        features = _paginate_feature_server(
            _FEATURE_SERVER, _OUT_FIELDS, _PAGE_SIZE, self._log
        )
        self._log(f"  Fetched {len(features):,} territory features.")

        geojson = {"type": "FeatureCollection", "features": features}
        self._geojson_path.write_text(json.dumps(geojson))
        self._log(f"  Wrote {self._geojson_path.name}")

    def validate(self) -> None:
        if not self._geojson_path.exists():
            raise ValueError(f"GeoJSON not found: {self._geojson_path}")
        data = json.loads(self._geojson_path.read_text())
        count = len(data.get("features", []))
        if count < 1000:
            raise ValueError(f"Only {count} features — expected ~3,200. Re-download needed.")
        self._log(f"Validation passed — {count:,} territory features.")

    def load(self) -> None:
        """Load GeoJSON into electric_service_territories via ogr2ogr."""
        self._log("Loading into electric_service_territories via ogr2ogr…")
        s = self.settings
        pg_dsn = (
            f"PG:host={s.postgres_host} port={s.postgres_port} "
            f"dbname={s.postgres_db} user={s.postgres_user} "
            f"password={s.postgres_password}"
        )

        # Map source fields → target columns using -sql
        sql = (
            "SELECT "
            "  ID AS eia_id, "
            "  NAME AS utility_name, "
            "  STATE AS state, "
            "  NAICS_CODE AS naics_code, "
            "  TYPE AS entity_type, "
            "  ADDRESS AS address, "
            "  CITY AS city, "
            "  ZIP AS zip, "
            "  TELEPHONE AS phone, "
            "  SOURCEDATE AS source_date "
            f"FROM \"{self._geojson_path.stem}\""
        )

        cmd = [
            "ogr2ogr",
            "-f", "PostgreSQL", pg_dsn,
            "-overwrite",
            "-nln", "electric_service_territories",
            "-t_srs", "EPSG:4326",
            "-nlt", "PROMOTE_TO_MULTI",
            "-lco", "GEOMETRY_NAME=geom",
            "-sql", sql,
            str(self._geojson_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"ogr2ogr failed loading service territories.\nstderr: {result.stderr}"
            )
        self._log("  Loaded electric_service_territories.")

    def register(self) -> None:
        self._upsert_registry(
            version="2025",
            coverage_region="national",
            notes="HIFLD Electric Retail Service Territories. ~3,200 utility polygon boundaries.",
        )


def _paginate_feature_server(
    base_url: str,
    out_fields: str,
    page_size: int,
    log_fn,
) -> list[dict]:
    """Paginate an ArcGIS FeatureServer /query endpoint and return all features."""
    features: list[dict] = []
    offset = 0

    while True:
        params = {
            "where": "1=1",
            "outFields": out_fields,
            "outSR": "4326",
            "f": "geojson",
            "resultOffset": offset,
            "resultRecordCount": page_size,
            "returnGeometry": "true",
        }
        resp = httpx.get(f"{base_url}/query", params=params, timeout=120)
        resp.raise_for_status()
        data = resp.json()

        if "error" in data:
            raise RuntimeError(f"FeatureServer error: {data['error']}")

        batch = data.get("features", [])
        features.extend(batch)

        if len(batch) < page_size:
            break  # last page
        offset += len(batch)
        log_fn(f"  … fetched {len(features):,} features so far")

    return features
