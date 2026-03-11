"""FCC National Broadband Map bulk ingestor.

Downloads State/Location Coverage CSV files for Fixed Broadband from the
FCC BDC public data API and loads them into the ``fcc_broadband_coverage``
PostGIS table.

Source: https://broadbandmap.fcc.gov/data-download
API:    https://bdc.fcc.gov/api/public/map (Public Data API)
Auth:   FCC_USERNAME + FCC_API_TOKEN (hash_value) — generate at
        broadbandmap.fcc.gov → username menu → Manage API Access

Coverage note: Satellite technologies (GSO=60, NGSO=61) are excluded. They
cover essentially all locations statewide and are handled separately in the
report with a note that satellite broadband is universally available.

Refresh: Semi-annual (FCC publishes new data approximately June 30 and Dec 31).
"""

from __future__ import annotations

import csv
import io
import json
import shlex
import subprocess
import zipfile
from typing import Optional
from urllib.parse import urlencode

from plinth.ingest.base import BaseIngestor

_BASE = "https://bdc.fcc.gov/api/public/map"

# Technology codes to SKIP — satellite (universally available, handled separately)
_SKIP_TECH_CODES = {"60", "61"}

# Batch size for database inserts
_BATCH_SIZE = 5000


class FccBroadbandIngestor(BaseIngestor):
    """Download FCC BDC State/Location Coverage CSVs and upsert into PostGIS.

    For each state configured in the region, fetches all Fixed Broadband
    Location Coverage files for the latest available as-of date, downloads
    each technology-type ZIP, parses the CSV, and bulk-upserts into
    ``fcc_broadband_coverage``.

    All business_residential_code values (R=Residential, B=Business, X=Both)
    are loaded. Satellite technologies (60/61) are excluded.
    """

    source_name = "fcc-broadband"
    update_frequency = "semi-annual"

    def __init__(self) -> None:
        super().__init__()
        self._as_of_date: str = ""
        self._file_manifest: list[dict] = []
        self._total_rows: int = 0

    def _auth_headers(self) -> dict[str, str]:
        token = getattr(self.settings, "fcc_api_token", "")
        username = getattr(self.settings, "fcc_username", "")
        if not token or not username:
            raise RuntimeError(
                "FCC_API_TOKEN and FCC_USERNAME must be set to run the FCC broadband ingestor."
            )
        return {"username": username, "hash_value": token, "Accept": "application/json"}

    def _fcc_get_json(self, url: str, params: Optional[dict] = None) -> dict:
        """HTTP GET to the FCC API via curl, return parsed JSON.

        Uses curl instead of Python HTTP clients because bdc.fcc.gov forces
        HTTP/2 (ALPN h2) and httpx's h2 implementation triggers a server-side
        stream reset (INTERNAL_ERROR) while curl handles it cleanly.
        """
        if params:
            url = f"{url}?{urlencode(params)}"
        auth = self._auth_headers()
        result = subprocess.run(
            ["curl", "-s", "--max-time", "60",
             "-H", f"username: {auth['username']}",
             "-H", f"hash_value: {auth['hash_value']}",
             "-H", "Accept: application/json",
             url],
            capture_output=True, text=True, timeout=65,
        )
        if result.returncode != 0:
            raise RuntimeError(f"curl failed (rc={result.returncode}): {result.stderr}")
        return json.loads(result.stdout)

    def _fcc_get_bytes(self, url: str) -> bytes:
        """HTTP GET to the FCC API via curl, return raw bytes (for ZIP downloads)."""
        auth = self._auth_headers()
        result = subprocess.run(
            ["curl", "-s", "--max-time", "300",
             "-L",  # follow redirects
             "-H", f"username: {auth['username']}",
             "-H", f"hash_value: {auth['hash_value']}",
             url],
            capture_output=True, timeout=310,
        )
        if result.returncode != 0:
            raise RuntimeError(f"curl failed (rc={result.returncode}): {result.stderr}")
        return result.stdout

    def download(self, region: Optional[str] = None) -> None:
        """Discover the latest as-of date and build the file manifest.

        Files are downloaded on-demand during load() to avoid holding large
        ZIPs on disk. The manifest (list of file_ids) is stored in memory.
        """
        self._log("Fetching list of available as-of dates…")
        data = self._fcc_get_json(f"{_BASE}/listAsOfDates")
        if data.get("status_code") != 200:
            raise RuntimeError(f"listAsOfDates failed: {data}")

        avail_dates = sorted(
            d["as_of_date"] for d in data["data"] if d.get("data_type") == "availability"
        )
        if not avail_dates:
            raise RuntimeError("No availability dates returned from FCC API.")

        self._as_of_date = avail_dates[-1]
        self._log(f"Latest availability as-of date: {self._as_of_date}")

        state_fips_list = _state_fips_for_region(region or "ne-oklahoma")
        self._log(f"States to ingest: {state_fips_list}")

        self._file_manifest = []
        for state_fips in state_fips_list:
            self._log(f"  Listing files for state FIPS {state_fips}…")
            page_data = self._fcc_get_json(
                f"{_BASE}/downloads/listAvailabilityData/{self._as_of_date}",
                params={
                    "category": "State",
                    "subcategory": "Location Coverage",
                    "technology_type": "Fixed Broadband",
                },
            )
            if page_data.get("status_code") != 200:
                raise RuntimeError(f"listAvailabilityData failed: {page_data}")

            state_files = [
                f for f in page_data.get("data", [])
                if f.get("state_fips") == state_fips
                and f.get("file_type") == "csv"
                and str(f.get("technology_code", "")) not in _SKIP_TECH_CODES
            ]
            self._log(
                f"  Found {len(state_files)} Fixed Broadband technology files for state {state_fips} "
                f"(satellite excluded)"
            )
            self._file_manifest.extend(state_files)

        self._log(f"Total files to download and ingest: {len(self._file_manifest)}")

    def validate(self) -> None:
        """Verify the manifest is populated."""
        if not self._file_manifest:
            raise ValueError("File manifest is empty — download() must run first and find files.")
        if not self._as_of_date:
            raise ValueError("No as-of date set — download() must run first.")

    def load(self) -> None:
        """Download each file, parse, and upsert into fcc_broadband_coverage."""
        from plinth.db.connection import get_connection

        self._total_rows = 0
        as_of_date = self._as_of_date

        for entry in self._file_manifest:
            file_id = entry["file_id"]
            tech_desc = entry.get("technology_code_desc", entry.get("technology_code", "?"))
            state_name = entry.get("state_name", "?")
            state_fips = entry.get("state_fips", "")
            record_count = entry.get("record_count", "?")

            self._log(
                f"  Downloading {state_name} — {tech_desc} "
                f"(file_id={file_id}, ~{record_count} rows)…"
            )

            zip_bytes = self._download_file(file_id)
            rows_loaded = self._load_csv_from_zip(
                zip_bytes, state_fips, as_of_date, get_connection
            )
            self._total_rows += rows_loaded
            self._log(f"    Loaded {rows_loaded:,} residential/mixed rows")

        self._log(f"Total rows upserted: {self._total_rows:,}")

    def register(self) -> None:
        """Upsert into data_source_registry."""
        self._upsert_registry(
            version=self._as_of_date,
            coverage_region="Oklahoma (Fixed Broadband, residential/mixed, excl. satellite)",
            notes=(
                f"FCC BDC State/Location Coverage. As-of date: {self._as_of_date}. "
                f"{self._total_rows:,} rows loaded (R+B+X). "
                "Satellite (GSO/NGSO) excluded — universally available, noted separately in reports."
            ),
        )

    # ── Private helpers ──────────────────────────────────────────────────────

    def _download_file(self, file_id: int) -> bytes:
        """Download a single availability file as bytes (ZIP)."""
        return self._fcc_get_bytes(
            f"{_BASE}/downloads/downloadFile/availability/{file_id}"
        )

    def _load_csv_from_zip(
        self,
        zip_bytes: bytes,
        state_fips: str,
        as_of_date: str,
        get_connection,
    ) -> int:
        """Parse a CSV from a ZIP archive and upsert rows into PostGIS."""
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            csv_names = [n for n in zf.namelist() if n.endswith(".csv")]
            if not csv_names:
                self._log("    Warning: no .csv found in ZIP — skipping")
                return 0
            csv_name = csv_names[0]
            with zf.open(csv_name) as raw_csv:
                reader = csv.DictReader(io.TextIOWrapper(raw_csv, encoding="utf-8"))
                return self._upsert_rows(reader, state_fips, as_of_date, get_connection)

    def _upsert_rows(
        self,
        reader: csv.DictReader,
        state_fips: str,
        as_of_date: str,
        get_connection,
    ) -> int:
        sql = """
            INSERT INTO fcc_broadband_coverage
                (location_id, provider_id, brand_name, technology_code,
                 max_download_mbps, max_upload_mbps, low_latency,
                 business_residential_code, block_geoid, state_fips, as_of_date)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (location_id, provider_id, technology_code) DO UPDATE SET
                brand_name                = EXCLUDED.brand_name,
                max_download_mbps         = EXCLUDED.max_download_mbps,
                max_upload_mbps           = EXCLUDED.max_upload_mbps,
                low_latency               = EXCLUDED.low_latency,
                business_residential_code = EXCLUDED.business_residential_code,
                block_geoid               = EXCLUDED.block_geoid,
                state_fips                = EXCLUDED.state_fips,
                as_of_date                = EXCLUDED.as_of_date
        """

        batch: list[tuple] = []
        total = 0

        with get_connection() as conn:
            with conn.cursor() as cur:
                for row in reader:
                    tech_code = row.get("technology", "")
                    if tech_code in _SKIP_TECH_CODES:
                        continue
                    brc = row.get("business_residential_code", "")
                    batch.append((
                        int(row["location_id"]),
                        row["provider_id"],
                        row["brand_name"],
                        int(tech_code) if tech_code else 0,
                        int(row.get("max_advertised_download_speed") or 0),
                        int(row.get("max_advertised_upload_speed") or 0),
                        row.get("low_latency", "0") == "1",
                        brc,
                        row.get("block_geoid", ""),
                        state_fips,
                        as_of_date,
                    ))

                    if len(batch) >= _BATCH_SIZE:
                        cur.executemany(sql, batch)
                        total += len(batch)
                        batch = []

                if batch:
                    cur.executemany(sql, batch)
                    total += len(batch)

            conn.commit()

        return total


def _state_fips_for_region(region: str) -> list[str]:
    """Return the list of 2-digit state FIPS codes for the given region slug."""
    _REGION_MAP: dict[str, list[str]] = {
        "ne-oklahoma": ["40"],
        "oklahoma": ["40"],
        "national": [
            "01", "02", "04", "05", "06", "08", "09", "10", "11", "12",
            "13", "15", "16", "17", "18", "19", "20", "21", "22", "23",
            "24", "25", "26", "27", "28", "29", "30", "31", "32", "33",
            "34", "35", "36", "37", "38", "39", "40", "41", "42", "44",
            "45", "46", "47", "48", "49", "50", "51", "53", "54", "55",
            "56",
        ],
    }
    return _REGION_MAP.get(region, ["40"])
