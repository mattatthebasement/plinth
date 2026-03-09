"""IECC climate zone point-in-polygon query."""

from __future__ import annotations

from typing import Any

from plinth.db.connection import get_connection


def query_iecc_zone(lat: float, lon: float) -> dict[str, Any]:
    """
    Return the IECC climate zone label and description for the given point.

    Returns a dict with zone_label (e.g. '3A') and zone_description.
    """
    point = f"ST_SetSRID(ST_MakePoint({lon}, {lat}), 4326)"

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT zone_label, zone_description
                FROM iecc_climate_zones
                WHERE ST_Contains(geom, {point})
                LIMIT 1
                """,
            )
            row = cur.fetchone()

    if not row:
        return {
            "available": False,
            "flag": "No IECC climate zone found for this location.",
        }

    zone_label, zone_description = row
    return {
        "available": True,
        "source": "IECC 2021 Climate Zone Map",
        "zone_label": zone_label,
        "zone_description": zone_description,
    }
