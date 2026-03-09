"""USDA SSURGO soil map unit point-in-polygon query."""

from __future__ import annotations

from typing import Any

from plinth.db.connection import get_connection

# Gap thresholds for nearest-unit fallback
_NEAR_GAP_M = 200    # Small gap — likely road or creek edge; data still representative
_FAR_GAP_M = 500     # Larger gap — data may not represent actual site soils
_MAX_GAP_M = 500     # Beyond this, return unavailable rather than a distant proxy


def query_soil(lat: float, lon: float) -> dict[str, Any]:
    """
    Return soil map unit data for the given point from SSURGO.

    Joins ssurgo_mapunits → ssurgo_muaggatt (aggregate attributes) →
    ssurgo_component (dominant component by comppct_r).

    Gap handling:
    - Point inside a polygon: exact match, no flag.
    - Gap < 200 m: nearest unit returned with minor flag (road/creek edge).
    - Gap 200–500 m: nearest unit returned with prominent distance warning.
    - Gap > 500 m: returns unavailable — site is in a developed/urban area
      not covered by SSURGO county-level mapping.
    """
    geo_point = f"ST_SetSRID(ST_MakePoint({lon}, {lat}), 4326)::geography"
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
                    0.0 AS gap_m
                FROM ssurgo_mapunits m
                LEFT JOIN ssurgo_muaggatt a ON a.mukey = m.mukey
                WHERE ST_Contains(m.geom, {point})
                LIMIT 1
                """,
            )
            row = cur.fetchone()

    if not row:
        # Coverage gap — find nearest unit and measure exact distance
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
                        ST_Distance(m.geom::geography, {geo_point}) AS gap_m
                    FROM ssurgo_mapunits m
                    LEFT JOIN ssurgo_muaggatt a ON a.mukey = m.mukey
                    WHERE ST_DWithin(m.geom::geography, {geo_point}, {_MAX_GAP_M})
                    ORDER BY gap_m
                    LIMIT 1
                    """,
                )
                row = cur.fetchone()

    if not row:
        return {
            "available": False,
            "flag": (
                "No SSURGO soil data within 500 m of this location. The site is likely "
                "in a developed or urban area not covered by county-level SSURGO mapping. "
                "Consult a licensed soil scientist or geotechnical engineer for "
                "site-specific soil characterization."
            ),
        }

    mukey, musym, muname, hydgrpdcd, drclassdcd, slopegraddcp, taxclname, gap_m = row

    # Beyond max gap — refuse to return a distant proxy
    if gap_m > _MAX_GAP_M:
        return {
            "available": False,
            "flag": (
                f"Nearest SSURGO map unit is {gap_m:.0f} m away. The site is likely in a "
                "developed or urban area not covered by county-level SSURGO mapping. "
                "Consult a licensed soil scientist or geotechnical engineer for "
                "site-specific soil characterization."
            ),
        }

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
        "gap_m": round(gap_m, 0) if gap_m > 0 else None,
    }

    if 0 < gap_m <= _NEAR_GAP_M:
        result["flag"] = (
            f"Point falls in a small SSURGO coverage gap ({gap_m:.0f} m — likely a road, "
            "water body, or parcel edge). Nearest map unit returned; values are likely "
            "representative of on-site conditions."
        )
    elif gap_m > _NEAR_GAP_M:
        result["flag"] = (
            f"Point is {gap_m:.0f} m from the nearest SSURGO map unit. The site may be "
            "in a developed or disturbed area. Soil data shown is from the nearest mapped "
            "unit and may not represent actual on-site conditions. Verify with USDA Web "
            "Soil Survey or a licensed soil scientist."
        )

    return result

