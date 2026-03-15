"""FEMA National Flood Hazard Layer (NFHL) ingestor.

Queries the FEMA NFHL ArcGIS REST API (layer 28 — Flood Hazard Zones) directly
as GeoJSON per county, then loads into PostGIS.  Also computes *unmapped areas*
(county boundary minus flood zones) so sites with no FEMA data are never
silently classified as Zone X.

National mode (default): fetches all counties in the US by querying the
census_block_groups table for a distinct county list.  Downloads run in parallel
using a thread pool.

Region mode: pass ``region="ne-oklahoma"`` to restrict to the 8-county
NE-Oklahoma test area.
"""

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
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

_COUNTIES_CACHE = "counties.json"
_MAX_WORKERS = 8


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

    def _get_county_dict(self, region: Optional[str]) -> dict[str, str]:
        """Return {fips: label} for the counties to process.

        If region="ne-oklahoma", returns the hardcoded 8-county dict.
        Otherwise queries census_block_groups for all distinct counties.
        """
        if region == "ne-oklahoma":
            return NE_OKLAHOMA_COUNTIES

        from plinth.db.connection import get_connection

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT DISTINCT statefp || countyfp FROM census_block_groups ORDER BY 1"
                )
                rows = cur.fetchall()
        return {row[0]: row[0] for row in rows}

    def download(self, region: Optional[str] = None) -> None:
        """Fetch flood zone GeoJSON for all counties (or a named region)."""
        import datetime
        import httpx

        self._skipped = set()
        counties = self._get_county_dict(region)

        # Persist county list to staging so validate/load can use it without DB
        self.staging_dir.mkdir(parents=True, exist_ok=True)
        (self.staging_dir / _COUNTIES_CACHE).write_text(json.dumps(list(counties.keys())))

        today = datetime.date.today().isoformat()
        pending = []
        for fips, name in counties.items():
            dest = self.staging_dir / f"{fips}.geojson"
            meta = self.staging_dir / f"{fips}.meta.json"
            if dest.exists() and meta.exists():
                saved = json.loads(meta.read_text()).get("fetched_date", "")
                if saved == today:
                    continue
            pending.append((fips, name))

        total = len(counties)
        already_done = total - len(pending)
        self._log(
            f"Counties: {total} total, {already_done} up to date, "
            f"{len(pending)} to fetch (workers={_MAX_WORKERS})."
        )

        if not pending:
            return

        def _fetch_one(fips_name):
            fips, name = fips_name
            client = httpx.Client(timeout=60, follow_redirects=True)
            try:
                features = self._fetch_county_features(fips, client)
            except Exception as exc:
                return fips, name, exc, None
            finally:
                client.close()
            return fips, name, None, features

        done = 0
        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
            futures = {pool.submit(_fetch_one, item): item for item in pending}
            for future in as_completed(futures):
                fips, name, exc, features = future.result()
                done += 1
                if exc is not None:
                    self._log(
                        f"  [{done}/{len(pending)}] Warning: FEMA API failed for "
                        f"{name} ({fips}): {exc}. Skipping."
                    )
                    self._skipped.add(fips)
                    continue

                fc = {"type": "FeatureCollection", "features": features}
                dest = self.staging_dir / f"{fips}.geojson"
                meta = self.staging_dir / f"{fips}.meta.json"
                dest.write_text(json.dumps(fc))
                meta.write_text(json.dumps({
                    "fetched_date": datetime.date.today().isoformat(),
                    "count": len(features),
                }))
                if done % 100 == 0 or done == len(pending):
                    self._log(f"  [{done}/{len(pending)}] fetched {fips} ({len(features)} features).")

    def _fetch_county_features(self, fips: str, client) -> list:
        """Page through the NFHL REST API for one county, returning all features.

        Uses 200 records/page to keep geometry payload sizes well within the
        limit that causes FEMA's ArcGIS server to 500.
        """
        features: list = []
        offset = 0
        while True:
            params = {
                "where": f"DFIRM_ID LIKE '{fips}%'",
                "outFields": "DFIRM_ID,FLD_ZONE,ZONE_SUBTY,SFHA_TF,BFE_REVERT,STATIC_BFE",
                "outSR": "4326",
                "returnGeometry": "true",
                "resultOffset": str(offset),
                "resultRecordCount": "200",
                "f": "geojson",
            }
            resp = client.get(_NFHL_QUERY, params=params)
            resp.raise_for_status()
            batch = resp.json().get("features", [])
            features.extend(batch)
            if len(batch) < 200:
                break
            offset += 200
        return features

    def _load_county_list(self) -> list[str]:
        """Load persisted county FIPS list from staging directory."""
        cache = self.staging_dir / _COUNTIES_CACHE
        if cache.exists():
            return json.loads(cache.read_text())
        # Fallback: scan for .geojson files
        return [p.stem for p in self.staging_dir.glob("*.geojson")]

    def validate(self) -> None:
        """Check that downloaded county GeoJSON files are present and non-empty."""
        skipped = getattr(self, "_skipped", set())
        counties = self._load_county_list()
        missing = 0
        for fips in counties:
            if fips in skipped:
                continue
            dest = self.staging_dir / f"{fips}.geojson"
            if not dest.exists():
                missing += 1
                if missing <= 5:
                    self._log(f"  Warning: GeoJSON not found for {fips}: {dest}")
        if missing:
            self._log(f"  {missing} counties missing GeoJSON (will be skipped in load).")

    def load(self) -> None:
        """Load flood zones and compute unmapped areas for each county."""
        skipped = getattr(self, "_skipped", set())
        counties = self._load_county_list()
        loaded = 0
        for fips in counties:
            if fips in skipped:
                continue
            geojson_path = self.staging_dir / f"{fips}.geojson"
            if not geojson_path.exists():
                continue

            self._load_flood_zones(fips, str(geojson_path))
            self._compute_unmapped(fips)
            loaded += 1
            if loaded % 100 == 0:
                self._log(f"  Loaded {loaded}/{len(counties)} counties…")

        self._log(f"Load complete: {loaded} counties processed.")

    def _load_flood_zones(self, county_fips: str, geojson_path: str) -> None:
        import json as _json

        # Check for empty feature collection — many rural counties have no mapped zones
        with open(geojson_path) as f:
            fc = _json.load(f)
        if not fc.get("features"):
            self._log(f"  {county_fips}: no flood zone features (unmapped) — skipping ogr2ogr.")
            return

        # GeoJSON from FEMA ArcGIS has UPPERCASE property names (DFIRM_ID, FLD_ZONE, etc.).
        # Use -sql with lowercase aliases to ensure consistent PostgreSQL column names.
        layer_name = Path(geojson_path).stem
        staging = "_staging_flood_zones"
        sql = (
            f"SELECT DFIRM_ID AS dfirm_id, FLD_ZONE AS fld_zone, "
            f"ZONE_SUBTY AS zone_subty, SFHA_TF AS sfha_tf, "
            f"BFE_REVERT AS bfe_revert, STATIC_BFE AS static_bfe "
            f'FROM "{layer_name}"'
        )
        s = self.settings
        pg_dsn = (
            f"PG:host={s.postgres_host} port={s.postgres_port} "
            f"dbname={s.postgres_db} user={s.postgres_user} "
            f"password={s.postgres_password}"
        )
        import subprocess as _sp
        cmd = [
            "ogr2ogr",
            "-f", "PostgreSQL", pg_dsn,
            "-overwrite",
            "-nln", staging,
            "-t_srs", "EPSG:4326",
            "-nlt", "PROMOTE_TO_MULTI",
            "-lco", "GEOMETRY_NAME=geom",
            "-sql", sql,
            geojson_path,
        ]
        result = _sp.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            self._log(f"  ogr2ogr error for {county_fips}: {result.stderr[:300]}")
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
        self._log(f"  {county_fips}: {rows} flood zone rows inserted.")

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
                                    ST_GeomFromText('GEOMETRYCOLLECTION EMPTY', 4326)
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

    def register(self) -> None:
        """Register this source in data_source_registry."""
        import datetime

        counties = self._load_county_list()
        is_national = len(counties) > 100
        coverage = "national" if is_national else "ne-oklahoma"
        self._upsert_registry(
            version=datetime.date.today().isoformat(),
            coverage_region=coverage,
            notes=(
                f"Flood zones for {len(counties)} counties ({coverage}). "
                "fema_unmapped_areas tracks areas with no FEMA coverage. "
                "Schema may vary across county GDB releases."
            ),
        )
