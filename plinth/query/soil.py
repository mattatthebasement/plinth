"""USDA SSURGO soil map unit point-in-polygon query."""

from __future__ import annotations

from typing import Any

from plinth.db.connection import get_connection


def query_soil(lat: float, lon: float) -> dict[str, Any]:
    """
    Return soil map unit data for the given point from SSURGO.

    Joins ssurgo_mapunits → ssurgo_muaggatt (aggregate attributes) →
    ssurgo_component (dominant component by comppct_r).

    If the point falls in a coverage gap (roads, water, unmapped areas),
    falls back to the nearest map unit within 500 m.

    Returns map unit key/name, hydrologic group, drainage class, slope,
    taxonomic classification, and the dominant component name.
    """
    point = f"ST_SetSRID(ST_MakePoint({lon}, {lat}), 4326)"

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    m.mukey,
                    m.musym,
                    m.muname,
                    a.hydgrpdcd,
                    a.drclassdcd,
                    a.slopegraddcp,
                    a.taxclname,
                    false AS is_nearest
                FROM ssurgo_mapunits m
                LEFT JOIN ssurgo_muaggatt a ON a.mukey = m.mukey
                WHERE ST_Contains(m.geom, {point})
                LIMIT 1
                """,
            )
            row = cur.fetchone()

    if not row:
        # Coverage gap (road, water, etc.) — fall back to nearest unit within 500 m
        # ~0.0045 degrees at mid-latitudes
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT
                        m.mukey,
                        m.musym,
                        m.muname,
                        a.hydgrpdcd,
                        a.drclassdcd,
                        a.slopegraddcp,
                        a.taxclname,
                        true AS is_nearest
                    FROM ssurgo_mapunits m
                    LEFT JOIN ssurgo_muaggatt a ON a.mukey = m.mukey
                    WHERE ST_DWithin(m.geom, {point}, 0.015)
                    ORDER BY ST_Distance(m.geom, {point})
                    LIMIT 1
                    """,
                )
                row = cur.fetchone()

    if not row:
        return {
            "available": False,
            "flag": "No SSURGO soil map unit found for this location.",
        }

    mukey, musym, muname, hydgrpdcd, drclassdcd, slopegraddcp, taxclname, is_nearest = row

    # Fetch the dominant component (highest comppct_r)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT compname, comppct_r, majcompflag
                FROM ssurgo_component
                WHERE mukey = %s
                ORDER BY comppct_r DESC NULLS LAST
                LIMIT 5
                """,
                (mukey,),
            )
            components = cur.fetchall()

    dominant = components[0] if components else (None, None, None)

    result: dict[str, Any] = {
        "available": True,
        "source": "USDA NRCS SSURGO",
        "mukey": mukey,
        "musym": musym,
        "muname": muname,
        "hydrologic_group": hydgrpdcd,
        "drainage_class": drclassdcd,
        "slope_pct": float(slopegraddcp) if slopegraddcp is not None else None,
        "taxonomic_class": taxclname,
        "dominant_component": dominant[0],
        "dominant_component_pct": float(dominant[1]) if dominant[1] is not None else None,
        "components": [
            {
                "name": c[0],
                "pct": float(c[1]) if c[1] is not None else None,
                "major": c[2] == "Yes",
            }
            for c in components
        ],
    }

    if is_nearest:
        result["flag"] = (
            "Point falls in a SSURGO coverage gap (road, water, or unmapped area). "
            "Nearest map unit returned."
        )

    return result
