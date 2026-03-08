"""Query FCC broadband availability from the fcc_broadband_coverage PostGIS table.

Spatial join strategy: FCC location data includes a 15-digit census block GEOID
(``block_geoid``). The first 12 characters match the ``census_block_groups.geoid``
column. We find the block group that contains the query point, then look up all
broadband coverage rows whose ``block_geoid`` starts with that block group GEOID.

This returns all providers and technologies reported as available at any
serviceable location within the same census block group as the query point —
a good proxy for site-level broadband availability.
"""

from __future__ import annotations

from typing import Any

from plinth.ingest.api.fcc_broadband import DISCLAIMER

_TECH_LABELS: dict[int, str] = {
    0: "Other",
    10: "Copper/DSL",
    40: "Cable",
    50: "Fiber",
    70: "Unlicensed Fixed Wireless",
    71: "Licensed Fixed Wireless",
    72: "LBR Fixed Wireless",
    300: "Licensed Fixed Wireless (300)",
    400: "Unlicensed Fixed Wireless (400)",
}


def query_fcc_broadband(lat: float, lon: float) -> dict[str, Any]:
    """
    Return fixed broadband providers available at the query point.

    Looks up the census block group containing (lat, lon), then returns all
    FCC broadband coverage rows for that block group, grouped by provider
    and technology. Satellite broadband is noted separately as universally
    available.

    Returns a dict with keys:
      - available (bool)
      - providers (list of dicts with brand_name, technology, download/upload Mbps)
      - best_download_mbps (int | None)
      - best_upload_mbps (int | None)
      - technologies (list of technology label strings)
      - block_group_geoid (str)
      - source_date (str — the as-of date of the loaded data)
      - disclaimer (str)
      - flag (str, only present if data unavailable)
    """
    from plinth.db.connection import get_connection

    with get_connection() as conn:
        with conn.cursor() as cur:
            # Step 1: find the block group containing the point
            cur.execute(
                """
                SELECT geoid
                FROM census_block_groups
                WHERE ST_Contains(
                    geom,
                    ST_SetSRID(ST_MakePoint(%s, %s), 4326)
                )
                LIMIT 1
                """,
                (lon, lat),
            )
            row = cur.fetchone()
            if not row:
                return {
                    "available": False,
                    "flag": "No census block group found for this location.",
                    "disclaimer": DISCLAIMER,
                }
            bg_geoid = row[0]

            # Step 2: look up all broadband providers for that block group
            cur.execute(
                """
                SELECT DISTINCT
                    brand_name,
                    technology_code,
                    MAX(max_download_mbps) AS max_dl,
                    MAX(max_upload_mbps)   AS max_ul,
                    bool_or(low_latency)   AS low_latency,
                    MAX(as_of_date::text)  AS as_of_date
                FROM fcc_broadband_coverage
                WHERE LEFT(block_geoid, 12) = %s
                  AND business_residential_code IN ('R', 'X')
                GROUP BY brand_name, technology_code
                ORDER BY MAX(max_download_mbps) DESC, brand_name
                """,
                (bg_geoid,),
            )
            rows = cur.fetchall()

    if not rows:
        return {
            "available": False,
            "flag": (
                "No FCC broadband coverage data found for this location. "
                "The FCC broadband ingestor may not have been run yet."
            ),
            "block_group_geoid": bg_geoid,
            "disclaimer": DISCLAIMER,
        }

    as_of_date = rows[0][5] if rows else None
    providers = []
    best_dl = 0
    best_ul = 0
    tech_set: set[str] = set()

    for brand_name, tech_code, max_dl, max_ul, low_lat, _ in rows:
        label = _TECH_LABELS.get(tech_code, f"Tech {tech_code}")
        providers.append({
            "brand_name": brand_name,
            "technology": label,
            "technology_code": tech_code,
            "max_download_mbps": max_dl,
            "max_upload_mbps": max_ul,
            "low_latency": low_lat,
        })
        tech_set.add(label)
        if max_dl and max_dl > best_dl:
            best_dl = max_dl
        if max_ul and max_ul > best_ul:
            best_ul = max_ul

    return {
        "available": True,
        "providers": providers,
        "provider_count": len(providers),
        "best_download_mbps": best_dl or None,
        "best_upload_mbps": best_ul or None,
        "technologies": sorted(tech_set),
        "satellite_note": "GSO and NGSO satellite broadband (e.g. Starlink, Viasat) is available at virtually all US locations and is not included in the counts above.",
        "block_group_geoid": bg_geoid,
        "source_date": as_of_date,
        "disclaimer": DISCLAIMER,
    }
