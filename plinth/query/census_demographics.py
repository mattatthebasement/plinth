"""Census block group area-weighted intersection query.

Returns block group GEOIDs and their area-weighted fractions at 1-, 5-,
and 10-mile straight-line radius buffers around a point. Used as input to
Census ACS demographic lookups at report generation time.
"""

from __future__ import annotations

from typing import Any

from plinth.db.connection import get_connection

_RADII_MI = [1, 5, 10]
_MI_TO_M = 1609.344


def query_census_block_groups(
    lat: float,
    lon: float,
    radii_mi: list[int] | None = None,
) -> dict[str, Any]:
    """
    Return area-weighted Census block group fractions for each radius buffer.

    Uses PostGIS geography type for geodesic accuracy. Each block group entry
    includes geoid, state/county FIPS, and the fraction of its area that falls
    within the buffer (intersection_pct).

    Args:
        lat: Latitude (WGS84)
        lon: Longitude (WGS84)
        radii_mi: Buffer radii in miles. Defaults to [1, 5, 10].

    Returns:
        dict keyed by radius label (e.g. '1mi') with list of block groups.
    """
    if radii_mi is None:
        radii_mi = _RADII_MI

    result: dict[str, Any] = {
        "available": True,
        "source": "US Census TIGER/Line Block Groups",
        "note": "Buffers are straight-line (Euclidean) radii, not drive-time.",
        "radii": {},
    }

    for radius_mi in radii_mi:
        radius_m = radius_mi * _MI_TO_M
        label = f"{radius_mi}mi"

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    WITH buffer AS (
                        SELECT ST_Buffer(
                            ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                            %s
                        )::geometry AS geom
                    ),
                    intersections AS (
                        SELECT
                            bg.geoid,
                            bg.statefp,
                            bg.countyfp,
                            ST_Area(ST_Intersection(bg.geom::geography, b.geom::geography)) AS intersection_area,
                            ST_Area(bg.geom::geography) AS bg_area
                        FROM census_block_groups bg, buffer b
                        WHERE ST_Intersects(bg.geom, b.geom)
                    )
                    SELECT
                        geoid,
                        statefp,
                        countyfp,
                        ROUND((intersection_area / NULLIF(bg_area, 0) * 100)::numeric, 2) AS intersection_pct
                    FROM intersections
                    ORDER BY intersection_pct DESC
                    """,
                    (lon, lat, radius_m),
                )
                rows = cur.fetchall()

        result["radii"][label] = [
            {
                "geoid": geoid,
                "statefp": statefp,
                "countyfp": countyfp,
                "intersection_pct": float(pct) if pct is not None else None,
            }
            for geoid, statefp, countyfp, pct in rows
        ]

    total = sum(len(v) for v in result["radii"].values())
    if total == 0:
        return {
            "available": False,
            "flag": "No Census block groups found near this location.",
        }

    return result
