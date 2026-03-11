"""Census ACS 5-Year Summary File bulk ingestor.

Downloads pre-built table `.dat` files from the Census Bureau's ACS Summary
File server (no API key required) and loads all block group rows into the
``acs_block_group_data`` table.

Loads all states (national coverage) — files are provided nationally by the
Census Bureau and loading all ~240k block groups future-proofs coverage for
any US address.
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Optional

from plinth.ingest.base import BaseIngestor
from plinth.ingest.api.census_acs import ACS_VARS

log = logging.getLogger(__name__)

_DEFAULT_YEAR = 2023
_SUMLEVEL_PREFIX = "1500000US"  # block group SUMLEVEL=150 prefix in GEO_ID
_BATCH_SIZE = 5000

# Base URL for ACS 5-Year Summary File table data files
_BASE_URL = (
    "https://www2.census.gov/programs-surveys/acs/summary_file"
    "/{year}/table-based-SF/data/5YRData/acsdt5y{year}-{table}.dat"
)


def _api_code_to_file_col(code: str) -> str:
    """Convert a Census API variable code to its Summary File column name.

    Census API:   ``B01003_001E``  (table + underscore + seq + type_letter)
    Summary File: ``B01003_E001``  (table + underscore + type_letter + seq)
    """
    table, rest = code.rsplit("_", 1)
    seq = rest[:-1]     # e.g. "001"
    letter = rest[-1]   # e.g. "E"
    return f"{table}_{letter}{seq}"


# Build lookup: file column name → DB column name (for both _E and _M variants)
# e.g. "B01003_E001" → "total_population"
#      "B01003_M001" → "total_population_moe"
_FILE_COL_TO_DB: dict[str, str] = {}
for _code, _field in ACS_VARS.items():
    _est_col = _api_code_to_file_col(_code)              # e.g. "B01003_E001"
    _moe_col = _est_col.replace("_E", "_M", 1)           # e.g. "B01003_M001"
    _FILE_COL_TO_DB[_est_col] = _field
    _FILE_COL_TO_DB[_moe_col] = f"{_field}_moe"

# Group variable file columns by table prefix (e.g. "b01003")
# Each group corresponds to one .dat file.
_TABLE_GROUPS: dict[str, list[tuple[str, str]]] = {}
for _file_col, _db_col in _FILE_COL_TO_DB.items():
    _table_prefix = _file_col.split("_")[0].lower()   # e.g. "b01003"
    _TABLE_GROUPS.setdefault(_table_prefix, []).append((_file_col, _db_col))


class CensusAcsBulkIngestor(BaseIngestor):
    """Download ACS 5-year Summary File and load all block groups nationally.

    Downloads one ``.dat`` file per ACS table prefix found in ``ACS_VARS``
    (~23 files). Filters to block group rows (``SUMLEVEL=150``) and upserts
    into ``acs_block_group_data``.  Each table file is processed independently
    so only one file's worth of data is held in memory at a time.
    """

    source_name = "census-acs-bulk"
    update_frequency = "annual"

    def __init__(self, year: int = _DEFAULT_YEAR) -> None:
        super().__init__()
        self.year = year
        self._table_groups = _TABLE_GROUPS
        self._downloaded: list[str] = []
        self._missing: list[str] = []

    # ------------------------------------------------------------------
    # Pipeline
    # ------------------------------------------------------------------

    def download(self, region: Optional[str] = None) -> None:
        """Download one .dat file per ACS table prefix via Last-Modified caching.

        census.gov does not return ETag headers, so we use Last-Modified /
        If-Modified-Since instead of the base class ETag helper.
        """
        import httpx

        self._downloaded = []
        self._missing = []

        for table_prefix in sorted(self._table_groups):
            url = _BASE_URL.format(year=self.year, table=table_prefix)
            dest = self.staging_dir / f"acsdt5y{self.year}-{table_prefix}.dat"
            lm_file = dest.with_suffix(dest.suffix + ".lm")

            headers: dict[str, str] = {}
            if dest.exists() and lm_file.exists():
                headers["If-Modified-Since"] = lm_file.read_text().strip()

            try:
                with httpx.stream(
                    "GET", url, headers=headers, follow_redirects=True, timeout=300
                ) as response:
                    if response.status_code == 304:
                        self._log(f"Cached    {table_prefix}")
                        self._downloaded.append(table_prefix)
                        continue

                    response.raise_for_status()
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with dest.open("wb") as fh:
                        for chunk in response.iter_bytes(1024 * 1024):
                            fh.write(chunk)

                    last_modified = response.headers.get("last-modified", "")
                    if last_modified:
                        lm_file.write_text(last_modified)

                self._downloaded.append(table_prefix)
                self._log(f"Downloaded {table_prefix} ({dest.stat().st_size:,} bytes)")

            except Exception as exc:
                self._log(f"ERROR downloading {table_prefix}: {exc}")
                self._missing.append(table_prefix)

    def validate(self) -> None:
        """Verify each downloaded file has a header and at least one BG row."""
        if self._missing:
            raise ValueError(
                f"Missing table files: {', '.join(self._missing)}"
            )

        for table_prefix in self._downloaded:
            path = self.staging_dir / f"acsdt5y{self.year}-{table_prefix}.dat"
            if not path.exists():
                raise ValueError(f"Expected file not found: {path}")

            with path.open("r", encoding="utf-8") as fh:
                header = fh.readline()
                if "GEO_ID" not in header:
                    raise ValueError(
                        f"{path.name}: unexpected header — missing GEO_ID column"
                    )
                # Scan for at least one block group row (fast — first match)
                found_bg = any(
                    line.startswith(_SUMLEVEL_PREFIX) for line in fh
                )
                if not found_bg:
                    raise ValueError(
                        f"{path.name}: no block group rows found (prefix {_SUMLEVEL_PREFIX!r})"
                    )

        self._log(f"Validated {len(self._downloaded)} table files")

    def load(self) -> None:
        """Upsert block group rows table-by-table into acs_block_group_data."""
        from plinth.db.connection import get_connection

        total_rows = 0

        with get_connection() as conn:
            for table_prefix in sorted(self._downloaded):
                path = self.staging_dir / f"acsdt5y{self.year}-{table_prefix}.dat"
                columns = self._table_groups[table_prefix]  # [(file_col, db_col), ...]
                db_cols = [db_col for _, db_col in columns]

                n = self._load_table_file(conn, path, db_cols, columns)
                total_rows += n
                self._log(f"  {table_prefix}: upserted {n:,} block groups")

            conn.commit()

        self._log(f"Total: {total_rows:,} block group × table upserts")

    def register(self) -> None:
        """Register this source in data_source_registry."""
        self._upsert_registry(
            version=f"acs5-{self.year}",
            coverage_region="national",
            notes=(
                f"ACS 5-year estimates, {self.year} vintage, all block groups. "
                f"Source: Census Bureau Summary File (no API key required)."
            ),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_table_file(
        self,
        conn,
        path: Path,
        db_cols: list[str],
        file_to_db: list[tuple[str, str]],
    ) -> int:
        """Stream one .dat file and upsert its columns into acs_block_group_data.

        Uses multi-row VALUES batching for efficiency (psycopg3-compatible).
        Returns the number of block group rows processed.
        """
        col_list = ", ".join(["geoid", "acs_year"] + db_cols)
        update_set = ", ".join(
            f"{c} = EXCLUDED.{c}" for c in db_cols
        )
        ncols = 2 + len(db_cols)
        row_ph = f"({', '.join(['%s'] * ncols)})"

        # PostgreSQL allows at most 65,535 bind parameters per query.
        # Compute the max safe batch size for this table's column count.
        safe_batch_size = max(1, 65535 // ncols)

        # SQL template; values placeholder filled per-batch
        sql_tmpl = (
            f"INSERT INTO acs_block_group_data ({col_list}) VALUES {{}} "
            f"ON CONFLICT (geoid, acs_year) DO UPDATE SET {update_set}"
        )

        batch: list[tuple] = []
        total = 0

        with path.open("r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh, delimiter="|")

            for row in reader:
                geo_id = row.get("GEO_ID", "")
                if not geo_id.startswith(_SUMLEVEL_PREFIX):
                    continue

                geoid = geo_id[len(_SUMLEVEL_PREFIX):]  # 12-char GEOID

                values: list = [geoid, self.year]
                for file_col, _ in file_to_db:
                    values.append(_parse_numeric(row.get(file_col)))
                batch.append(tuple(values))

                if len(batch) >= safe_batch_size:
                    _flush_batch(conn, sql_tmpl, batch, row_ph)
                    total += len(batch)
                    batch = []

        if batch:
            _flush_batch(conn, sql_tmpl, batch, row_ph)
            total += len(batch)

        return total


def _flush_batch(conn, sql_tmpl: str, batch: list[tuple], row_ph: str) -> None:
    """Execute a multi-row VALUES INSERT for a batch of rows."""
    values_str = ", ".join([row_ph] * len(batch))
    sql = sql_tmpl.format(values_str)
    flat = [v for row in batch for v in row]
    with conn.cursor() as cur:
        cur.execute(sql, flat)


def _parse_numeric(value: Optional[str]) -> Optional[float]:
    """Parse a Census numeric value; return None for missing/special codes."""
    if value is None:
        return None
    v = value.strip()
    # Census special values: -999999999 (missing), -555555555 (not applicable),
    # -333333333 (not sampled), -222222222 (median >= threshold), etc.
    try:
        f = float(v)
        if f in (-999999999, -555555555, -333333333, -222222222, -111111111, -666666666):
            return None
        return f
    except (ValueError, TypeError):
        return None
