"""USGS NWIS Groundwater Monitoring Wells ingestor.

Downloads the USGS NWIS groundwater monitoring site inventory for all US
states via the NWIS site web services, then fetches pre-computed depth-to-water
statistics for sites that have approved daily-value groundwater level data, and
loads everything into usgs_groundwater_wells.

Also downloads the last 3 years of discrete groundwater level readings via the
new USGS Water Data OGC API and loads all readings per well into
usgs_groundwater_well_readings.  A second pass fetches the historical window
(3–20 years ago) into a separate cache.  Fetches all four depth-to-water parameter
codes (72019, 62610, 62611, 72150) — same measurement, different instruments — to
maximise coverage of recently-measured wells.  These observed readings let report
users cross-check the modeled water table depth (Ma et al. 2025 COG) against real
nearby measurements.

Three-step process:
  1. Site inventory — all NWIS groundwater monitoring sites (GW type) per state
  2. DTW statistics — parameter 72019 (depth to water, ft below land surface)
     monthly statistical summaries for sites with approved daily values
  3. Recent readings — last 3 years of discrete field measurements via the
     new OGC API (api.waterdata.usgs.gov), cursor-paginated nationally.

~800K sites nationally; a large fraction are monitoring wells with depth-to-water
data. Sites without depth-to-water measurements are still loaded (dtw_* = NULL)
as they may carry useful aquifer code / well depth information.

Source:  USGS National Water Information System
         Site inventory: https://waterservices.usgs.gov/nwis/site/
         Statistics:     https://waterservices.usgs.gov/nwis/stat/
         GW levels:      https://api.waterdata.usgs.gov/ogcapi/v0/collections/field-measurements/
Refresh: Annual

Note: The legacy waterservices.usgs.gov/nwis/gwlevels/ endpoint is being
decommissioned in early 2027; readings now use the new OGC API.
"""
from __future__ import annotations

import csv
import io
import time
from pathlib import Path
from typing import Optional

import httpx

from plinth.ingest.base import BaseIngestor

_SITE_BASE_URL  = "https://waterservices.usgs.gov/nwis/site/"
_STAT_BASE_URL  = "https://waterservices.usgs.gov/nwis/stat/"
# New OGC API — replaces deprecated waterservices.usgs.gov/nwis/gwlevels/
_FIELD_MEAS_URL = "https://api.waterdata.usgs.gov/ogcapi/v0/collections/field-measurements/items"

# How many years of recent readings to download (0 → _READINGS_YEARS)
_READINGS_YEARS = 3
# How many years back to extend the historical window (_READINGS_YEARS → _READINGS_HISTORY_YEARS)
_READINGS_HISTORY_YEARS = 20
# All USGS parameter codes that represent depth-to-water below land surface (ft).
# 72019 = standard DTW; 62610/62611/72150 = same measurement, different instruments.
# Fetching all four gives the most complete coverage of recently-measured wells.
_GW_DEPTH_PARAMETER_CODES = ["72019", "62610", "62611", "72150"]
# Qualifiers indicating a reading is NOT a static measurement (skip these)
# No qualifier filtering — all readings are stored regardless of qualifier.
# The qualifier is surfaced in reports so users can interpret the reading themselves.

# USGS state codes for all 50 states + DC + PR + VI
_STATE_CODES = [
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "DC", "PR", "VI",
]

# Request delay between paginated API calls
_REQUEST_DELAY_S = 2.0

# RDB column names (USGS tab-delimited format)
_SITE_COLS = {
    "agency_cd", "site_no", "station_nm", "site_tp_cd", "dec_lat_va",
    "dec_long_va", "coord_acy_cd", "state_cd", "county_cd",
    "aqfr_cd", "nat_aqfr_cd", "well_depth_va", "hole_depth_va",
}


def _parse_rdb(text: str, expected_cols: set[str] | None = None) -> list[dict]:
    """Parse USGS RDB (tab-delimited) format. Skips # comment lines and type row."""
    lines = []
    header: list[str] | None = None

    for line in text.splitlines():
        if line.startswith("#") or not line.strip():
            continue
        if header is None:
            header = line.split("\t")
            continue
        # Second non-comment line is the type descriptor row (e.g. "5s\t10s\t…") — skip it
        if all(part.endswith("s") or part.endswith("n") or part.endswith("d")
               for part in line.split("\t") if part):
            continue
        if header:
            row = dict(zip(header, line.split("\t")))
            lines.append(row)

    return lines


class UsgsGroundwaterWellsIngestor(BaseIngestor):
    """Download USGS NWIS groundwater wells and load into PostGIS.

    The full national download is done state-by-state to stay within NWIS
    service limits. Each state's site data is cached to staging so re-runs
    only re-fetch stale files.
    """

    source_name = "usgs-groundwater-wells"
    update_frequency = "annual"

    def download(self, region: Optional[str] = None) -> None:
        """Download site inventory, DTW monthly statistics, and recent discrete readings.

        Three-pass approach:
          1. Site inventory — all NWIS groundwater monitoring sites per state.
          2. DTW statistics — for sites with approved daily-value parameterCd=72019,
             fetch MONTHLY stats in batches of 20 sites.
          3. Recent readings — last 3 years of discrete gwlevels per state.
        """
        self._log("Downloading USGS NWIS groundwater site inventory (state by state)…")
        for state in _STATE_CODES:
            self._download_state_sites(state)

        self._log("Downloading USGS NWIS DTW statistics (batched MONTHLY stats)…")
        for state in _STATE_CODES:
            self._download_state_stats(state)

        self._log(f"Downloading USGS NWIS discrete readings (last {_READINGS_YEARS} years)…")
        self._download_readings_national()

        self._log(f"Downloading USGS NWIS historical readings ({_READINGS_YEARS}–{_READINGS_HISTORY_YEARS} years ago)…")
        self._download_readings_historical()

    def _download_state_sites(self, state: str) -> None:
        """Download site inventory for one state, cached to staging."""
        cache = self.staging_dir / f"sites_{state}.rdb"
        if cache.exists():
            age_days = (time.time() - cache.stat().st_mtime) / 86400
            if age_days < 365:
                return  # fresh enough

        try:
            resp = httpx.get(
                _SITE_BASE_URL,
                params={
                    "stateCd": state,
                    "siteType": "GW",
                    "siteStatus": "all",
                    "hasDataTypeCd": "gw",
                    "siteOutput": "expanded",
                    "format": "rdb",
                },
                timeout=120,
            )
            resp.raise_for_status()
            cache.write_text(resp.text)
            time.sleep(_REQUEST_DELAY_S)
        except Exception as exc:
            self._log(f"  Warning: failed to fetch sites for {state}: {exc}")

    def _fetch_state_dtw_site_nos(self, state: str) -> list[str]:
        """Return site_nos in a state with *daily-value* DTW records.

        The /nwis/stat/ endpoint only computes statistics from approved daily
        values (hasDataTypeCd=dv).  Discrete groundwater level measurements
        (hasDataTypeCd=gw) have no pre-computed stats.
        """
        try:
            resp = httpx.get(
                _SITE_BASE_URL,
                params={
                    "stateCd": state,
                    "siteType": "GW",
                    "siteStatus": "all",
                    "hasDataTypeCd": "dv",
                    "parameterCd": "72019",
                    "format": "rdb",
                },
                timeout=120,
            )
            resp.raise_for_status()
            rows = _parse_rdb(resp.text)
            time.sleep(_REQUEST_DELAY_S)
            return [r["site_no"].strip() for r in rows if r.get("site_no", "").strip()]
        except Exception as exc:
            self._log(f"  Warning: failed to fetch DTW site list for {state}: {exc}")
            return []

    def _download_state_stats(self, state: str) -> None:
        """Download depth-to-water MONTHLY statistics for all 72019 sites in one state.

        Two-step process:
          1. GET /nwis/site/ with stateCd+parameterCd=72019 to get site_nos.
          2. Batch site_nos 100 at a time to /nwis/stat/?statReportType=MONTHLY.

        The /nwis/stat/ endpoint only accepts 'sites=' as a geographic filter;
        stateCd and other geo parameters are not supported by that endpoint.
        """
        cache = self.staging_dir / f"stats_{state}.rdb"
        if cache.exists():
            age_days = (time.time() - cache.stat().st_mtime) / 86400
            if age_days < 365:
                return

        site_nos = self._fetch_state_dtw_site_nos(state)
        if not site_nos:
            cache.write_text(f"# No sites with parameterCd=72019 data in {state}\n")
            return

        self._log(f"  {state}: {len(site_nos)} DTW sites — fetching MONTHLY stats in batches…")

        header_line: str | None = None
        type_line: str | None = None
        data_lines: list[str] = []

        # Batch size of 20: each site_no is 15 chars; 20 sites ≈ 400 chars of
        # query string — well within URL length limits that cause 400 errors with
        # larger batches.
        _BATCH = 20
        for i in range(0, len(site_nos), _BATCH):
            batch = site_nos[i : i + _BATCH]
            try:
                resp = httpx.get(
                    _STAT_BASE_URL,
                    params={
                        "format": "rdb",
                        "parameterCd": "72019",
                        "statReportType": "MONTHLY",
                        "sites": ",".join(batch),
                    },
                    timeout=120,
                )
                resp.raise_for_status()
                for line in resp.text.splitlines():
                    if line.startswith("#") or not line.strip():
                        continue
                    if header_line is None:
                        header_line = line
                        continue
                    if type_line is None:
                        type_line = line
                        continue
                    data_lines.append(line)
                time.sleep(_REQUEST_DELAY_S)
            except Exception as exc:
                self._log(f"  Warning: stats batch {i // _BATCH + 1} for {state}: {exc}")

        if header_line is None:
            cache.write_text(f"# No MONTHLY DTW stats returned for {state}\n")
            return

        out_lines = [
            f"# DTW MONTHLY stats for {state} — {len(data_lines):,} data rows",
            header_line,
            type_line or "",
        ] + data_lines
        cache.write_text("\n".join(out_lines) + "\n")

    def _api_headers(self) -> dict[str, str]:
        """Return auth headers for USGS Water Data API calls."""
        from plinth.config import get_settings
        key = get_settings().usgs_api_key
        return {"X-Api-Key": key} if key else {}

    def _fetch_with_retry(self, url: str, params: dict | None = None, max_retries: int = 5) -> tuple[dict, dict]:
        """GET a URL with exponential backoff on 429 / 503.

        Returns (response_json, response_headers).
        """
        delay = 4.0
        headers = self._api_headers()
        for attempt in range(max_retries):
            resp = httpx.get(url, params=params, headers=headers, timeout=120)
            if resp.status_code in (429, 503):
                retry_after = int(resp.headers.get("Retry-After", delay))
                wait = max(retry_after, delay)
                self._log(f"  Rate-limited ({resp.status_code}), waiting {wait:.0f}s…")
                time.sleep(wait)
                delay = min(delay * 2, 120)
                continue
            resp.raise_for_status()
            return resp.json(), dict(resp.headers)
        resp.raise_for_status()
        return {}, {}

    def _download_readings_national(self) -> None:
        """Download last 3 years of discrete GW level readings from the USGS OGC API.

        Fetches all four depth-to-water parameter codes (72019, 62610, 62611,
        72150) — same measurement, different instruments — to maximise coverage
        of recently-measured wells.  Iterates cursor-based pagination nationally
        for each code.  Caches to readings_national.jsonl (one GeoJSON feature
        per line).  Skips if cache is < 365 days old.
        """
        import datetime
        import json

        cache = self.staging_dir / "readings_national.jsonl"
        if cache.exists():
            age_days = (time.time() - cache.stat().st_mtime) / 86400
            first_line = cache.open().readline(200)
            if age_days < 365 and not first_line.startswith("# Error"):
                self._log(f"  Readings cache is {age_days:.0f} days old — skipping download.")
                return

        start_dt = (
            datetime.date.today().replace(year=datetime.date.today().year - _READINGS_YEARS)
        ).isoformat() + "T00:00:00Z"
        end_dt = datetime.date.today().isoformat() + "T23:59:59Z"

        count = 0

        try:
            with cache.open("w") as fh:
                for param_code in _GW_DEPTH_PARAMETER_CODES:
                    self._log(f"  Fetching parameter_code={param_code}…")
                    data, hdrs = self._fetch_with_retry(
                        _FIELD_MEAS_URL,
                        params={
                            "f": "json",
                            "parameter_code": param_code,
                            "datetime": f"{start_dt}/{end_dt}",
                            "limit": 1000,
                        },
                    )

                    for feature in data.get("features", []):
                        fh.write(json.dumps(feature) + "\n")
                        count += 1

                    while True:
                        next_url = next(
                            (lnk["href"] for lnk in data.get("links", []) if lnk.get("rel") == "next"),
                            None,
                        )
                        if not next_url:
                            break

                        # Honour rate-limit headers — pause longer when quota is low
                        remaining = int(hdrs.get("x-ratelimit-remaining", 999))
                        limit = int(hdrs.get("x-ratelimit-limit", 1000))
                        if remaining < 50:
                            pause = _REQUEST_DELAY_S * 10
                            self._log(f"  Rate quota low ({remaining}/{limit}), pausing {pause:.0f}s…")
                        else:
                            pause = _REQUEST_DELAY_S
                        time.sleep(pause)

                        data, hdrs = self._fetch_with_retry(next_url)

                        for feature in data.get("features", []):
                            fh.write(json.dumps(feature) + "\n")
                            count += 1

                        if count % 100_000 == 0:
                            self._log(f"  … fetched {count:,} readings so far (quota: {remaining}/{limit})")

        except Exception as exc:
            self._log(f"  Warning: failed to fetch national readings: {exc}")
            cache.write_text(f"# Error fetching national readings: {exc}\n")
            return

        self._log(f"  Downloaded {count:,} total readings.")

    def _download_readings_historical(self) -> None:
        """Download the historical window of GW level readings (_READINGS_YEARS to
        _READINGS_HISTORY_YEARS ago) from the USGS OGC API.

        Complements _download_readings_national() which covers 0–_READINGS_YEARS.
        Caches to readings_historical.jsonl.  Skips if cache is < 365 days old.
        """
        import datetime
        import json

        cache = self.staging_dir / "readings_historical.jsonl"
        if cache.exists():
            age_days = (time.time() - cache.stat().st_mtime) / 86400
            first_line = cache.open().readline(200)
            if age_days < 365 and not first_line.startswith("# Error"):
                self._log(f"  Historical readings cache is {age_days:.0f} days old — skipping download.")
                return

        today = datetime.date.today()
        start_dt = today.replace(year=today.year - _READINGS_HISTORY_YEARS).isoformat() + "T00:00:00Z"
        end_dt = today.replace(year=today.year - _READINGS_YEARS).isoformat() + "T23:59:59Z"

        count = 0

        try:
            with cache.open("w") as fh:
                for param_code in _GW_DEPTH_PARAMETER_CODES:
                    self._log(f"  Fetching historical parameter_code={param_code}…")
                    data, hdrs = self._fetch_with_retry(
                        _FIELD_MEAS_URL,
                        params={
                            "f": "json",
                            "parameter_code": param_code,
                            "datetime": f"{start_dt}/{end_dt}",
                            "limit": 1000,
                        },
                    )

                    for feature in data.get("features", []):
                        fh.write(json.dumps(feature) + "\n")
                        count += 1

                    while True:
                        next_url = next(
                            (lnk["href"] for lnk in data.get("links", []) if lnk.get("rel") == "next"),
                            None,
                        )
                        if not next_url:
                            break

                        remaining = int(hdrs.get("x-ratelimit-remaining", 999))
                        limit = int(hdrs.get("x-ratelimit-limit", 1000))
                        if remaining < 50:
                            pause = _REQUEST_DELAY_S * 10
                            self._log(f"  Rate quota low ({remaining}/{limit}), pausing {pause:.0f}s…")
                        else:
                            pause = _REQUEST_DELAY_S
                        time.sleep(pause)

                        data, hdrs = self._fetch_with_retry(next_url)

                        for feature in data.get("features", []):
                            fh.write(json.dumps(feature) + "\n")
                            count += 1

                        if count % 100_000 == 0:
                            self._log(f"  … fetched {count:,} historical readings so far (quota: {remaining}/{limit})")

        except Exception as exc:
            self._log(f"  Warning: failed to fetch historical readings: {exc}")
            cache.write_text(f"# Error fetching historical readings: {exc}\n")
            return

        self._log(f"  Downloaded {count:,} total historical readings.")

    def validate(self) -> None:
        """Verify at least 40 state site files exist and total sites are reasonable."""
        site_files = list(self.staging_dir.glob("sites_*.rdb"))
        if len(site_files) < 40:
            raise ValueError(
                f"Only {len(site_files)} state site files found — expected 50+. "
                "Re-run download."
            )
        self._log(f"Validation passed — {len(site_files)} state site files found.")

    def load(self) -> None:
        """Parse all state RDB files and upsert into usgs_groundwater_wells."""
        from plinth.db.connection import get_connection

        # Build depth-to-water stats index from stat RDB files
        self._log("Building depth-to-water statistics index…")
        dtw_stats = self._build_dtw_stats()
        self._log(f"  Stats loaded for {len(dtw_stats):,} wells.")

        self._log("Parsing site inventory files…")
        batch: list[dict] = []
        total_loaded = 0

        with get_connection() as conn:
            for state in _STATE_CODES:
                cache = self.staging_dir / f"sites_{state}.rdb"
                if not cache.exists():
                    continue

                rows = _parse_rdb(cache.read_text())
                state_rows = []
                for row in rows:
                    site = self._parse_site_row(row, dtw_stats)
                    if site:
                        state_rows.append(site)

                if state_rows:
                    batch.extend(state_rows)

                # Flush every 5,000 rows
                if len(batch) >= 5_000:
                    self._upsert_batch(conn, batch)
                    total_loaded += len(batch)
                    self._log(f"  … loaded {total_loaded:,} wells so far")
                    batch = []

            if batch:
                self._upsert_batch(conn, batch)
                total_loaded += len(batch)

        self._log(f"  Total: upserted {total_loaded:,} groundwater wells.")

        self._log("Loading recent discrete groundwater level readings…")
        self._load_readings()

    def _load_readings(self) -> None:
        """Parse readings_national.jsonl and readings_historical.jsonl and upsert
        into usgs_groundwater_well_readings.

        Loads all readings from both JSONL caches, filtered to sites present in
        usgs_groundwater_wells. Skips any cache file that is missing or errored.
        """
        import datetime
        import json
        from plinth.db.connection import get_connection

        cache_files = [
            self.staging_dir / "readings_national.jsonl",
            self.staging_dir / "readings_historical.jsonl",
        ]
        valid_caches = []
        for cache in cache_files:
            if not cache.exists():
                self._log(f"  No cache found at {cache.name} — skipping.")
                continue
            first_line = cache.open().readline(200)
            if first_line.startswith("# Error"):
                self._log(f"  Cache {cache.name} contains an error — skipping.")
                continue
            valid_caches.append(cache)

        if not valid_caches:
            self._log("  No readings cache files found — skipping.")
            return

        site_readings: dict[str, list[dict]] = {}

        for cache in valid_caches:
            self._log(f"  Parsing {cache.name}…")
            with cache.open() as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        feature = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    props = feature.get("properties", {})
                    loc_id = (props.get("monitoring_location_id") or "").strip()
                    if not loc_id.startswith("USGS-"):
                        continue
                    site_no = loc_id[5:]  # strip "USGS-" prefix

                    time_str = (props.get("time") or "").strip()
                    if not time_str:
                        continue
                    try:
                        lev_dt = datetime.date.fromisoformat(time_str[:10])
                    except ValueError:
                        continue

                    qualifiers = props.get("qualifier") or []
                    qualifier_str = qualifiers[0] if qualifiers else None

                    value_str = (props.get("value") or "").strip()
                    try:
                        lev_va = float(value_str) if value_str else None
                    except ValueError:
                        lev_va = None

                    reading = {
                        "site_no": site_no,
                        "lev_dt": lev_dt,
                        "lev_va": lev_va,
                        "parameter_code": props.get("parameter_code"),
                        "qualifier": qualifier_str,
                    }

                    site_readings.setdefault(site_no, []).append(reading)

        flat: list[dict] = []
        for site_no, readings in site_readings.items():
            flat.extend(readings)

        if not flat:
            self._log("  No discrete readings found.")
            return

        with get_connection() as conn:
            with conn.cursor() as cur:
                # Load only readings whose site_no exists in usgs_groundwater_wells;
                # the OGC API returns readings for all site types, not just GW monitors.
                cur.execute("SELECT site_no FROM usgs_groundwater_wells")
                known_sites = {r[0] for r in cur.fetchall()}
                flat = [r for r in flat if r["site_no"] in known_sites]
                if not flat:
                    self._log("  No readings matched known GW well sites.")
                    return

                cur.executemany(
                    """
                    INSERT INTO usgs_groundwater_well_readings
                        (site_no, lev_dt, lev_va, parameter_code, qualifier)
                    VALUES
                        (%(site_no)s, %(lev_dt)s, %(lev_va)s, %(parameter_code)s, %(qualifier)s)
                    ON CONFLICT (site_no, lev_dt, COALESCE(qualifier, '')) DO UPDATE SET
                        lev_va         = EXCLUDED.lev_va,
                        parameter_code = EXCLUDED.parameter_code
                    """,
                    flat,
                )
            conn.commit()

        self._log(f"  Upserted {len(flat):,} readings for {len(site_readings):,} wells.")

    def _build_dtw_stats(self) -> dict[str, dict]:
        """Parse all stats_*.rdb files and return {site_no: {dtw stats}}.

        Stats files contain MONTHLY data: one row per site/year/month with
        'mean_va' = mean depth-to-water for that month.  We aggregate across
        all rows per site:
          dtw_min_ft    = shallowest month (wet-season high water table)
          dtw_max_ft    = deepest month    (dry-season low water table)
          dtw_median_ft = median of all monthly means  (typical depth)
          dtw_mean_ft   = mean   of all monthly means
        """
        site_values: dict[str, list[float]] = {}
        site_counts: dict[str, int] = {}
        site_years:  dict[str, list[int]] = {}

        for state in _STATE_CODES:
            cache = self.staging_dir / f"stats_{state}.rdb"
            if not cache.exists():
                continue

            rows = _parse_rdb(cache.read_text())
            for row in rows:
                site_no = (row.get("site_no") or "").strip()
                if not site_no:
                    continue
                try:
                    mean_va = float(row.get("mean_va") or "")
                except (ValueError, TypeError):
                    continue
                try:
                    count_nu = int(row.get("count_nu") or 0)
                except (ValueError, TypeError):
                    count_nu = 0
                try:
                    year_nu = int(row.get("year_nu") or 0)
                except (ValueError, TypeError):
                    year_nu = 0

                if site_no not in site_values:
                    site_values[site_no] = []
                    site_counts[site_no] = 0
                    site_years[site_no] = []
                site_values[site_no].append(mean_va)
                site_counts[site_no] += count_nu
                if year_nu:
                    site_years[site_no].append(year_nu)

        stats: dict[str, dict] = {}
        for site_no, values in site_values.items():
            if not values:
                continue
            sv = sorted(values)
            n = len(sv)
            median = sv[n // 2] if n % 2 == 1 else (sv[n // 2 - 1] + sv[n // 2]) / 2.0
            years = sorted(set(site_years.get(site_no, [])))
            stats[site_no] = {
                "dtw_median_ft":    round(median, 3),
                "dtw_mean_ft":      round(sum(values) / n, 3),
                "dtw_min_ft":       round(min(values), 3),  # shallowest (wet season)
                "dtw_max_ft":       round(max(values), 3),  # deepest    (dry season)
                "dtw_obs_count":    site_counts[site_no] or None,
                "dtw_period_start": f"{years[0]}-01-01"  if years else None,
                "dtw_period_end":   f"{years[-1]}-12-31" if years else None,
            }

        return stats

    def _parse_site_row(self, row: dict, dtw_stats: dict) -> Optional[dict]:
        """Parse one NWIS site row into an upsert dict."""
        site_no = (row.get("site_no") or "").strip()
        if not site_no:
            return None

        try:
            lat = float(row.get("dec_lat_va") or "")
            lon = float(row.get("dec_long_va") or "")
        except (ValueError, TypeError):
            return None  # Skip sites without coordinates

        def _f(col: str) -> Optional[float]:
            try:
                return float(row.get(col, "") or "")
            except (ValueError, TypeError):
                return None

        def _s(col: str) -> Optional[str]:
            v = (row.get(col) or "").strip()
            return v if v else None

        dtw = dtw_stats.get(site_no, {})

        return {
            "site_no": site_no,
            "station_nm": _s("station_nm"),
            "state_cd": _s("state_cd"),
            "county_cd": _s("county_cd"),
            "aquifer_cd": _s("aqfr_cd"),
            "nat_aqfr_cd": _s("nat_aqfr_cd"),
            "well_depth_ft": _f("well_depth_va"),
            "hole_depth_ft": _f("hole_depth_va"),
            "lat": lat,
            "lon": lon,
            "dtw_median_ft": dtw.get("dtw_median_ft"),
            "dtw_mean_ft": dtw.get("dtw_mean_ft"),
            "dtw_min_ft": dtw.get("dtw_min_ft"),
            "dtw_max_ft": dtw.get("dtw_max_ft"),
            "dtw_obs_count": dtw.get("dtw_obs_count"),
            "dtw_period_start": dtw.get("dtw_period_start"),
            "dtw_period_end": dtw.get("dtw_period_end"),
        }

    def _upsert_batch(self, conn, batch: list[dict]) -> None:
        """Upsert a batch of well rows."""
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO usgs_groundwater_wells (
                    site_no, station_nm, state_cd, county_cd,
                    aquifer_cd, nat_aqfr_cd, well_depth_ft, hole_depth_ft,
                    geom,
                    dtw_median_ft, dtw_mean_ft, dtw_min_ft, dtw_max_ft,
                    dtw_obs_count, dtw_period_start, dtw_period_end
                ) VALUES (
                    %(site_no)s, %(station_nm)s, %(state_cd)s, %(county_cd)s,
                    %(aquifer_cd)s, %(nat_aqfr_cd)s, %(well_depth_ft)s, %(hole_depth_ft)s,
                    ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326),
                    %(dtw_median_ft)s, %(dtw_mean_ft)s, %(dtw_min_ft)s, %(dtw_max_ft)s,
                    %(dtw_obs_count)s, %(dtw_period_start)s, %(dtw_period_end)s
                )
                ON CONFLICT (site_no) DO UPDATE SET
                    station_nm       = EXCLUDED.station_nm,
                    county_cd        = EXCLUDED.county_cd,
                    aquifer_cd       = EXCLUDED.aquifer_cd,
                    nat_aqfr_cd      = EXCLUDED.nat_aqfr_cd,
                    well_depth_ft    = EXCLUDED.well_depth_ft,
                    hole_depth_ft    = EXCLUDED.hole_depth_ft,
                    geom             = EXCLUDED.geom,
                    dtw_median_ft    = EXCLUDED.dtw_median_ft,
                    dtw_mean_ft      = EXCLUDED.dtw_mean_ft,
                    dtw_min_ft       = EXCLUDED.dtw_min_ft,
                    dtw_max_ft       = EXCLUDED.dtw_max_ft,
                    dtw_obs_count    = EXCLUDED.dtw_obs_count,
                    dtw_period_start = EXCLUDED.dtw_period_start,
                    dtw_period_end   = EXCLUDED.dtw_period_end,
                    updated_at       = now()
                """,
                batch,
            )
        conn.commit()

    def register(self) -> None:
        self._upsert_registry(
            version=str(__import__("datetime").date.today().year),
            coverage_region="national",
            notes=(
                "USGS NWIS groundwater monitoring site inventory. "
                "~800k sites nationally with pre-aggregated depth-to-water statistics "
                "(parameter 72019). State-by-state download from waterservices.usgs.gov."
            ),
        )
