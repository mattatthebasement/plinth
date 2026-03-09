"""FEMA flood zone point-in-polygon query."""

from __future__ import annotations

from typing import Any

from plinth.db.connection import get_connection


def query_flood_zone(lat: float, lon: float) -> dict[str, Any]:
    """
    Return FEMA flood zone classification for the given point.

    Checks fema_flood_zones first. Falls back to fema_unmapped_areas to
    distinguish explicitly unmapped areas from missing data entirely.

    Returns a dict with:
      available (bool), zone, zone_subty, sfha (bool), bfe_ft,
      source_date, mapped (bool), flag (str if applicable)
    """
    point = f"ST_SetSRID(ST_MakePoint({lon}, {lat}), 4326)"

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    fld_zone,
                    zone_subty,
                    sfha_tf,
                    bfe_revert,
                    static_bfe,
                    source_date
                FROM fema_flood_zones
                WHERE ST_Contains(geom, {point})
                ORDER BY
                    -- Prefer SFHA zones (higher priority) over Zone X
                    CASE WHEN sfha_tf = 'T' THEN 0 ELSE 1 END,
                    source_date DESC NULLS LAST
                LIMIT 1
                """,
            )
            row = cur.fetchone()

    if row:
        zone, subty, sfha_tf, bfe_revert, static_bfe, source_date = row
        bfe = static_bfe if static_bfe is not None else bfe_revert
        return {
            "available": True,
            "mapped": True,
            "source": "FEMA National Flood Hazard Layer (NFHL)",
            "zone": zone,
            "zone_subty": subty,
            "sfha": sfha_tf == "T",
            "bfe_ft": float(bfe) if bfe is not None else None,
            "source_date": source_date.isoformat() if source_date else None,
        }

    # No flood zone polygon — check unmapped areas
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT county_fips FROM fema_unmapped_areas
                WHERE ST_Contains(geom, {point})
                LIMIT 1
                """,
            )
            unmapped_row = cur.fetchone()

    if unmapped_row:
        return {
            "available": True,
            "mapped": False,
            "source": "FEMA National Flood Hazard Layer (NFHL)",
            "zone": None,
            "flag": (
                "This area has not been mapped by FEMA. Flood risk is unknown. "
                "Approximately 15–20% of the US lacks FEMA flood mapping."
            ),
        }

    # Point falls outside all known FEMA coverage (offshore, outside US, etc.)
    return {
        "available": False,
        "mapped": False,
        "flag": "No FEMA flood data found for this location.",
    }
