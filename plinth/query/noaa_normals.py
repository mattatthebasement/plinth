"""NOAA Climate Normals nearest-station query."""

from __future__ import annotations

import math
from typing import Any

from plinth.db.connection import get_connection

_MAX_DISTANCE_MI = 50.0
_MAX_SNOW_DISTANCE_MI = 15.0
_WARN_DISTANCE_MI = 15.0
_WARN_SNOW_DISTANCE_MI = 10.0
_MI_TO_M = 1609.344

_MONTH_LABELS = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]

_COMPASS_16 = [
    "N", "NNE", "NE", "ENE",
    "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW",
    "W", "WNW", "NW", "NNW",
]


def _bearing_direction(site_lat: float, site_lon: float,
                       stn_lat: float, stn_lon: float) -> str:
    """Return the 16-point compass direction FROM the site TO the station."""
    lat1 = math.radians(site_lat)
    lat2 = math.radians(stn_lat)
    d_lon = math.radians(stn_lon - site_lon)
    x = math.sin(d_lon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(d_lon)
    bearing = (math.degrees(math.atan2(x, y)) + 360) % 360
    idx = round(bearing / 22.5) % 16
    return _COMPASS_16[idx]


def _monthly(arr: list | None) -> list[dict] | None:
    if arr is None or len(arr) < 12:
        return None
    return [
        {"month": _MONTH_LABELS[i], "value": float(arr[i]) if arr[i] is not None else None}
        for i in range(12)
    ]


def _has_data(arr: list | None) -> bool:
    """Return True if the array has at least one non-null value greater than zero."""
    if not arr:
        return False
    return any(v is not None and v > 0 for v in arr)


def _fetch_station(lat: float, lon: float, require_snow: bool = False,
                   exclude_station_id: str | None = None,
                   max_dist_mi: float | None = None) -> dict | None:
    """
    Find the nearest NOAA station that has HDD, CDD, tmax, and tmin data.

    If require_snow=True, the station must have at least one monthly snow value > 0.
    If exclude_station_id is given, that station is skipped.
    max_dist_mi defaults to _MAX_DISTANCE_MI (50 mi) or _MAX_SNOW_DISTANCE_MI for snow.

    Prefers official ASOS/COOP stations (USW/USC prefix) over CoCoRaHS (US1).
    Returns a raw dict of station fields, or None if not found.
    """
    if max_dist_mi is None:
        max_dist_mi = _MAX_DISTANCE_MI
    max_dist_m = max_dist_mi * _MI_TO_M

    # For snow, require at least one array element > 0 (not just non-null)
    snow_filter = (
        "AND snow IS NOT NULL "
        "AND (SELECT MAX(v::numeric) FROM unnest(snow) AS t(v)) > 0"
    ) if require_snow else ""

    exclude_filter = "AND station_id != %s" if exclude_station_id else ""

    params: list = [lon, lat, lon, lat, max_dist_m]
    if exclude_station_id:
        params.append(exclude_station_id)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    station_id,
                    name,
                    elevation_m,
                    tmax, tmin, tavg, prcp, snow, htdd, cldd,
                    ST_Distance(
                        geom::geography,
                        ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
                    ) AS dist_m,
                    ST_Y(geom) AS stn_lat,
                    ST_X(geom) AS stn_lon
                FROM noaa_climate_normals
                WHERE ST_DWithin(
                    geom::geography,
                    ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                    %s
                )
                  AND htdd IS NOT NULL
                  AND cldd IS NOT NULL
                  AND tmax IS NOT NULL
                  AND tmin IS NOT NULL
                  {snow_filter}
                  {exclude_filter}
                ORDER BY
                    CASE WHEN station_id LIKE 'USW%%' OR station_id LIKE 'USC%%' THEN 0 ELSE 1 END,
                    dist_m
                LIMIT 1
                """,
                params,
            )
            row = cur.fetchone()

    if not row:
        return None

    (
        station_id, name, elevation_m,
        tmax, tmin, tavg, prcp, snow, htdd, cldd,
        dist_m, stn_lat, stn_lon,
    ) = row

    dist_mi = round(dist_m / _MI_TO_M, 1)
    bearing = _bearing_direction(lat, lon, float(stn_lat), float(stn_lon))

    return {
        "station_id": station_id,
        "station_name": name,
        "station_elevation_m": float(elevation_m) if elevation_m is not None else None,
        "distance_mi": dist_mi,
        "bearing_dir": bearing,
        "tmax": tmax,
        "tmin": tmin,
        "tavg": tavg,
        "prcp": prcp,
        "snow": snow,
        "htdd": htdd,
        "cldd": cldd,
    }


def query_noaa_normals(lat: float, lon: float) -> dict[str, Any]:
    """
    Return NOAA Climate Normals (1991–2020) from the nearest qualifying station.

    Primary station must have HDD, CDD, tmax, and tmin data (required for
    degree-day and freeze-thaw calculations). If that station lacks snowfall
    data, a separate nearest station with snow data is found for the snow row.

    Returns temperature (°F), precipitation (in/month), snowfall, and
    heating/cooling degree days. When two stations are used, both are included
    in the result for display in the report.
    """
    primary = _fetch_station(lat, lon, require_snow=False)

    if not primary:
        return {
            "available": False,
            "flag": f"No qualifying NOAA Climate Normals station within {_MAX_DISTANCE_MI} miles.",
        }

    # Check whether the primary station has usable snowfall data (at least one month > 0)
    primary_has_snow = _has_data(primary["snow"])

    snow_station: dict | None = None
    if not primary_has_snow:
        snow_station = _fetch_station(
            lat, lon,
            require_snow=True,
            exclude_station_id=primary["station_id"],
            max_dist_mi=_MAX_SNOW_DISTANCE_MI,
        )

    result: dict[str, Any] = {
        "available": True,
        "source": "NOAA US Climate Normals 1991–2020",
        "station_id": primary["station_id"],
        "station_name": primary["station_name"],
        "station_elevation_m": primary["station_elevation_m"],
        "distance_mi": primary["distance_mi"],
        "bearing_dir": primary["bearing_dir"],
        "tmax_f": _monthly(primary["tmax"]),
        "tmin_f": _monthly(primary["tmin"]),
        "tavg_f": _monthly(primary["tavg"]),
        "prcp_in": _monthly(primary["prcp"]),
        "heating_degree_days": _monthly(primary["htdd"]),
        "cooling_degree_days": _monthly(primary["cldd"]),
    }

    if snow_station:
        result["snow_in"] = _monthly(snow_station["snow"])
        result["snow_station_id"] = snow_station["station_id"]
        result["snow_station_name"] = snow_station["station_name"]
        result["snow_distance_mi"] = snow_station["distance_mi"]
        result["snow_bearing_dir"] = snow_station["bearing_dir"]
        result["snow_distance_warn"] = snow_station["distance_mi"] > _WARN_SNOW_DISTANCE_MI
    elif primary_has_snow:
        result["snow_in"] = _monthly(primary["snow"])
        result["snow_distance_warn"] = False
    else:
        # No usable snowfall data within range — omit the snow row
        result["snow_in"] = None
        result["snow_distance_warn"] = False

    if primary["distance_mi"] > _WARN_DISTANCE_MI:
        result["flag"] = (
            f"Nearest NOAA station is {primary['distance_mi']} miles away. "
            "Values may not represent site microclimate."
        )

    return result
