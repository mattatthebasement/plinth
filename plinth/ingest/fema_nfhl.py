"""FEMA National Flood Hazard Layer (NFHL) ingestor.

Queries the FEMA NFHL ArcGIS REST API (layer 28 — Flood Hazard Zones) directly
as GeoJSON per county, then loads into PostGIS.  Also computes *unmapped areas*
(county boundary minus flood zones) so sites with no FEMA data are never
silently classified as Zone X.
"""

import json
from pathlib import Path
from typing import Optional

from plinth.ingest.base import BaseIngestor

NE_OKLAHOMA_COUNTIES: dict[str, str] = {
    "40021": "Cherokee",
    "40035": "Craig",
    "40041": "Delaware",
    "40097": "Mayes",
    "40115": "Ottawa",
    "40131": "Rogers",
    "40143": "Tulsa",
    "40145": "Wagoner",
}

# Correct ArcGIS REST endpoint — layer 28 is Flood Hazard Zones
_NFHL_QUERY = (
    "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28/query"
)
_PAGE_SIZE = 2000  # service maxRecordCount


class FemaNfhlIngestor(BaseIngestor):
    """Query FEMA NFHL REST API and load flood-zone polygons.

    For each county:
    1. Page through the NFHL REST API (GeoJSON) filtering by DFIRM_ID prefix.
    2. Save accumulated GeoJSON to staging directory.
    3. Load via ogr2ogr into ``fema_flood_zones``.
    4. Compute the unmapped area (county boundary minus flood zones) and store
       in ``fema_unmapped_areas``.
    """

    source_name = "fema-nfhl"
    update_frequency = "monthly"

    # Counties that failed API fetch — skipped in validate/load
    _skipped: set[str]

    def download(self, region: Optional[str] = None) -> None:
        """Fetch flood zone GeoJSON for all NE-Oklahoma counties."""
        import datetime
        import httpx

        self._skipped = set()

        for fips, name in NE_OKLAHOMA_COUNTIES.items():
            dest = self.staging_dir / f"{fips}.geojson"
            meta = self.staging_dir / f"{fips}.meta.json"

            # Skip if already fetched today
            if dest.exists() and meta.exists():
                saved = json.loads(meta.read_text()).get("fetched_date", "")
                if saved == datetime.date.today().isoformat():
                    self._log(f"  {name} ({fips}): up to date (fetched today)")
                    continue

            self._log(f"  Fetching flood zones for {name} ({fips})…")
            try:
                features = self._fetch_county_features(fips, httpx.Client(timeout=60, follow_redirects=True))
            except Exception as exc:
                self._log(
                    f"  Warning: FEMA API failed for {name} ({fips}): {exc}. "
                    "Skipping — re-run later to retry."
                )
                self._skipped.add(fips)
                continue

            fc = {"type": "FeatureCollection", "features": features}
            self.staging_dir.mkdir(parents=True, exist_ok=True)
            dest.write_text(json.dumps(fc))
            meta.write_text(json.dumps({
                "fetched_date": datetime.date.today().isoformat(),
                "count": len(features),
            }))
            self._log(f"    {len(features)} features saved.")

    def _fetch_county_features(self, fips: str, client) -> list:
        """Page through the NFHL REST API for one county, returning all features."""
        features: list = []
        offset = 0
        while True:
            params = {
                "where": f"DFIRM_ID LIKE '{fips}%'",
                "outFields": "DFIRM_ID,FLD_ZONE,ZONE_SUBTY,SFHA_TF,BFE_REVERT,STATIC_BFE",
                "outSR": "4326",
                "returnGeometry": "true",
                "resultOffset": str(offset),
                "resultRecordCount": str(_PAGE_SIZE),
                "f": "geojson",
            }
            resp = client.get(_NFHL_QUERY, params=params)
            resp.raise_for_status()
            page = resp.json()
            batch = page.get("features", [])
            features.extend(batch)
            if len(batch) < _PAGE_SIZE:
                break
            offset += _PAGE_SIZE
        return features

    def validate(self) -> None:
        """Check that downloaded county GeoJSON files are present and non-empty."""
        skipped = getattr(self, "_skipped", set())
        for fips, name in NE_OKLAHOMA_COUNTIES.items():
            if fips in skipped:
                continue
            dest = self.staging_dir / f"{fips}.geojson"
            if not dest.exists():
                raise ValueError(f"GeoJSON not found for {name} ({fips}): {dest}")
            if dest.stat().st_size == 0:
                raise ValueError(f"Empty GeoJSON for {name} ({fips}): {dest}")

    def load(self) -> None:
        """Load flood zones and compute unmapped areas for each county."""
        skipped = getattr(self, "_skipped", set())
        for fips, name in NE_OKLAHOMA_COUNTIES.items():
            if fips in skipped:
                self._log(f"Skipping {name} ({fips}) — API fetch failed during download.")
                continue
            geojson_path = self.staging_dir / f"{fips}.geojson"
            if not geojson_path.exists():
                self._log(f"Skipping {name} ({fips}) — GeoJSON not downloaded.")
                continue

            self._log(f"Loading flood zones for {name} ({fips})…")
            self._load_flood_zones(fips, str(geojson_path))
            self._log(f"Computing unmapped areas for {name} ({fips})…")
            self._compute_unmapped(fips)

    def _load_flood_zones(self, county_fips: str, geojson_path: str) -> None:
        staging = "_staging_flood_zones"
        # For GeoJSON, ogr2ogr uses the filename stem as the layer name.
        layer_name = Path(geojson_path).stem
        try:
            self._ogr2ogr_to_staging_table(geojson_path, layer_name, staging)
        except RuntimeError as exc:
            self._log(f"  ogr2ogr error for {county_fips}: {exc}")
            return

        from plinth.db.connection import get_connection

        with get_connection() as conn:
            with conn.cursor() as cur:
                # Idempotent: delete existing rows for this county then re-insert.
                cur.execute(
                    "DELETE FROM fema_flood_zones WHERE county_fips = %s",
                    (county_fips,),
                )
                cur.execute(
                    f"""
                    INSERT INTO fema_flood_zones
                        (dfirm_id, fld_zone, zone_subty, sfha_tf,
                         bfe_revert, static_bfe, county_fips, source_date, geom)
                    SELECT
                        dfirm_id,
                        fld_zone,
                        zone_subty,
                        sfha_tf,
                        NULLIF(bfe_revert::text, '')::numeric,
                        NULLIF(static_bfe::text, '')::numeric,
                        %s,
                        now()::date,
                        geom
                    FROM {staging}
                    """,
                    (county_fips,),
                )
                rows = cur.rowcount
                cur.execute(f"DROP TABLE IF EXISTS {staging}")
            conn.commit()
        self._log(f"  Flood zone rows inserted: {rows}")

    def _compute_unmapped(self, county_fips: str) -> None:
        """Compute county boundary minus flood zones → fema_unmapped_areas.

        Skips (with a warning) if census_block_groups has no data for the county.
        """
        from plinth.db.connection import get_connection

        with get_connection() as conn:
            with conn.cursor() as cur:
                # Check that we have census geometry for this county
                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM census_block_groups
                    WHERE statefp = %s AND countyfp = %s
                    """,
                    (county_fips[:2], county_fips[2:]),
                )
                count = cur.fetchone()[0]
                if count == 0:
                    self._log(
                        f"  Warning: census_block_groups has no data for county "
                        f"{county_fips}. Cannot compute unmapped area — skipping. "
                        "Run census-tiger ingestor first."
                    )
                    return

                cur.execute(
                    """
                    INSERT INTO fema_unmapped_areas (county_fips, geom)
                    SELECT
                        %s,
                        ST_Multi(
                            ST_Difference(
                                ST_Union(bg.geom),
                                COALESCE(
                                    (SELECT ST_Union(fz.geom)
                                     FROM fema_flood_zones fz
                                     WHERE fz.county_fips = %s),
                                    'GEOMETRYCOLLECTION EMPTY'::geometry
                                )
                            )
                        )
                    FROM census_block_groups bg
                    WHERE bg.statefp = %s AND bg.countyfp = %s
                    ON CONFLICT (county_fips) DO UPDATE
                        SET geom = EXCLUDED.geom
                    """,
                    (
                        county_fips,
                        county_fips,
                        county_fips[:2],
                        county_fips[2:],
                    ),
                )
            conn.commit()
        self._log(f"  Unmapped area computed for {county_fips}.")

    def register(self) -> None:
        """Register this source in data_source_registry."""
        import datetime

        self._upsert_registry(
            version=datetime.date.today().isoformat(),
            coverage_region="ne-oklahoma",
            notes=(
                "Flood zones for NE Oklahoma counties. "
                "fema_unmapped_areas tracks areas with no FEMA coverage. "
                "Schema may vary across county GDB releases."
            ),
        )
