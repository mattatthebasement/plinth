"""EPA AQS air quality query — spatial nearest-monitor lookup against local bulk table."""

from __future__ import annotations

from typing import Any

from plinth.db.connection import get_connection

_DATASET = "epa-aqs"
_SEARCH_RADIUS_KM = 100.0      # look for monitors within 100 km
_FALLBACK_RADIUS_KM = 200.0    # expand to 200 km if nothing found nearby

# Parameter codes of interest
_PM25_CODE = "88101"
_OZONE_CODE = "44201"
_PARAMS = {_PM25_CODE: "pm25", _OZONE_CODE: "ozone"}


def query_epa_aqs(lat: float, lon: float, county_fips: str = "") -> dict[str, Any]:
    """Return EPA AQS annual PM2.5 and ozone summary from local bulk table.

    Finds the nearest monitor(s) within 100 km (expanding to 200 km if needed),
    then returns the most recent year's data.  Keeps the same return structure
    as the API-based client.
    """
    results: dict[str, Any] = {}
    year_used: int | None = None

    for param_code, key in _PARAMS.items():
        result = _fetch_pollutant_local(lat, lon, param_code)
        results[key] = result
        if result.get("available") and result.get("year"):
            year_used = year_used or result["year"]

    if not any(r.get("available") for r in results.values()):
        return {
            "available": False,
            "flag": "No EPA AQS monitors found within 200 km of this location.",
        }

    return {
        "available": True,
        "source": f"EPA Air Quality System (AQS) Annual Summary — Local Bulk Data",
        "note": "AQS data represents annual summaries. Not real-time AQI.",
        "year": year_used,
        "pm25": results["pm25"],
        "ozone": results["ozone"],
    }


def _fetch_pollutant_local(lat: float, lon: float, param_code: str) -> dict[str, Any]:
    """Find the nearest monitor for *param_code* and return its best annual summary."""
    for radius_km in (_SEARCH_RADIUS_KM, _FALLBACK_RADIUS_KM):
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        s.site_id, s.local_site_name, s.address,
                        a.year, a.arithmetic_mean, a.units, a.observation_count,
                        a.observation_percent, a.pollutant_standard,
                        ST_Distance(s.geom::geography,
                                    ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography) AS dist_m
                    FROM epa_aqs_sites s
                    JOIN epa_aqs_annual_summary a ON a.site_id = s.site_id
                    WHERE a.parameter_code = %s
                      AND ST_DWithin(
                            s.geom::geography,
                            ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography,
                            %s
                          )
                    ORDER BY a.year DESC, a.observation_count DESC
                    LIMIT 1
                    """,
                    (lon, lat, param_code, lon, lat, radius_km * 1000),
                )
                row = cur.fetchone()

        if row:
            site_id, site_name, address, year, mean, units, obs_count, obs_pct, standard, dist_m = row
            return {
                "available": True,
                "monitor_name": site_name or address or site_id,
                "monitor_id": site_id,
                "arithmetic_mean": float(mean) if mean is not None else None,
                "units": units,
                "observation_count": obs_count,
                "observation_pct": float(obs_pct) if obs_pct is not None else None,
                "year": year,
                "distance_km": round(dist_m / 1000, 1) if dist_m else None,
                "pollutant_standard": standard,
            }

    return {
        "available": False,
        "flag": f"No monitor data found for parameter {param_code} within {_FALLBACK_RADIUS_KM:.0f} km.",
    }

