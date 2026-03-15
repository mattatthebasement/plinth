"""EPA Safe Drinking Water Information System (SDWIS) ingestor.

Downloads the SDWIS bulk data ZIP from EPA's ECHO platform (no API key
required). Parses four CSV files and loads into sdwis_water_systems:

  WATER_SYSTEM.csv    — system metadata (name, type, source, population)
  SERVICE_AREA.csv    — county FIPS codes served by each system
  VIOLATIONS.csv      — health-based violations for violation count summary
  GEOGRAPHIC_AREA.csv — zip codes and city/county associations

Only CWS (Community Water System) and NTNC (Non-Transient Non-Community)
systems are loaded; TNC (transient campgrounds/gas stations) are skipped.

Source:  EPA ECHO bulk download
         https://echo.epa.gov/files/echodownloads/SDWA_latest_downloads.zip
Refresh: Monthly (SDWIS data is updated quarterly by EPA)
"""
from __future__ import annotations

import csv
import io
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Optional

from plinth.ingest.base import BaseIngestor

_DOWNLOAD_URL = "https://echo.epa.gov/files/echodownloads/SDWA_latest_downloads.zip"
_ZIP_FILE = "SDWA_latest_downloads.zip"

# Actual CSV filenames inside the ZIP (SDWA_ prefix, as of 2025)
_CSV_WATER_SYSTEMS = "SDWA_PUB_WATER_SYSTEMS.csv"
_CSV_SERVICE_AREAS = "SDWA_SERVICE_AREAS.csv"
_CSV_VIOLATIONS    = "SDWA_VIOLATIONS_ENFORCEMENT.csv"
_CSV_GEO_AREAS     = "SDWA_GEOGRAPHIC_AREAS.csv"

# System types to include
_INCLUDE_TYPES = {"CWS", "NTNC"}


class EpaSdwisIngestor(BaseIngestor):
    """Download EPA SDWIS bulk CSVs and load into sdwis_water_systems.

    Loads all active CWS and NTNC systems nationally with county-level
    service area attribution and a 5-year health violation count.
    """

    source_name = "epa-sdwis"
    update_frequency = "monthly"

    @property
    def _zip_path(self) -> Path:
        return self.staging_dir / _ZIP_FILE

    def download(self, region: Optional[str] = None) -> None:
        """Download SDWIS bulk ZIP with ETag-based idempotency."""
        self._log("Checking EPA SDWIS bulk download…")
        fetched = self._download_if_changed(_DOWNLOAD_URL, self._zip_path)
        if not fetched:
            self._log("ZIP is up-to-date (ETag matched).")

    def validate(self) -> None:
        """Verify ZIP is present and contains expected CSV files."""
        if not self._zip_path.exists():
            raise ValueError(f"SDWIS ZIP not found: {self._zip_path}")
        if self._zip_path.stat().st_size < 5_000_000:
            raise ValueError(f"ZIP suspiciously small: {self._zip_path.stat().st_size} bytes")

        with zipfile.ZipFile(self._zip_path) as zf:
            names = set(zf.namelist())

        required = {_CSV_WATER_SYSTEMS, _CSV_SERVICE_AREAS, _CSV_VIOLATIONS, _CSV_GEO_AREAS}
        missing = required - names
        if missing:
            raise ValueError(f"Missing CSV files in SDWIS ZIP: {missing}")
        self._log("Validation passed — SDWIS ZIP contains required CSV files.")

    def load(self) -> None:
        """Parse CSVs and upsert into sdwis_water_systems."""
        from plinth.db.connection import get_connection

        with zipfile.ZipFile(self._zip_path) as zf:
            water_systems, data_quarter = self._parse_water_system(zf)
            self._log(f"  Parsed {len(water_systems):,} CWS/NTNC water systems.")

            counties_by_pwsid, zips_by_pwsid = self._parse_geographic_areas(zf)
            self._log(f"  Parsed geographic areas for {len(counties_by_pwsid):,} systems.")

            violation_counts = self._parse_violations(zf)
            self._log(f"  Computed violation counts for {len(violation_counts):,} systems.")

        # Merge all data into water_systems
        for pwsid, row in water_systems.items():
            row["counties_served"] = counties_by_pwsid.get(pwsid, [])
            row["violation_count_5yr"] = violation_counts.get(pwsid, 0)
            row["zip_codes"] = zips_by_pwsid.get(pwsid, [])
            row["data_quarter"] = data_quarter

        rows = list(water_systems.values())
        self._log(f"Upserting {len(rows):,} rows into sdwis_water_systems…")

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.executemany(
                    """
                    INSERT INTO sdwis_water_systems (
                        pwsid, pws_name, pws_type_code, primary_source,
                        owner_type_code, population_served, service_connections,
                        state_code, primary_county, city_served,
                        zip_codes, counties_served, activity_code,
                        violation_count_5yr, data_quarter
                    ) VALUES (
                        %(pwsid)s, %(pws_name)s, %(pws_type_code)s, %(primary_source)s,
                        %(owner_type_code)s, %(population_served)s, %(service_connections)s,
                        %(state_code)s, %(primary_county)s, %(city_served)s,
                        %(zip_codes)s, %(counties_served)s, %(activity_code)s,
                        %(violation_count_5yr)s, %(data_quarter)s
                    )
                    ON CONFLICT (pwsid) DO UPDATE SET
                        pws_name            = EXCLUDED.pws_name,
                        pws_type_code       = EXCLUDED.pws_type_code,
                        primary_source      = EXCLUDED.primary_source,
                        owner_type_code     = EXCLUDED.owner_type_code,
                        population_served   = EXCLUDED.population_served,
                        service_connections = EXCLUDED.service_connections,
                        state_code          = EXCLUDED.state_code,
                        primary_county      = EXCLUDED.primary_county,
                        city_served         = EXCLUDED.city_served,
                        zip_codes           = EXCLUDED.zip_codes,
                        counties_served     = EXCLUDED.counties_served,
                        activity_code       = EXCLUDED.activity_code,
                        violation_count_5yr = EXCLUDED.violation_count_5yr,
                        data_quarter        = EXCLUDED.data_quarter,
                        updated_at          = now()
                    """,
                    rows,
                )
            conn.commit()
        self._log(f"  Upserted {len(rows):,} water systems.")

    def register(self) -> None:
        self._upsert_registry(
            version="latest",
            coverage_region="national",
            notes=(
                "EPA SDWIS via ECHO bulk download. "
                "CWS and NTNC systems only. County-level service area attribution. "
                "5-year health violation counts."
            ),
        )

    # ------------------------------------------------------------------
    # Private CSV parsers
    # ------------------------------------------------------------------

    def _find_csv(self, zf: zipfile.ZipFile, name: str) -> str:
        """Return the ZIP member path matching *name* (exact match)."""
        if name in zf.namelist():
            return name
        # Fallback: case-insensitive search
        for member in zf.namelist():
            if member.upper() == name.upper():
                return member
        raise ValueError(f"CSV file not found in ZIP: {name}")

    def _read_csv(self, zf: zipfile.ZipFile, name: str):
        """Open a ZIP member as a CSV DictReader."""
        member = self._find_csv(zf, name)
        f = io.TextIOWrapper(zf.open(member), encoding="latin-1", errors="replace")
        return csv.DictReader(f)

    def _parse_water_system(self, zf: zipfile.ZipFile) -> tuple[dict, str]:
        """Parse SDWA_PUB_WATER_SYSTEMS.csv. Returns (dict keyed by PWSID, data_quarter)."""
        systems: dict[str, dict] = {}
        data_quarter = "unknown"

        for row in self._read_csv(zf, _CSV_WATER_SYSTEMS):
            pws_type = (row.get("PWS_TYPE_CODE") or "").strip()
            if pws_type not in _INCLUDE_TYPES:
                continue

            pwsid = (row.get("PWSID") or "").strip()
            if not pwsid:
                continue

            quarter_raw = (row.get("SUBMISSIONYEARQUARTER") or "").strip()
            if quarter_raw and len(quarter_raw) >= 5:
                data_quarter = f"{quarter_raw[:4]}Q{quarter_raw[4]}"

            def _int(col: str) -> Optional[int]:
                try:
                    return int(row.get(col, "") or 0)
                except (ValueError, TypeError):
                    return None

            systems[pwsid] = {
                "pwsid": pwsid,
                "pws_name": (row.get("PWS_NAME") or "").strip() or f"PWS {pwsid}",
                "pws_type_code": pws_type,
                "primary_source": (row.get("PRIMARY_SOURCE_CODE") or "").strip() or None,
                "owner_type_code": (row.get("OWNER_TYPE_CODE") or "").strip() or None,
                "population_served": _int("POPULATION_SERVED_COUNT"),
                "service_connections": _int("SERVICE_CONNECTIONS_COUNT"),
                "state_code": (row.get("STATE_CODE") or row.get("PRIMACY_AGENCY_CODE") or "").strip()[:2] or None,
                "primary_county": None,  # populated from GEOGRAPHIC_AREAS
                "city_served": (row.get("CITY_NAME") or "").strip() or None,
                "activity_code": (row.get("PWS_ACTIVITY_CODE") or "A").strip(),
            }

        return systems, data_quarter

    def _parse_violations(self, zf: zipfile.ZipFile) -> dict[str, int]:
        """Parse SDWA_VIOLATIONS_ENFORCEMENT.csv → {pwsid: health_violation_count (5 yr)}."""
        import datetime
        cutoff_year = datetime.date.today().year - 5
        counts: dict[str, int] = defaultdict(int)

        for row in self._read_csv(zf, _CSV_VIOLATIONS):
            pwsid = (row.get("PWSID") or "").strip()
            is_health = (row.get("IS_HEALTH_BASED_IND") or "").strip().upper()
            # Date format is MM/DD/YYYY — extract year from last 4 chars
            date_raw = (row.get("COMPL_PER_BEGIN_DATE") or "").strip()
            if len(date_raw) >= 4:
                year_raw = date_raw[-4:]
            else:
                continue

            try:
                year = int(year_raw)
            except ValueError:
                continue

            if year >= cutoff_year and is_health == "Y":
                counts[pwsid] += 1

        return dict(counts)

    def _parse_geographic_areas(self, zf: zipfile.ZipFile) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
        """Parse SDWA_GEOGRAPHIC_AREAS.csv → ({pwsid: [county, …]}, {pwsid: [zip, …]})."""
        counties: dict[str, set[str]] = defaultdict(set)
        zips: dict[str, set[str]] = defaultdict(set)

        for row in self._read_csv(zf, _CSV_GEO_AREAS):
            pwsid = (row.get("PWSID") or "").strip()
            if not pwsid:
                continue
            county = (row.get("COUNTY_SERVED") or "").strip()
            if county:
                counties[pwsid].add(county)
            zip_code = (row.get("ZIP_CODE_SERVED") or "").strip()
            if zip_code:
                zips[pwsid].add(zip_code)

        counties_out = {k: sorted(v) for k, v in counties.items()}
        zips_out = {k: sorted(v) for k, v in zips.items()}
        return counties_out, zips_out
