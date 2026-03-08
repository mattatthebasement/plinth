"""FEMA National Flood Hazard Layer (NFHL) ingestor.

Downloads per-county GDB packages from FEMA MSC and loads flood-zone polygons
into PostGIS.  Also computes *unmapped areas* (county boundary minus flood zones)
so that sites with no FEMA data are never silently classified as Zone X.
"""

import zipfile
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

_NFHL_QUERY_BASE = (
    "https://hazards.fema.gov/gis/nfhl/rest/services/public/NFHL/MapServer/28/query"
)
_MSC_DOWNLOAD = (
    "https://msc.fema.gov/portal/downloadProduct"
    "?productTypeID=NFHL&productSubTypeID=&productID=NFHL_{fips}"
)
_HAZARDS_DOWNLOAD = (
    "https://hazards.fema.gov/nfhlv2/output/County/NFHL_{fips}_{date}.zip"
)


class FemaNfhlIngestor(BaseIngestor):
    """Download FEMA NFHL county GDBs and load flood-zone polygons.

    For each county:
    1. Query the FEMA NFHL REST service to discover the current effective date.
    2. Download the county GDB package (trying MSC portal first, then the
       direct hazards.fema.gov URL).
    3. Load ``S_FLD_HAZ_AR`` into ``fema_flood_zones`` via ogr2ogr.
    4. Compute the unmapped area (county boundary minus flood zones) and store
       in ``fema_unmapped_areas``.
    """

    source_name = "fema-nfhl"
    update_frequency = "monthly"

    # county_fips → effective-date string discovered during download()
    _eff_dates: dict[str, str]

    def download(self, region: Optional[str] = None) -> None:
        """Download NFHL GDB zips for all NE-Oklahoma counties."""
        import datetime
        import httpx

        self._eff_dates = {}
        counties = NE_OKLAHOMA_COUNTIES

        for fips, name in counties.items():
            self._log(f"Fetching effective date for {name} ({fips})…")
            eff_date = self._get_effective_date(fips)
            self._eff_dates[fips] = eff_date
            self._log(f"  Effective date: {eff_date}")

            dest = self.staging_dir / f"{fips}.zip"
            downloaded = False

            # Try MSC portal first
            msc_url = _MSC_DOWNLOAD.format(fips=fips)
            try:
                downloaded = self._download_if_changed(msc_url, dest)
            except Exception as exc:
                self._log(
                    f"  MSC portal download failed for {fips}: {exc}. "
                    f"Trying direct hazards.fema.gov URL."
                )
                # Fallback: use effective date to build direct URL
                date_suffix = eff_date.replace("-", "") if eff_date else (
                    datetime.date.today().strftime("%Y%m%d")
                )
                fallback_url = _HAZARDS_DOWNLOAD.format(
                    fips=fips, date=date_suffix
                )
                try:
                    downloaded = self._download_if_changed(fallback_url, dest)
                except Exception as exc2:
                    self._log(
                        f"  Fallback download also failed for {fips}: {exc2}. "
                        f"Check updated URL at: {fallback_url}"
                    )
                    continue

            unzip_dir = self.staging_dir / fips
            if downloaded or not unzip_dir.exists():
                self._log(f"  Unzipping {fips}.zip…")
                unzip_dir.mkdir(parents=True, exist_ok=True)
                try:
                    with zipfile.ZipFile(dest) as zf:
                        zf.extractall(unzip_dir)
                except zipfile.BadZipFile as exc:
                    self._log(f"  Bad zip for {fips}: {exc}")

    def _get_effective_date(self, county_fips: str) -> str:
        """Query the FEMA REST API for the latest effective date for a county."""
        import httpx
        import datetime

        params = {
            "where": f"DFIRM_ID LIKE '{county_fips}%'",
            "outFields": "EFF_DATE",
            "returnDistinctValues": "true",
            "orderByFields": "EFF_DATE DESC",
            "resultRecordCount": "1",
            "f": "json",
        }
        try:
            resp = httpx.get(_NFHL_QUERY_BASE, params=params, timeout=30, follow_redirects=True)
            resp.raise_for_status()
            data = resp.json()
            features = data.get("features", [])
            if features:
                raw = features[0]["attributes"].get("EFF_DATE")
                if raw is not None:
                    # EFF_DATE may be a Unix ms timestamp or a string
                    if isinstance(raw, (int, float)):
                        dt = datetime.datetime.fromtimestamp(raw / 1000, tz=datetime.timezone.utc)
                        return dt.strftime("%Y%m%d")
                    return str(raw).replace("-", "")[:8]
        except Exception as exc:
            self._log(f"  Could not fetch effective date for {county_fips}: {exc}")

        return datetime.date.today().strftime("%Y%m%d")

    def validate(self) -> None:
        """Check that all county zips are present and non-empty."""
        for fips in NE_OKLAHOMA_COUNTIES:
            dest = self.staging_dir / f"{fips}.zip"
            if not dest.exists():
                self._log(f"  Warning: zip not found for {fips}, skipping validation.")
                continue
            if dest.stat().st_size == 0:
                raise ValueError(f"Empty zip file for county {fips}: {dest}")

            unzip_dir = self.staging_dir / fips
            if not unzip_dir.exists() or not any(unzip_dir.iterdir()):
                raise ValueError(
                    f"GDB directory missing or empty for county {fips}: {unzip_dir}"
                )

    def load(self) -> None:
        """Load flood zones and compute unmapped areas for each county."""
        for fips, name in NE_OKLAHOMA_COUNTIES.items():
            dest = self.staging_dir / f"{fips}.zip"
            if not dest.exists():
                self._log(f"Skipping {name} ({fips}) — zip not downloaded.")
                continue

            gdb_path = self._find_gdb(self.staging_dir / fips)
            if gdb_path is None:
                self._log(
                    f"Warning: no GDB found for {name} ({fips}). "
                    "Schema may vary across county GDB releases."
                )
                continue

            self._log(f"Loading flood zones for {name} ({fips})…")
            self._load_flood_zones(fips, str(gdb_path))
            self._log(f"Computing unmapped areas for {name} ({fips})…")
            self._compute_unmapped(fips)

    def _find_gdb(self, directory: Path) -> Optional[Path]:
        """Return the first .gdb directory found under *directory*."""
        for item in directory.rglob("*.gdb"):
            if item.is_dir():
                return item
        return None

    def _load_flood_zones(self, county_fips: str, gdb_path: str) -> None:
        staging = "_staging_flood_zones"
        try:
            self._ogr2ogr_to_staging_table(gdb_path, "S_FLD_HAZ_AR", staging)
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
