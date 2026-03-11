"""NASA POWER climatology query — reads from local nasa_power_climatology table.

The bulk ingestor fetches met parameters (community=SB, MERRA-2 0.5°×0.625° grid)
and solar parameters (SRB/CERES 1°×1° grid) separately. They land in different rows
in the table, so the query does two nearest-cell lookups: one for met, one for solar.

Solar values are stored in W/m² (24-hour mean) and are converted to kWh/m²/day
(multiply by 24/1000) to match the expected output format.
"""

from __future__ import annotations

import math
from typing import Any

from plinth.db.connection import get_connection

_DATASET = "nasa-power"

# Met columns — found on the MERRA-2 0.5°×0.625° grid cells
_MET_COLS = {
    "t2m_mean_c":          "t2m",
    "t2m_max_c":           "t2m_max",
    "t2m_min_c":           "t2m_min",
    "t2mdew_c":            "t2m_dew",
    "prectotcorr_mm_day":  "precip_mm_day",
    "ws10m_m_s":           "wind_speed_10m",
    "rh2m_pct":            "rel_humidity",
    "hdd18_3":             "hdd_18_3c",
    "cdd18_3":             "cdd_18_3c",
}

# Solar columns — found on the SRB/CERES 1°×1° grid cells (different rows)
# Values in DB are W/m² (24-hour mean); multiply by 24/1000 → kWh/m²/day
_SOLAR_COLS = {
    "allsky_sfc_sw_dwn":   "solar_kwh_m2_day",
    "allsky_kt":           "solar_clearness",
}
_W_TO_KWH = 24.0 / 1000.0  # W/m² 24h-mean → kWh/m²/day


def _nearest_cell(cur, lat: float, lon: float, not_null_col: str | None = None) -> tuple[float, float] | None:
    """Return (grid_lat, grid_lon) of the nearest cell, optionally requiring a column to be non-null."""
    where = f"WHERE month = 0{f' AND {not_null_col} IS NOT NULL' if not_null_col else ''}"
    cur.execute(
        f"SELECT grid_lat, grid_lon FROM nasa_power_climatology "
        f"{where} ORDER BY ABS(grid_lat - %s) + ABS(grid_lon - %s) LIMIT 1",
        (lat, lon),
    )
    row = cur.fetchone()
    return (float(row[0]), float(row[1])) if row else None


def _fetch_months(cur, grid_lat: float, grid_lon: float, cols: dict[str, str]) -> dict[int, dict]:
    """Return {month: {db_col: value}} for all 13 months at the given cell."""
    col_list = ", ".join(cols.keys())
    cur.execute(
        f"SELECT month, {col_list} FROM nasa_power_climatology "
        "WHERE grid_lat = %s AND grid_lon = %s ORDER BY month",
        (grid_lat, grid_lon),
    )
    rows = cur.fetchall()
    return {row[0]: dict(zip(cols.keys(), row[1:])) for row in rows}


def _extract(by_month: dict[int, dict], db_col: str, scale: float = 1.0) -> dict:
    """Build {annual, monthly} dict for one column, applying optional unit scale."""
    annual_val = by_month.get(0, {}).get(db_col)
    monthly = [
        round(float(by_month[m][db_col]) * scale, 4)
        if by_month.get(m, {}).get(db_col) is not None else None
        for m in range(1, 13)
    ]
    return {
        "annual": round(float(annual_val) * scale, 4) if annual_val is not None else None,
        "monthly": monthly,
    }


def query_nasa_power(lat: float, lon: float) -> dict[str, Any]:
    """Return NASA POWER monthly climatology from the local bulk table.

    Performs two nearest-cell snaps: one for met parameters (MERRA-2 grid)
    and one for solar parameters (SRB/CERES grid), then merges results.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            met_cell = _nearest_cell(cur, lat, lon)
            solar_cell = _nearest_cell(cur, lat, lon, not_null_col="allsky_sfc_sw_dwn")

    if met_cell is None:
        return {"available": False, "flag": "NASA POWER climatology data not loaded."}

    with get_connection() as conn:
        with conn.cursor() as cur:
            met_by_month = _fetch_months(cur, *met_cell, _MET_COLS)
            solar_by_month = _fetch_months(cur, *solar_cell, _SOLAR_COLS) if solar_cell else {}

    if not met_by_month:
        return {"available": False, "flag": "NASA POWER data missing for nearest grid cell."}

    result: dict[str, Any] = {
        "available": True,
        "source": "NASA POWER Climatology 2001-2020 (local bulk data)",
        "grid_lat": met_cell[0],
        "grid_lon": met_cell[1],
    }

    for db_col, out_key in _MET_COLS.items():
        result[out_key] = _extract(met_by_month, db_col)

    for db_col, out_key in _SOLAR_COLS.items():
        scale = _W_TO_KWH if out_key == "solar_kwh_m2_day" else 1.0
        result[out_key] = _extract(solar_by_month, db_col, scale=scale)

    return result

