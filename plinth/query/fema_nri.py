"""FEMA National Risk Index (NRI) tract-level query."""

from __future__ import annotations

from typing import Any

from plinth.db.connection import get_connection

_NRI_HAZARDS = [
    ("avln_score", "Avalanche"),
    ("cfld_score", "Coastal Flooding"),
    ("cwav_score", "Cold Wave"),
    ("drgt_score", "Drought"),
    ("erqk_score", "Earthquake"),
    ("hail_score", "Hail"),
    ("hwav_score", "Heat Wave"),
    ("hrcn_score", "Hurricane"),
    ("istm_score", "Ice Storm"),
    ("lnds_score", "Landslide"),
    ("ltng_score", "Lightning"),
    ("rfld_score", "Riverine Flooding"),
    ("swnd_score", "Strong Wind"),
    ("trnd_score", "Tornado"),
    ("tsun_score", "Tsunami"),
    ("vlcn_score", "Volcanic Activity"),
    ("wfir_score", "Wildfire"),
    ("wntw_score", "Winter Weather"),
]


def query_fema_nri(lat: float, lon: float) -> dict[str, Any]:
    """
    Return FEMA NRI risk scores for the Census tract containing the point.

    NRI scores are FEMA's composite model values — presented as-is with
    attribution. No risk rating or suitability determination is derived.

    Returns a dict with tract_id, composite risk_score, risk_ratng,
    and individual hazard scores keyed by hazard name.
    """
    point = f"ST_SetSRID(ST_MakePoint({lon}, {lat}), 4326)"

    with get_connection() as conn:
        with conn.cursor() as cur:
            # Find the census tract containing the point
            cur.execute(
                f"""
                SELECT t.geoid
                FROM census_tracts t
                WHERE ST_Contains(t.geom, {point})
                LIMIT 1
                """,
            )
            tract_row = cur.fetchone()

    if not tract_row:
        return {
            "available": False,
            "flag": "No Census tract found for this location.",
        }

    tract_geoid = tract_row[0]

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    tract_id, risk_score, risk_ratng,
                    avln_score, cfld_score, cwav_score, drgt_score,
                    erqk_score, hail_score, hwav_score, hrcn_score,
                    istm_score, lnds_score, ltng_score, rfld_score,
                    swnd_score, trnd_score, tsun_score, vlcn_score,
                    wfir_score, wntw_score
                FROM fema_nri
                WHERE tract_id = %s
                """,
                (tract_geoid,),
            )
            nri_row = cur.fetchone()

    if not nri_row:
        return {
            "available": False,
            "tract_id": tract_geoid,
            "flag": "Census tract found but no FEMA NRI data for this tract.",
        }

    (
        tract_id, risk_score, risk_ratng,
        *hazard_scores
    ) = nri_row

    hazards = {
        label: (float(val) if val is not None else None)
        for (col, label), val in zip(_NRI_HAZARDS, hazard_scores)
    }

    return {
        "available": True,
        "source": "FEMA National Risk Index",
        "citation": (
            "FEMA National Risk Index composite scores. Scores reflect FEMA's model "
            "combining hazard frequency, exposure, and community resilience. "
            "Source: FEMA National Risk Index — not a derived risk rating."
        ),
        "tract_id": tract_id,
        "risk_score": float(risk_score) if risk_score is not None else None,
        "risk_ratng": risk_ratng,
        "hazard_scores": hazards,
    }
