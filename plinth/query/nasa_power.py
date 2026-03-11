"""NASA POWER climatology query — reads from local nasa_power_climatology table."""

from __future__ import annotations

import math
from typing import Any

from plinth.db.connection import get_connection

_DATASET = "nasa-power"

# DB column → output key mapping (matches the API client's return structure)
_COL_TO_KEY = {
    "t2m_mean_c":          "t2m",
    "t2m_max_c":           "t2m_max",
    "t2m_min_c":           "t2m_min",
    "t2mdew_c":            "t2m_dew",
    "prectotcorr_mm_day":  "precip_mm_day",
    "allsky_sfc_sw_dwn":   "solar_kwh_m2_day",
    "allsky_kt":           "solar_clearness",
    "ws10m_m_s":           "wind_speed_10m",
    "rh2m_pct":            "rel_humidity",
    "hdd18_3":             "hdd_18_3c",
    "cdd18_3":             "cdd_18_3c",
}


def query_nasa_power(lat: float, lon: float) -> dict[str, Any]:
    """Return NASA POWER monthly climatology from the local bulk table.

    Snaps the query point to the nearest stored grid cell, then assembles
    the same ``{annual, monthly: [jan..dec]}`` structure as the API client.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            # Find the nearest grid cell
            cur.execute(
                """
                SELECT grid_lat, grid_lon
                FROM nasa_power_climatology
                WHERE month = 0
                ORDER BY ABS(grid_lat - %s) + ABS(grid_lon - %s)
                LIMIT 1
                """,
                (lat, lon),
            )
            nearest = cur.fetchone()

    if nearest is None:
        return {"available": False, "flag": "NASA POWER climatology data not loaded."}

    grid_lat, grid_lon = float(nearest[0]), float(nearest[1])

    # Pull all 13 months (0=annual, 1-12=monthly) for this cell
    cols = ", ".join(_COL_TO_KEY.keys())
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT month, {cols} FROM nasa_power_climatology "
                "WHERE grid_lat = %s AND grid_lon = %s "
                "ORDER BY month",
                (grid_lat, grid_lon),
            )
            rows = cur.fetchall()

    if not rows:
        return {"available": False, "flag": "NASA POWER data missing for nearest grid cell."}

    # Index by month: 0=annual, 1..12=Jan..Dec
    by_month: dict[int, dict] = {}
    for row in rows:
        month = row[0]
        by_month[month] = dict(zip(_COL_TO_KEY.keys(), row[1:]))

    def _extract(db_col: str) -> dict:
        annual_val = by_month.get(0, {}).get(db_col)
        monthly = [
            float(by_month[m][db_col]) if by_month.get(m, {}).get(db_col) is not None else None
            for m in range(1, 13)
        ]
        return {
            "annual": float(annual_val) if annual_val is not None else None,
            "monthly": monthly,
        }

    result: dict[str, Any] = {
        "available": True,
        "source": "NASA POWER Climatology 2001-2020 (local bulk data)",
        "grid_lat": grid_lat,
        "grid_lon": grid_lon,
    }
    for db_col, out_key in _COL_TO_KEY.items():
        result[out_key] = _extract(db_col)

    return result

