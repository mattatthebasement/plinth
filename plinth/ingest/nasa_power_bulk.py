"""NASA POWER regional climatology bulk ingestor.

Makes 15 regional API calls (one per parameter) covering the NE Oklahoma
bounding box. Caches each response as a staging CSV. Stores one row per
grid cell × month in nasa_power_climatology.

Source: https://power.larc.nasa.gov/api/temporal/climatology/regional
Coverage: 20-year climatology 2001–2020 (pre-computed, does not change)
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

from plinth.ingest.base import BaseIngestor

_BASE_URL = "https://power.larc.nasa.gov/api/temporal/climatology/regional"
_DATASET = "nasa-power-bulk"

# NE Oklahoma bounding box with 0.5° buffer
_DEFAULT_BBOX = {
    "lat_min": 35.0,
    "lat_max": 37.5,
    "lon_min": -97.5,
    "lon_max": -94.0,
}

# API parameter name → DB column name
_PARAMS: dict[str, str] = {
    "T2M":               "t2m_mean_c",
    "T2M_MAX":           "t2m_max_c",
    "T2M_MIN":           "t2m_min_c",
    "T2MDEW":            "t2mdew_c",
    "PRECTOTCORR":       "prectotcorr_mm_day",
    "ALLSKY_SFC_SW_DWN": "allsky_sfc_sw_dwn",
    "ALLSKY_KT":         "allsky_kt",
    "WS10M":             "ws10m_m_s",
    "RH2M":              "rh2m_pct",
    "HDD18_3":           "hdd18_3",
    "CDD18_3":           "cdd18_3",
    "WS50M":             "ws50m_m_s",
    "ALLSKY_SFC_LW_DWN": "allsky_sfc_lw_dwn",
    "CLRSKY_SFC_SW_DWN": "clrsky_sfc_sw_dwn",
    "T2MWET":            "t2mwet_c",
}

# CSV header columns → month index (0 = annual)
_MONTH_COLS = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4,
    "MAY": 5, "JUN": 6, "JUL": 7, "AUG": 8,
    "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
    "ANN": 0,
}

_POWER_MISSING = -999.0


def _floatnull(val: str) -> float | None:
    if not val or not val.strip():
        return None
    try:
        f = float(val.strip())
        return None if f == _POWER_MISSING else f
    except ValueError:
        return None


class NasaPowerBulkIngestor(BaseIngestor):
    """Ingestor for NASA POWER 20-year monthly climatology.

    Fetches all 15 parameters for the NE Oklahoma bounding box via the
    regional climatology API (1 call per parameter). Responses are cached
    as CSV files in staging_dir so subsequent runs skip the API calls.
    """

    source_name = _DATASET
    update_frequency = "decadal"

    def __init__(self, bbox: dict | None = None) -> None:
        super().__init__()
        self.bbox = bbox or _DEFAULT_BBOX

    # ------------------------------------------------------------------
    # Pipeline steps
    # ------------------------------------------------------------------

    def download(self, region=None) -> None:
        import httpx

        for api_param in _PARAMS:
            dest = self.staging_dir / f"nasa_power_{api_param}.csv"
            if dest.exists() and dest.stat().st_size > 0:
                self._log(f"Skipped {api_param} (cached)")
                continue

            url = (
                f"{_BASE_URL}"
                f"?latitude-min={self.bbox['lat_min']}"
                f"&latitude-max={self.bbox['lat_max']}"
                f"&longitude-min={self.bbox['lon_min']}"
                f"&longitude-max={self.bbox['lon_max']}"
                f"&parameters={api_param}"
                f"&community=SB&format=CSV&header=true"
            )
            resp = httpx.get(url, timeout=60, follow_redirects=True)
            resp.raise_for_status()
            body = resp.text
            if "failed" in body[:200].lower():
                raise RuntimeError(f"NASA POWER rejected {api_param}: {body[:200]}")
            dest.write_text(body, encoding="utf-8")
            rows = sum(1 for ln in body.splitlines() if ln and not ln.startswith("-") and not ln.startswith("PARAMETER"))
            self._log(f"Downloaded {api_param} ({rows} grid-cell rows)")

    def validate(self) -> None:
        for api_param in _PARAMS:
            dest = self.staging_dir / f"nasa_power_{api_param}.csv"
            if not dest.exists() or dest.stat().st_size == 0:
                raise FileNotFoundError(f"Missing staging file for {api_param}: {dest}")
            text = dest.read_text(encoding="utf-8")
            if "-END HEADER-" not in text:
                raise ValueError(f"Unexpected format in {dest.name}: missing END HEADER marker")
        self._log(f"Validated {len(_PARAMS)} parameter files")

    def load(self) -> None:
        from plinth.db.connection import get_connection

        # Accumulate all parameter values keyed by (lat, lon, month)
        # Structure: {(lat, lon, month): {db_col: value}}
        cells: dict[tuple, dict[str, float | None]] = {}

        for api_param, db_col in _PARAMS.items():
            dest = self.staging_dir / f"nasa_power_{api_param}.csv"
            text = dest.read_text(encoding="utf-8")
            self._parse_parameter(text, db_col, cells)

        self._log(f"Parsed {len(cells):,} (lat, lon, month) cells across {len(_PARAMS)} parameters")

        with get_connection() as conn:
            _upsert_cells(conn, cells)

        self._log(f"Upserted {len(cells):,} rows into nasa_power_climatology")

    def register(self) -> None:
        bbox = self.bbox
        region = (
            f"lat {bbox['lat_min']}–{bbox['lat_max']}°N, "
            f"lon {bbox['lon_min']}–{bbox['lon_max']}°W"
        )
        self._upsert_registry(
            version="MERRA-2 Climatology 2001–2020",
            coverage_region=region,
            notes=(
                f"NASA POWER regional climatology API — {len(_PARAMS)} parameters, "
                "20-year monthly averages (2001–2020). Pre-computed; does not change."
            ),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_parameter(
        text: str,
        db_col: str,
        cells: dict[tuple, dict[str, float | None]],
    ) -> None:
        """Parse a single-parameter NASA POWER CSV response into *cells*."""
        in_data = False
        reader_lines: list[str] = []

        for line in text.splitlines():
            if line.startswith("-END HEADER-"):
                in_data = True
                continue
            if in_data and line.strip():
                reader_lines.append(line)

        if not reader_lines:
            return

        reader = csv.DictReader(io.StringIO("\n".join(reader_lines)))
        for row in reader:
            lat = float(row["LAT"])
            lon = float(row["LON"])
            for month_col, month_idx in _MONTH_COLS.items():
                key = (lat, lon, month_idx)
                if key not in cells:
                    cells[key] = {}
                cells[key][db_col] = _floatnull(row.get(month_col, ""))


def _upsert_cells(conn, cells: dict[tuple, dict[str, float | None]]) -> None:
    """Upsert all (lat, lon, month) cells into nasa_power_climatology."""
    all_cols = list(_PARAMS.values())
    col_list = "grid_lat, grid_lon, month, " + ", ".join(all_cols)
    update_set = ", ".join(
        f"{c} = EXCLUDED.{c}" for c in all_cols
    )
    ncols = 3 + len(all_cols)
    row_ph = f"({', '.join(['%s'] * ncols)})"
    safe_batch = max(1, 65535 // ncols)

    sql = (
        f"INSERT INTO nasa_power_climatology ({col_list}) VALUES {{}} "
        f"ON CONFLICT (grid_lat, grid_lon, month) DO UPDATE SET {update_set}"
    )

    rows = list(cells.items())
    for i in range(0, len(rows), safe_batch):
        chunk = rows[i : i + safe_batch]
        placeholders = ", ".join(row_ph for _ in chunk)
        flat: list = []
        for (lat, lon, month), vals in chunk:
            flat += [lat, lon, month] + [vals.get(c) for c in all_cols]
        with conn.cursor() as cur:
            cur.execute(sql.format(placeholders), flat)
    conn.commit()
