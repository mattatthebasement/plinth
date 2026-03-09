"""NHDPlus hydrography nearest-feature query."""

from __future__ import annotations

from typing import Any

from plinth.db.connection import get_connection

_MI_TO_M = 1609.344

# NHD ftype codes for waterbodies
_FTYPE_LABELS = {
    390: "Lake/Pond",
    436: "Reservoir",
    466: "Swamp/Marsh",
    493: "Estuary",
    361: "Playa",
    378: "Ice Mass",
}

# NHD ftype codes for flowlines
_FLOWLINE_LABELS = {
    460: "Stream/River",
    558: "Artificial Path",
    334: "Connector",
    336: "Canal/Ditch",
    420: "Underground Conduit",
    428: "Pipeline",
}


def query_hydro(lat: float, lon: float, radius_mi: float = 5.0) -> dict[str, Any]:
    """
    Return nearest named waterbody and flowline within *radius_mi* miles.

    Searches nhd_waterbodies and nhd_flowlines separately, returning the
    nearest feature of each type. Unnamed features (gnis_name IS NULL) are
    included only if no named feature is found.

    Returns distances in miles from the input point.
    """
    radius_m = radius_mi * _MI_TO_M

    # Nearest waterbody
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    permanent_identifier,
                    gnis_name,
                    areasqkm,
                    ftype,
                    fcode,
                    ST_Distance(
                        geom::geography,
                        ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
                    ) AS dist_m
                FROM nhd_waterbodies
                WHERE ST_DWithin(
                    geom::geography,
                    ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                    %s
                )
                ORDER BY
                    gnis_name IS NULL,   -- named features first
                    dist_m
                LIMIT 1
                """,
                (lon, lat, lon, lat, radius_m),
            )
            wb_row = cur.fetchone()

    # Nearest flowline
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    permanent_identifier,
                    gnis_name,
                    lengthkm,
                    ftype,
                    fcode,
                    ST_Distance(
                        geom::geography,
                        ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
                    ) AS dist_m
                FROM nhd_flowlines
                WHERE ST_DWithin(
                    geom::geography,
                    ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                    %s
                )
                ORDER BY
                    gnis_name IS NULL,
                    dist_m
                LIMIT 1
                """,
                (lon, lat, lon, lat, radius_m),
            )
            fl_row = cur.fetchone()

    if not wb_row and not fl_row:
        return {
            "available": True,
            "source": "USGS NHDPlus High Resolution",
            "search_radius_mi": radius_mi,
            "waterbody": None,
            "flowline": None,
            "flag": f"No hydrographic features found within {radius_mi} mile(s).",
        }

    result: dict[str, Any] = {
        "available": True,
        "source": "USGS NHDPlus High Resolution",
        "search_radius_mi": radius_mi,
        "waterbody": None,
        "flowline": None,
    }

    if wb_row:
        pid, name, area_sqkm, ftype, fcode, dist_m = wb_row
        result["waterbody"] = {
            "name": name or "(unnamed)",
            "type": _FTYPE_LABELS.get(ftype, f"ftype:{ftype}"),
            "fcode": fcode,
            "area_sqkm": float(area_sqkm) if area_sqkm is not None else None,
            "distance_mi": round(dist_m / _MI_TO_M, 3),
            "permanent_identifier": pid,
        }

    if fl_row:
        pid, name, length_km, ftype, fcode, dist_m = fl_row
        result["flowline"] = {
            "name": name or "(unnamed)",
            "type": _FLOWLINE_LABELS.get(ftype, f"ftype:{ftype}"),
            "fcode": fcode,
            "length_km": float(length_km) if length_km is not None else None,
            "distance_mi": round(dist_m / _MI_TO_M, 3),
            "permanent_identifier": pid,
        }

    return result
