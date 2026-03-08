"""USDA SSURGO soils ingestor.

Uses the NRCS Soil Data Mart WFS to load map-unit geometries plus extended
attributes into PostGIS, and the SDM Tabular API for component-level data.
"""

import json
from pathlib import Path
from typing import Optional

from plinth.ingest.base import BaseIngestor

WFS_URL = "WFS:https://SDMDataAccess.sc.egov.usda.gov/Spatial/SDMWGS84Geographic.wfs"
WFS_LAYER = "mapunitpolyextended"
SDM_TABULAR = "https://SDMDataAccess.nrcs.usda.gov/Tabular/post.rest"

NE_OK_SURVEY_AREAS: dict[str, str] = {
    "OK021": "40021",  # Cherokee
    "OK035": "40035",  # Craig
    "OK041": "40041",  # Delaware
    "OK097": "40097",  # Mayes
    "OK115": "40115",  # Ottawa
    "OK131": "40131",  # Rogers
    "OK143": "40143",  # Tulsa
    "OK145": "40145",  # Wagoner
}

_BATCH_SIZE = 500


class SsurgoIngestor(BaseIngestor):
    """Load USDA SSURGO soils data via WFS and SDM Tabular API.

    Loads:
    - WFS ``mapunitpolyextended`` layer → ``ssurgo_mapunits`` + ``ssurgo_muaggatt``
    - SDM Tabular component query → ``ssurgo_component``

    Note: Only raw USDA taxonomy is stored — no derived suitability or
    foundation ratings are computed.
    """

    source_name = "usda-ssurgo"
    update_frequency = "annual"

    def download(self, region: Optional[str] = None) -> None:
        """Fetch SSURGO map units and components from NRCS web services."""
        meta_path = self.staging_dir / "meta.json"
        if self._is_fresh(meta_path, ttl_days=30):
            self._log("SSURGO data is up-to-date (< 30 days old).")
            return

        areas = list(NE_OK_SURVEY_AREAS.keys())
        self._log(f"Fetching SSURGO for {len(areas)} survey areas…")
        self._fetch_mapunits_via_wfs(areas)
        self._fetch_components_via_sdm(areas)

        meta_path.write_text(json.dumps({"fetched_date": __import__("datetime").date.today().isoformat()}))

    def _fetch_mapunits_via_wfs(self, areas: list[str]) -> None:
        """Load mapunitpolyextended into a staging table via WFS, one county at a time.

        ogr2ogr's -spat flag sends an OGC XML BBOX filter that this WFS server
        rejects (400). Instead, we download GML directly via httpx using the
        BBOX as a URL query parameter (which the server accepts), write to a
        temp file, then load from file.

        The SDM WFS has a ~10.1 billion sq-m bbox area limit, so we query per
        county using bboxes from census_block_groups.
        """
        import subprocess
        import tempfile

        import httpx

        from plinth.db.connection import get_connection

        s = self.settings
        pg_dsn = (
            f"PG:host={s.postgres_host} port={s.postgres_port} "
            f"dbname={s.postgres_db} user={s.postgres_user} "
            f"password={s.postgres_password}"
        )

        countyfps = [NE_OK_SURVEY_AREAS[a][-3:] for a in areas if a in NE_OK_SURVEY_AREAS]
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT countyfp,
                        ST_XMin(ST_Extent(geom))::numeric(8,4),
                        ST_YMin(ST_Extent(geom))::numeric(8,4),
                        ST_XMax(ST_Extent(geom))::numeric(8,4),
                        ST_YMax(ST_Extent(geom))::numeric(8,4)
                    FROM census_block_groups
                    WHERE statefp='40' AND countyfp = ANY(%s)
                    GROUP BY countyfp
                """, (countyfps,))
                county_bboxes = {row[0]: row[1:] for row in cur.fetchall()}

        first = True
        for sym, fips in NE_OK_SURVEY_AREAS.items():
            if sym not in areas:
                continue
            countyfp = fips[-3:]
            if countyfp not in county_bboxes:
                self._log(f"  Warning: no bbox found for {sym} ({fips}), skipping.")
                continue
            minx, miny, maxx, maxy = county_bboxes[countyfp]
            buf = 0.02
            bbox = f"{float(minx)-buf},{float(miny)-buf},{float(maxx)+buf},{float(maxy)+buf}"
            self._log(f"  Fetching WFS GML for {sym} (BBOX {bbox})…")

            url = (
                "https://SDMDataAccess.sc.egov.usda.gov/Spatial/SDMWGS84Geographic.wfs"
                f"?SERVICE=WFS&VERSION=1.1.0&REQUEST=GetFeature"
                f"&TYPENAME={WFS_LAYER}&BBOX={bbox}"
            )
            try:
                resp = httpx.get(url, timeout=120, follow_redirects=True)
                resp.raise_for_status()
            except Exception as exc:
                self._log(f"  Warning: WFS fetch failed for {sym}: {exc}")
                continue

            if b"ServiceException" in resp.content[:200]:
                self._log(f"  Warning: WFS returned error for {sym}: {resp.text[:200]}")
                continue

            with tempfile.NamedTemporaryFile(suffix=".gml", delete=False) as tmp:
                tmp.write(resp.content)
                tmp_path = tmp.name

            mode_flags = ["-overwrite"] if first else ["-append", "-update"]
            cmd = [
                "ogr2ogr",
                "-f", "PostgreSQL",
                pg_dsn,
                *mode_flags,
                "-nln", "_staging_ssurgo_wfs",
                "-t_srs", "EPSG:4326",
                "-nlt", "PROMOTE_TO_MULTI",
                "-lco", "GEOMETRY_NAME=geom",
                "-lco", "FID=gid",
                tmp_path,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            __import__("os").unlink(tmp_path)
            if result.returncode != 0:
                self._log(f"  Warning: ogr2ogr load failed for {sym}: {result.stderr[:300]}")
                continue
            first = False
            self._log(f"  Loaded {sym}.")

        if first:
            raise RuntimeError("WFS load failed for all survey areas.")

    def _fetch_components_via_sdm(self, areas: list[str]) -> None:
        """Query SDM Tabular for component data and cache as JSON."""
        import httpx

        area_list = ",".join(f"'{a}'" for a in areas)
        query = f"""
            SELECT c.cokey, c.mukey, c.compname, c.comppct_r, c.majcompflag
            FROM component c
            JOIN mapunit mu ON c.mukey = mu.mukey
            JOIN legend l ON mu.lkey = l.lkey
            WHERE l.areasymbol IN ({area_list})
        """
        self._log("  Querying SDM for component data…")
        try:
            resp = httpx.post(
                SDM_TABULAR,
                data={"query": query, "format": "JSON+COLUMNNAME+METADATA"},
                timeout=120,
                follow_redirects=True,
            )
            resp.raise_for_status()
            data = resp.json()
            rows = data.get("Table", [])
            # rows[0] = headers, rows[1] = metadata, rows[2:] = data
            data_rows = rows[2:] if len(rows) > 2 else []
            cache_path = self.staging_dir / "components.json"
            cache_path.write_text(json.dumps(data_rows))
            self._log(f"  Component rows fetched: {len(data_rows)}")
        except Exception as exc:
            self._log(f"  Warning: component fetch failed: {exc}")
            cache_path = self.staging_dir / "components.json"
            cache_path.write_text(json.dumps([]))

    def validate(self) -> None:
        """Verify staging table and component cache are present."""
        from plinth.db.connection import get_connection

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM information_schema.tables "
                    "WHERE table_name = '_staging_ssurgo_wfs'"
                )
                exists = cur.fetchone()[0]

        if not exists:
            raise ValueError(
                "Staging table _staging_ssurgo_wfs not found. Run download() first."
            )

        comp_path = self.staging_dir / "components.json"
        if not comp_path.exists():
            raise ValueError("Component cache not found. Run download() first.")

        self._log("Validation passed.")

    def load(self) -> None:
        """Upsert map units, muaggatt attributes, and components into PostGIS."""
        self._load_mapunits_and_muaggatt()
        self._load_components()

    def _load_mapunits_and_muaggatt(self) -> None:
        from plinth.db.connection import get_connection

        self._log("Loading ssurgo_mapunits from WFS staging table…")
        with get_connection() as conn:
            with conn.cursor() as cur:
                area_list = ",".join(f"'{a}'" for a in NE_OK_SURVEY_AREAS)
                # Deduplicate: bboxes overlap, so the same mukey may appear more
                # than once in the staging table. Use DISTINCT ON to keep one row.
                cur.execute(f"""
                    INSERT INTO ssurgo_mapunits (mukey, musym, muname, geom)
                    SELECT DISTINCT ON (mukey) mukey, musym, muname, geom
                    FROM _staging_ssurgo_wfs
                    WHERE areasymbol IN ({area_list})
                    ORDER BY mukey
                    ON CONFLICT (mukey) DO UPDATE SET
                        musym  = EXCLUDED.musym,
                        muname = EXCLUDED.muname,
                        geom   = EXCLUDED.geom
                """)
                mu_rows = cur.rowcount
                self._log(f"  ssurgo_mapunits upserted: {mu_rows}")

                cur.execute(f"""
                    INSERT INTO ssurgo_muaggatt (mukey, hydgrpdcd, drclassdcd, slopegraddcp, taxclname)
                    SELECT DISTINCT ON (mukey) mukey, hydgrpdcd, drclassdcd, slopegraddcp::numeric, NULL
                    FROM _staging_ssurgo_wfs
                    WHERE areasymbol IN ({area_list})
                    ORDER BY mukey
                    ON CONFLICT (mukey) DO UPDATE SET
                        hydgrpdcd    = EXCLUDED.hydgrpdcd,
                        drclassdcd   = EXCLUDED.drclassdcd,
                        slopegraddcp = EXCLUDED.slopegraddcp
                """)
                mua_rows = cur.rowcount
                self._log(f"  ssurgo_muaggatt upserted: {mua_rows}")

                cur.execute("DROP TABLE IF EXISTS _staging_ssurgo_wfs")
            conn.commit()

    def _load_components(self) -> None:
        comp_path = self.staging_dir / "components.json"
        rows = json.loads(comp_path.read_text())
        if not rows:
            self._log("  No component data to load.")
            return

        from plinth.db.connection import get_connection

        self._log(f"Loading {len(rows)} component rows…")
        upsert_sql = """
            INSERT INTO ssurgo_component (cokey, mukey, compname, comppct_r, majcompflag)
            VALUES (%s, %s, %s, %s::numeric, %s)
            ON CONFLICT (cokey) DO UPDATE SET
                mukey       = EXCLUDED.mukey,
                compname    = EXCLUDED.compname,
                comppct_r   = EXCLUDED.comppct_r,
                majcompflag = EXCLUDED.majcompflag
        """
        batch: list[tuple] = []
        total = 0
        with get_connection() as conn:
            for row in rows:
                cokey, mukey, compname, comppct_r, majcompflag = row
                batch.append((
                    cokey or None, mukey or None,
                    compname or None,
                    comppct_r if comppct_r not in (None, "", "None") else None,
                    majcompflag or None,
                ))
                if len(batch) >= _BATCH_SIZE:
                    with conn.cursor() as cur:
                        cur.executemany(upsert_sql, batch)
                    conn.commit()
                    total += len(batch)
                    batch = []
            if batch:
                with conn.cursor() as cur:
                    cur.executemany(upsert_sql, batch)
                conn.commit()
                total += len(batch)
        self._log(f"  ssurgo_component upserted: {total}")

    def _is_fresh(self, path: Path, ttl_days: int = 30) -> bool:
        if not path.exists():
            return False
        import datetime
        age = datetime.datetime.now() - datetime.datetime.fromtimestamp(path.stat().st_mtime)
        return age.days < ttl_days

    def register(self) -> None:
        """Register this source in data_source_registry."""
        import datetime

        areas = ", ".join(NE_OK_SURVEY_AREAS.keys())
        self._upsert_registry(
            version=datetime.date.today().isoformat(),
            coverage_region="ne-oklahoma",
            notes=(
                f"USDA SSURGO soils via NRCS WFS. Survey areas: {areas}. "
                "Raw USDA taxonomy only — no derived suitability or foundation ratings."
            ),
        )
