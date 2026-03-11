"""USGS earthquake catalog query — reads from local usgs_earthquake_events table."""

from __future__ import annotations

from datetime import date
from typing import Any

from plinth.db.connection import get_connection

_DATASET = "usgs-eq"
_RADIUS_KM = 80.0   # ~50 miles
_YEARS = 50
_MIN_MAG = 3.0


def query_earthquakes(lat: float, lon: float) -> dict[str, Any]:
    """Return USGS M3+ earthquake summary within 50 mi, last 50 years, from local table."""
    start_year = date.today().year - _YEARS
    start_date = f"{start_year}-01-01"

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    event_id, magnitude, place, occurred_at,
                    ST_Z(geom) AS depth_km
                FROM usgs_earthquake_events
                WHERE magnitude >= %s
                  AND occurred_at >= %s
                  AND ST_DWithin(
                        geom::geography,
                        ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                        %s
                      )
                ORDER BY magnitude DESC
                LIMIT 1
                """,
                (_MIN_MAG, start_date, lon, lat, _RADIUS_KM * 1000),
            )
            largest_row = cur.fetchone()

            cur.execute(
                """
                SELECT COUNT(*)
                FROM usgs_earthquake_events
                WHERE magnitude >= %s
                  AND occurred_at >= %s
                  AND ST_DWithin(
                        geom::geography,
                        ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                        %s
                      )
                """,
                (_MIN_MAG, start_date, lon, lat, _RADIUS_KM * 1000),
            )
            count = cur.fetchone()[0]

    today_year = date.today().year
    note = (
        f"Events M{_MIN_MAG}+ within 50 miles, {start_year}–{today_year}. "
        "Reported count only; not a seismic risk assessment."
    )

    if count == 0:
        return {
            "available": True,
            "source": "USGS Earthquake Catalog (local bulk data)",
            "search_radius_mi": 50,
            "search_years": _YEARS,
            "min_magnitude": _MIN_MAG,
            "note": note,
            "event_count": 0,
            "max_magnitude": None,
            "largest_event": None,
        }

    event_id, mag, place, occurred_at, depth_km = largest_row
    return {
        "available": True,
        "source": "USGS Earthquake Catalog (local bulk data)",
        "search_radius_mi": 50,
        "search_years": _YEARS,
        "min_magnitude": _MIN_MAG,
        "note": note,
        "event_count": count,
        "max_magnitude": float(mag) if mag is not None else None,
        "largest_event": {
            "magnitude": float(mag) if mag is not None else None,
            "place": place,
            "time": int(occurred_at.timestamp() * 1000) if occurred_at else None,
            "depth_km": float(depth_km) if depth_km is not None else None,
        },
    }

