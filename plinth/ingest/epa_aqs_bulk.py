"""EPA AQS annual summary bulk ingestor.

Downloads pre-built annual summary ZIP files from the EPA AQS data portal
(no API key required) and loads all pollutant/monitor records into
epa_aqs_sites and epa_aqs_annual_summary.

Source: https://aqs.epa.gov/aqsweb/airdata/annual_conc_by_monitor_YYYY.zip
Coverage: National (all monitors, all pollutants)
Frequency: Annual (data lags ~6-18 months; most recent reliable year = 2 years back)
"""

from __future__ import annotations

import csv
import io
import zipfile
from datetime import date
from pathlib import Path

from plinth.ingest.base import BaseIngestor

_BASE_URL = "https://aqs.epa.gov/aqsweb/airdata"
_DATASET = "epa-aqs-bulk"
_SUMMARY_BATCH_SIZE = 2000


def _current_year() -> int:
    """Most recently complete AQS year (lags 6-18 months from publication)."""
    return date.today().year - 2


def _floatnull(val: str | None) -> float | None:
    if not val or not val.strip():
        return None
    try:
        return float(val.strip())
    except ValueError:
        return None


def _intnull(val: str | None) -> int | None:
    if not val or not val.strip():
        return None
    try:
        return int(float(val.strip()))
    except ValueError:
        return None


def _inner_csv_name(zf: zipfile.ZipFile, year: int) -> str:
    """Return the path of the CSV inside the ZIP, handling both layouts:
    - Old (2020-2023): annual_conc_by_monitor_YYYY/annual_conc_by_monitor_YYYY.csv
    - New (2024+):     annual_conc_by_monitor_YYYY.csv  (flat, no subdirectory)
    """
    nested = f"annual_conc_by_monitor_{year}/annual_conc_by_monitor_{year}.csv"
    flat = f"annual_conc_by_monitor_{year}.csv"
    names = zf.namelist()
    if nested in names:
        return nested
    if flat in names:
        return flat
    raise ValueError(f"Cannot find CSV for year {year} inside ZIP. Contents: {names}")


def _extract_hour(dt_str: str | None) -> int | None:
    """Extract the hour (0-23) from a datetime string like '5/3/2023 13:00'."""
    if not dt_str or not dt_str.strip():
        return None
    try:
        time_part = dt_str.strip().split()[-1]   # "13:00"
        return int(time_part.split(":")[0])
    except (ValueError, IndexError):
        return None


class EpaAqsBulkIngestor(BaseIngestor):
    """Ingestor for EPA AQS pre-built annual summary files.

    Downloads ``annual_conc_by_monitor_YYYY.zip`` for the requested years,
    parses all pollutant/monitor rows, and upserts into epa_aqs_sites and
    epa_aqs_annual_summary.
    """

    source_name = _DATASET
    update_frequency = "annual"

    def __init__(self, years: int = 5) -> None:
        super().__init__()
        end_year = _current_year()
        self.target_years = list(range(end_year - years + 1, end_year + 1))

    # ------------------------------------------------------------------
    # Pipeline steps
    # ------------------------------------------------------------------

    def download(self, region=None) -> None:
        for year in self.target_years:
            url = f"{_BASE_URL}/annual_conc_by_monitor_{year}.zip"
            dest = self.staging_dir / f"annual_conc_by_monitor_{year}.zip"
            fresh = self._download_if_changed(url, dest)
            if not fresh:
                size = dest.stat().st_size
                self._log(f"Skipped {year} (not modified, {size:,} bytes on disk)")
            else:
                size = dest.stat().st_size
                self._log(f"Downloaded {year} ({size:,} bytes)")

    def validate(self) -> None:
        for year in self.target_years:
            path = self.staging_dir / f"annual_conc_by_monitor_{year}.zip"
            if not path.exists():
                raise FileNotFoundError(f"Missing {path}")
            if not zipfile.is_zipfile(path):
                raise ValueError(f"Not a valid ZIP: {path}")
            # Confirm the inner CSV is present
            with zipfile.ZipFile(path) as zf:
                _inner_csv_name(zf, year)  # raises ValueError if not found
        self._log(f"Validated {len(self.target_years)} year files")

    def load(self) -> None:
        from plinth.db.connection import get_connection

        with get_connection() as conn:
            total_summaries = 0
            for year in self.target_years:
                path = self.staging_dir / f"annual_conc_by_monitor_{year}.zip"
                sites, summaries = self._load_year(conn, path, year)
                total_summaries += summaries
                self._log(f"  {year}: {sites:,} sites, {summaries:,} summary rows")
            self._log(f"Total: {total_summaries:,} summary rows across {len(self.target_years)} years")

    def register(self) -> None:
        years_str = f"{self.target_years[0]}–{self.target_years[-1]}"
        self._upsert_registry(
            version=f"AQS Annual Summary {years_str}",
            coverage_region="National",
            notes=(
                "Pre-built annual summary ZIPs from aqs.epa.gov/aqsweb/airdata. "
                "All monitors, all pollutants. Data lags 6–18 months from collection year."
            ),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_year(self, conn, path: Path, year: int) -> tuple[int, int]:
        """Load one year ZIP. Returns (unique_sites, summary_row_count)."""
        sites: dict[str, dict] = {}
        summary_batch: list[dict] = []
        flushed_site_ids: set[str] = set()
        summary_count = 0

        with zipfile.ZipFile(path) as zf:
            inner_csv = _inner_csv_name(zf, year)
            with zf.open(inner_csv) as raw:
                reader = csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8"))

                for row in reader:
                    site_id = (
                        row["State Code"].zfill(2)
                        + row["County Code"].zfill(3)
                        + row["Site Num"].zfill(4)
                    )

                    if site_id not in sites:
                        sites[site_id] = {
                            "site_id": site_id,
                            "state_code": row["State Code"].zfill(2),
                            "county_code": row["County Code"].zfill(3),
                            "site_num": row["Site Num"].zfill(4),
                            "local_site_name": row.get("Local Site Name") or None,
                            "address": row.get("Address") or None,
                            "city": row.get("City Name") or None,
                            "county_name": row.get("County Name") or None,
                            "state_name": row.get("State Name") or None,
                            "latitude": _floatnull(row.get("Latitude")),
                            "longitude": _floatnull(row.get("Longitude")),
                        }

                    summary_batch.append({
                        "site_id": site_id,
                        "year": int(row["Year"]),
                        "parameter_code": row["Parameter Code"],
                        "parameter_name": row.get("Parameter Name") or None,
                        "pollutant_standard": row.get("Pollutant Standard") or None,
                        "units": row.get("Units of Measure") or None,
                        "arithmetic_mean": _floatnull(row.get("Arithmetic Mean")),
                        "first_max_value": _floatnull(row.get("1st Max Value")),
                        "first_max_hour": _extract_hour(row.get("1st Max DateTime")),
                        "second_max_value": _floatnull(row.get("2nd Max Value")),
                        "third_max_value": _floatnull(row.get("3rd Max Value")),
                        "fourth_max_value": _floatnull(row.get("4th Max Value")),
                        "ninety_eighth_pctile": _floatnull(row.get("98th Percentile")),
                        "ninety_ninth_pctile": _floatnull(row.get("99th Percentile")),
                        "aqi": None,  # not included in pre-built annual summary CSV
                        "method_code": None,  # not included in pre-built annual summary CSV
                        "method_name": row.get("Method Name") or None,
                        "observation_count": _intnull(row.get("Observation Count")),
                        "observation_percent": _floatnull(row.get("Observation Percent")),
                        "valid_day_count": _intnull(row.get("Valid Day Count")),
                        "required_day_count": _intnull(row.get("Required Day Count")),
                        "exceptional_data_count": _intnull(row.get("Exceptional Data Count")),
                    })

                    if len(summary_batch) >= _SUMMARY_BATCH_SIZE:
                        # Flush any new sites before the summaries that reference them
                        new_site_ids = {r["site_id"] for r in summary_batch} - flushed_site_ids
                        if new_site_ids:
                            self._flush_sites(conn, [sites[s] for s in new_site_ids])
                            flushed_site_ids.update(new_site_ids)
                        _flush_summaries(conn, _dedup_summaries(summary_batch))
                        summary_count += len(summary_batch)
                        summary_batch = []

        # Final flush
        if summary_batch:
            new_site_ids = {r["site_id"] for r in summary_batch} - flushed_site_ids
            if new_site_ids:
                self._flush_sites(conn, [sites[s] for s in new_site_ids])
                flushed_site_ids.update(new_site_ids)
            _flush_summaries(conn, _dedup_summaries(summary_batch))
            summary_count += len(summary_batch)

        return len(sites), summary_count

    def _flush_sites(self, conn, site_rows: list[dict]) -> None:
        if not site_rows:
            return
        with conn.cursor() as cur:
            for s in site_rows:
                cur.execute(
                    """
                    INSERT INTO epa_aqs_sites
                        (site_id, state_code, county_code, site_num,
                         local_site_name, address, city, county_name,
                         state_name, latitude, longitude, geom)
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        CASE WHEN %s IS NOT NULL AND %s IS NOT NULL
                             THEN ST_SetSRID(ST_MakePoint(%s, %s), 4326)
                             ELSE NULL END
                    )
                    ON CONFLICT (site_id) DO UPDATE SET
                        local_site_name = EXCLUDED.local_site_name,
                        address         = EXCLUDED.address,
                        city            = EXCLUDED.city,
                        county_name     = EXCLUDED.county_name,
                        state_name      = EXCLUDED.state_name,
                        latitude        = EXCLUDED.latitude,
                        longitude       = EXCLUDED.longitude,
                        geom            = EXCLUDED.geom
                    """,
                    (
                        s["site_id"], s["state_code"], s["county_code"],
                        s["site_num"], s["local_site_name"], s["address"],
                        s["city"], s["county_name"], s["state_name"],
                        s["latitude"], s["longitude"],
                        # geom CASE params (lon, lat × 3)
                        s["longitude"], s["latitude"],
                        s["longitude"], s["latitude"],
                    ),
                )
        conn.commit()


def _dedup_summaries(batch: list[dict]) -> list[dict]:
    """Remove within-batch duplicates on the unique constraint key
    (site_id, year, parameter_code, pollutant_standard).

    The EPA CSV has one row per monitor instrument (POC) per pollutant standard.
    Multiple instruments at the same site for the same standard produce duplicate
    constraint keys in a single INSERT batch, which psycopg rejects.
    Keep the row with the highest observation_count (most complete record).
    """
    best: dict[tuple, dict] = {}
    for row in batch:
        key = (row["site_id"], row["year"], row["parameter_code"], row["pollutant_standard"])
        existing = best.get(key)
        if existing is None:
            best[key] = row
        else:
            if (row["observation_count"] or 0) > (existing["observation_count"] or 0):
                best[key] = row
    return list(best.values())


def _flush_summaries(conn, batch: list[dict]) -> None:
    """Batch-upsert summary rows using multi-row VALUES."""
    if not batch:
        return

    cols = [
        "site_id", "year", "parameter_code", "parameter_name",
        "pollutant_standard", "units", "arithmetic_mean",
        "first_max_value", "first_max_hour",
        "second_max_value", "third_max_value", "fourth_max_value",
        "ninety_eighth_pctile", "ninety_ninth_pctile",
        "aqi", "method_code", "method_name",
        "observation_count", "observation_percent",
        "valid_day_count", "required_day_count", "exceptional_data_count",
    ]
    ncols = len(cols)
    row_ph = f"({', '.join(['%s'] * ncols)})"
    col_list = ", ".join(cols)
    update_set = ", ".join(
        f"{c} = EXCLUDED.{c}"
        for c in cols
        if c not in ("site_id", "year", "parameter_code", "pollutant_standard")
    )

    safe_batch_size = max(1, 65535 // ncols)
    for i in range(0, len(batch), safe_batch_size):
        chunk = batch[i : i + safe_batch_size]
        placeholders = ", ".join(row_ph for _ in chunk)
        flat = [val for row in chunk for val in (row[c] for c in cols)]
        sql = (
            f"INSERT INTO epa_aqs_annual_summary ({col_list}) VALUES {placeholders} "
            f"ON CONFLICT (site_id, year, parameter_code, pollutant_standard) DO UPDATE SET {update_set}"
        )
        with conn.cursor() as cur:
            cur.execute(sql, flat)
    conn.commit()
