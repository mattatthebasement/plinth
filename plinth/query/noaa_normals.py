"""NOAA Climate Normals nearest-station query."""

from __future__ import annotations

from typing import Any

from plinth.db.connection import get_connection

_MAX_DISTANCE_MI = 50.0
_WARN_DISTANCE_MI = 15.0
_MI_TO_M = 1609.344

_MONTH_LABELS = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]


def query_noaa_normals(lat: float, lon: float) -> dict[str, Any]:
    """
    Return NOAA Climate Normals (1991–2020) from the nearest station within 50 mi.

    If the nearest station is >15 mi away, includes a distance flag.

    Returns temperature (°F), precipitation (in/month), snowfall, and
    heating/cooling degree days from the station's monthly arrays.
    """
    max_dist_m = _MAX_DISTANCE_MI * _MI_TO_M

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    station_id,
                    name,
                    elevation_m,
                    tmax, tmin, tavg, prcp, snow, htdd, cldd,
                    ST_Distance(
                        geom::geography,
                        ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
                    ) AS dist_m
                FROM noaa_climate_normals
                WHERE ST_DWithin(
                    geom::geography,
                    ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                    %s
                )
                ORDER BY
                    -- Prefer official ASOS/COOP stations (USW/USC) over CoCoRaHS (US1)
                    -- which typically lack temperature and degree-day data
                    CASE WHEN station_id LIKE 'USW%%' OR station_id LIKE 'USC%%' THEN 0 ELSE 1 END,
                    dist_m
                LIMIT 1
                """,
                (lon, lat, lon, lat, max_dist_m),
            )
            row = cur.fetchone()

    if not row:
        return {
            "available": False,
            "flag": f"No NOAA Climate Normals station within {_MAX_DISTANCE_MI} miles.",
        }

    (
        station_id, name, elevation_m,
        tmax, tmin, tavg, prcp, snow, htdd, cldd,
        dist_m,
    ) = row

    dist_mi = round(dist_m / _MI_TO_M, 1)

    def _monthly(arr: list | None) -> list[dict] | None:
        if arr is None or len(arr) < 12:
            return None
        return [
            {"month": _MONTH_LABELS[i], "value": float(arr[i]) if arr[i] is not None else None}
            for i in range(12)
        ]

    result: dict[str, Any] = {
        "available": True,
        "source": "NOAA US Climate Normals 1991–2020",
        "station_id": station_id,
        "station_name": name,
        "station_elevation_m": float(elevation_m) if elevation_m is not None else None,
        "distance_mi": dist_mi,
        "tmax_f": _monthly(tmax),
        "tmin_f": _monthly(tmin),
        "tavg_f": _monthly(tavg),
        "prcp_in": _monthly(prcp),
        "snow_in": _monthly(snow),
        "heating_degree_days": _monthly(htdd),
        "cooling_degree_days": _monthly(cldd),
    }

    if dist_mi > _WARN_DISTANCE_MI:
        result["flag"] = (
            f"Nearest NOAA station is {dist_mi} miles away. "
            "Values may not represent site microclimate."
        )

    return result
