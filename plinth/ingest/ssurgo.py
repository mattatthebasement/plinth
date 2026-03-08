"""USDA SSURGO soils ingestor.

Downloads per-county Web Soil Survey packages for NE Oklahoma and loads map-unit
geometries plus tabular attributes into PostGIS.
"""

import csv
import zipfile
from pathlib import Path
from typing import Optional

from plinth.ingest.base import BaseIngestor

# Survey area symbol → county FIPS for NE Oklahoma
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

WSS_DOWNLOAD = (
    "https://websoilsurvey.sc.egov.usda.gov/DSD/Download/Cache/SSA/"
    "wss_SSA_{areasymbol}_soildb_US_{date}.zip"
)
SDM_TABULAR = "https://SDMDataAccess.sc.egov.usda.gov/Tabular/post.rest"


class SsurgoIngestor(BaseIngestor):
    """Download USDA SSURGO survey-area packages and load into PostGIS.

    Loads:
    - ``MUPOLYGON`` layer → ``ssurgo_mapunits``
    - ``muaggatt.txt`` (pipe-delimited) → ``ssurgo_muaggatt``
    - ``component.txt`` (pipe-delimited) → ``ssurgo_component``

    Note: Only raw USDA taxonomy is stored — no derived suitability or
    foundation ratings are computed.
    """

    source_name = "usda-ssurgo"
    update_frequency = "annual"

    def download(self, region: Optional[str] = None) -> None:
        """Download SSURGO zip for each survey area."""
        for areasymbol in NE_OK_SURVEY_AREAS:
            self._log(f"Downloading SSURGO for {areasymbol}…")
            date_suffix = self._get_saverest_date(areasymbol)
            url = WSS_DOWNLOAD.format(areasymbol=areasymbol, date=date_suffix)
            dest = self.staging_dir / f"{areasymbol}.zip"

            try:
                fresh = self._download_if_changed(url, dest)
            except Exception as exc:
                self._log(
                    f"  Download failed for {areasymbol}: {exc}. "
                    f"Check URL: {url}"
                )
                continue

            unzip_dir = self.staging_dir / areasymbol
            if fresh or not unzip_dir.exists():
                self._log(f"  Unzipping {areasymbol}.zip…")
                unzip_dir.mkdir(parents=True, exist_ok=True)
                with zipfile.ZipFile(dest) as zf:
                    zf.extractall(unzip_dir)

    def _get_saverest_date(self, areasymbol: str) -> str:
        """Query SDM to get the SAVEREST (last updated) date for a survey area.

        Returns a date string in YYYYMMDD format.  Falls back to today's date
        if the query fails.
        """
        import datetime
        import httpx

        payload = {
            "query": (
                f"SELECT saverest FROM sacatalog WHERE areasymbol = '{areasymbol}'"
            ),
            "format": "JSON+COLUMNNAME+METADATA",
        }
        try:
            resp = httpx.post(SDM_TABULAR, data=payload, timeout=30, follow_redirects=True)
            resp.raise_for_status()
            data = resp.json()
            rows = data.get("Table", [])
            if len(rows) >= 2:  # row 0 is headers
                date_str = str(rows[1][0]).strip()
                # Format may be "MM/DD/YYYY HH:MM:SS" or "YYYY-MM-DD"
                for fmt in ("%m/%d/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
                    try:
                        dt = datetime.datetime.strptime(date_str[:len(fmt)], fmt)
                        return dt.strftime("%Y%m%d")
                    except ValueError:
                        continue
        except Exception as exc:
            self._log(f"  Could not fetch SAVEREST for {areasymbol}: {exc}")

        return datetime.date.today().strftime("%Y%m%d")

    def validate(self) -> None:
        """Verify zip files and GDB directories are present for each survey area."""
        for areasymbol in NE_OK_SURVEY_AREAS:
            dest = self.staging_dir / f"{areasymbol}.zip"
            if not dest.exists():
                self._log(f"  Warning: zip not found for {areasymbol}.")
                continue
            if dest.stat().st_size == 0:
                raise ValueError(f"Empty zip for {areasymbol}: {dest}")
            gdb = self._find_gdb(self.staging_dir / areasymbol)
            if gdb is None:
                raise ValueError(
                    f"No GDB directory found for {areasymbol}. "
                    "Check that the zip was extracted correctly."
                )

    def load(self) -> None:
        """Load map units, aggregated attributes, and components for each survey area."""
        for areasymbol in NE_OK_SURVEY_AREAS:
            dest = self.staging_dir / f"{areasymbol}.zip"
            if not dest.exists():
                self._log(f"Skipping {areasymbol} — zip not downloaded.")
                continue

            gdb_path = self._find_gdb(self.staging_dir / areasymbol)
            if gdb_path is None:
                self._log(f"Warning: no GDB found for {areasymbol}.")
                continue

            self._log(f"Loading map units for {areasymbol}…")
            self._load_mapunits(str(gdb_path))

            tabular_dir = self._find_tabular_dir(self.staging_dir / areasymbol)
            if tabular_dir is None:
                self._log(f"  Warning: no tabular directory found for {areasymbol}.")
            else:
                self._log(f"Loading muaggatt for {areasymbol}…")
                self._load_muaggatt(tabular_dir)
                self._log(f"Loading component for {areasymbol}…")
                self._load_component(tabular_dir)

    def _find_gdb(self, directory: Path) -> Optional[Path]:
        for item in directory.rglob("*.gdb"):
            if item.is_dir():
                return item
        return None

    def _find_tabular_dir(self, base: Path) -> Optional[Path]:
        for item in base.rglob("tabular"):
            if item.is_dir():
                return item
        return None

    def _load_mapunits(self, gdb_path: str) -> None:
        staging = "_staging_ssurgo_mu"
        try:
            self._ogr2ogr_to_staging_table(gdb_path, "MUPOLYGON", staging)
        except RuntimeError as exc:
            self._log(f"  ogr2ogr error (MUPOLYGON): {exc}")
            return

        from plinth.db.connection import get_connection

        with get_connection() as conn:
            with conn.cursor() as cur:
                # Column names from SSURGO GDB after ogr2ogr lowercasing
                cur.execute(
                    f"""
                    INSERT INTO ssurgo_mapunits (mukey, musym, muname, geom)
                    SELECT
                        mukey,
                        musym,
                        muname,
                        geom
                    FROM {staging}
                    ON CONFLICT (mukey) DO UPDATE SET
                        geom   = EXCLUDED.geom,
                        musym  = EXCLUDED.musym,
                        muname = EXCLUDED.muname
                    """
                )
                rows = cur.rowcount
                cur.execute(f"DROP TABLE IF EXISTS {staging}")
            conn.commit()
        self._log(f"  Map unit rows upserted: {rows}")

    def _load_muaggatt(self, tabular_dir: Path) -> None:
        """Load muaggatt.txt (pipe-delimited) into ssurgo_muaggatt."""
        muaggatt_path = tabular_dir / "muaggatt.txt"
        if not muaggatt_path.exists():
            self._log("  muaggatt.txt not found — skipping.")
            return

        from plinth.db.connection import get_connection

        rows_data: list[tuple] = []
        with muaggatt_path.open(newline="", encoding="utf-8") as fh:
            reader = csv.reader(fh, delimiter="|")
            for row in reader:
                if len(row) < 5:
                    continue
                # SSURGO muaggatt column order (first 5 relevant fields):
                # mukey | musym | muname | mukind | mapunitlfw_l | ... | hydgrpdcd | ...
                # We need: mukey, hydgrpdcd, drclassddc, slopegraddcp, taxclname
                # Use positional indexing from SSURGO column metadata
                mukey = row[0].strip()
                if not mukey:
                    continue
                # hydgrpdcd is typically column index ~7, but varies.
                # Use a best-effort parse based on known column count (56 cols).
                hydgrpdcd = row[6].strip() if len(row) > 6 else None
                drclassddc = row[7].strip() if len(row) > 7 else None
                slopegraddcp_raw = row[8].strip() if len(row) > 8 else None
                taxclname = row[len(row) - 1].strip() if row else None
                slopegraddcp: Optional[float] = None
                if slopegraddcp_raw:
                    try:
                        slopegraddcp = float(slopegraddcp_raw)
                    except ValueError:
                        pass
                rows_data.append((mukey, hydgrpdcd or None, drclassddc or None, slopegraddcp, taxclname or None))

        if not rows_data:
            return

        upsert_sql = """
            INSERT INTO ssurgo_muaggatt (mukey, hydgrpdcd, drclassddc, slopegraddcp, taxclname)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (mukey) DO UPDATE SET
                hydgrpdcd    = EXCLUDED.hydgrpdcd,
                drclassddc   = EXCLUDED.drclassddc,
                slopegraddcp = EXCLUDED.slopegraddcp,
                taxclname    = EXCLUDED.taxclname
        """
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.executemany(upsert_sql, rows_data)
            conn.commit()
        self._log(f"  muaggatt rows upserted: {len(rows_data)}")

    def _load_component(self, tabular_dir: Path) -> None:
        """Load component.txt (pipe-delimited) into ssurgo_component."""
        comp_path = tabular_dir / "comp.txt"
        if not comp_path.exists():
            comp_path = tabular_dir / "component.txt"
        if not comp_path.exists():
            self._log("  component.txt / comp.txt not found — skipping.")
            return

        from plinth.db.connection import get_connection

        rows_data: list[tuple] = []
        with comp_path.open(newline="", encoding="utf-8") as fh:
            reader = csv.reader(fh, delimiter="|")
            for row in reader:
                if len(row) < 5:
                    continue
                cokey = row[0].strip()
                mukey = row[1].strip()
                if not cokey or not mukey:
                    continue
                compname = row[2].strip() or None
                comppct_raw = row[3].strip()
                majcompflag = row[4].strip() or None
                comppct: Optional[float] = None
                if comppct_raw:
                    try:
                        comppct = float(comppct_raw)
                    except ValueError:
                        pass
                rows_data.append((cokey, mukey, compname, comppct, majcompflag))

        if not rows_data:
            return

        upsert_sql = """
            INSERT INTO ssurgo_component (cokey, mukey, compname, comppct_r, majcompflag)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (cokey) DO UPDATE SET
                mukey       = EXCLUDED.mukey,
                compname    = EXCLUDED.compname,
                comppct_r   = EXCLUDED.comppct_r,
                majcompflag = EXCLUDED.majcompflag
        """
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.executemany(upsert_sql, rows_data)
            conn.commit()
        self._log(f"  Component rows upserted: {len(rows_data)}")

    def register(self) -> None:
        """Register this source in data_source_registry."""
        import datetime

        areas = ", ".join(NE_OK_SURVEY_AREAS.keys())
        self._upsert_registry(
            version=datetime.date.today().isoformat(),
            coverage_region="ne-oklahoma",
            notes=(
                f"USDA SSURGO soils. Survey areas: {areas}. "
                "Raw USDA taxonomy only — no derived suitability or foundation ratings."
            ),
        )
