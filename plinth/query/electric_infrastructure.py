"""Electric infrastructure query — utility territory, substations, transmission lines, power plants."""

from __future__ import annotations

import math
from typing import Any

from plinth.db.connection import get_connection

_MAX_SUBSTATION_MI = 15.0
_MAX_TX_MI = 10.0
_MAX_PLANT_MI = 25.0
_MI_TO_M = 1609.344

# EIA fuel type codes → human-readable labels
_FUEL_LABELS: dict[str, str] = {
    "NG": "Natural Gas",
    "SUN": "Solar",
    "WND": "Wind",
    "WAT": "Hydro",
    "NUC": "Nuclear",
    "COL": "Coal",
    "BIT": "Coal (Bituminous)",
    "LIG": "Coal (Lignite)",
    "SUB": "Coal (Sub-bituminous)",
    "LFG": "Landfill Gas",
    "OIL": "Oil/Petroleum",
    "DFO": "Oil/Petroleum",
    "RFO": "Oil/Petroleum",
    "JF": "Oil/Petroleum",
    "KER": "Oil/Petroleum",
    "GEO": "Geothermal",
    "WH": "Waste Heat",
    "AB": "Agricultural Byproduct",
    "MSW": "Municipal Solid Waste",
    "OBG": "Other Biomass Gas",
    "OBL": "Other Biomass Liquid",
    "OBS": "Other Biomass Solid",
    "OG": "Other Gas",
    "PC": "Petroleum Coke",
    "PUR": "Purchased Steam",
    "SGC": "Coal-Derived Gas",
    "SGP": "Synthesis Gas",
    "TDF": "Tire-Derived Fuel",
    "WC": "Waste Coal",
    "WO": "Waste Oil",
    "OTH": "Other",
}

# Voltage class groupings (kV)
_VOLTAGE_CLASSES = [
    ("500kV+",   500, 9999),
    ("345kV",    300, 499),
    ("230kV",    200, 299),
    ("138–161kV", 100, 199),
    ("69–115kV",  60,  99),
    ("<69kV",      0,  59),
]

# Fuel color palette for maps and charts
FUEL_COLORS: dict[str, str] = {
    "Natural Gas":        "#F59E0B",
    "Solar":              "#EAB308",
    "Wind":               "#10B981",
    "Hydro":              "#3B82F6",
    "Nuclear":            "#8B5CF6",
    "Coal":               "#6B7280",
    "Coal (Bituminous)":  "#6B7280",
    "Coal (Lignite)":     "#6B7280",
    "Coal (Sub-bituminous)": "#6B7280",
    "Landfill Gas":       "#84CC16",
    "Oil/Petroleum":      "#92400E",
    "Geothermal":         "#EF4444",
    "Other":              "#94A3B8",
}


def _fuel_label(code: str) -> str:
    return _FUEL_LABELS.get(code, "Other")


def _fuel_color(label: str) -> str:
    return FUEL_COLORS.get(label, FUEL_COLORS["Other"])


def _substation_name(raw: str | None) -> str | None:
    """Return None for HIFLD placeholder names; caller shows 'Unnamed substation'."""
    if not raw:
        return None
    upper = raw.upper()
    if upper.startswith("UNKNOWN") or upper.startswith("TAP"):
        return None
    return raw


def query_electric_infrastructure(lat: float, lon: float) -> dict[str, Any]:
    """
    Return electric infrastructure data for the given coordinates.

    Queries:
    - Service territory (utility provider + simplified polygon for map)
    - Nearest substations within 15 mi
    - Nearest transmission line per voltage class within 10 mi
    - Nearest operating power plants within 25 mi + capacity by fuel
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            # ── Service territories ──────────────────────────────────────────
            cur.execute(
                """
                SELECT utility_name, eia_id, entity_type, state,
                       ST_AsGeoJSON(ST_Simplify(geom, 0.01)) AS geom_json
                FROM electric_service_territories
                WHERE ST_Contains(geom, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
                ORDER BY utility_name
                """,
                (lon, lat),
            )
            territory_rows = cur.fetchall()

            # ── Nearest substations ──────────────────────────────────────────
            cur.execute(
                """
                SELECT
                    substation_name,
                    max_voltage_kv,
                    min_voltage_kv,
                    line_count,
                    ST_Distance(
                        geom::geography,
                        ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
                    ) / 1609.344 AS dist_mi,
                    ST_Y(geom::geometry) AS stn_lat,
                    ST_X(geom::geometry) AS stn_lon
                FROM electric_substations
                WHERE ST_DWithin(
                    geom::geography,
                    ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                    %s
                )
                ORDER BY dist_mi
                LIMIT 5
                """,
                (lon, lat, lon, lat, _MAX_SUBSTATION_MI * _MI_TO_M),
            )
            substation_rows = cur.fetchall()

            # ── Transmission lines — nearest per voltage class ────────────────
            cur.execute(
                """
                SELECT
                    voltage_kv,
                    voltage_class,
                    owner,
                    ST_Distance(
                        geom::geography,
                        ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
                    ) / 1609.344 AS dist_mi,
                    ST_AsGeoJSON(ST_SimplifyPreserveTopology(geom, 0.001)) AS geom_json
                FROM electric_transmission_lines
                WHERE ST_DWithin(
                    geom::geography,
                    ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                    %s
                )
                  AND voltage_kv IS NOT NULL
                ORDER BY dist_mi
                """,
                (lon, lat, lon, lat, _MAX_TX_MI * _MI_TO_M),
            )
            tx_rows = cur.fetchall()

            # ── Power plants within 25 mi ────────────────────────────────────
            cur.execute(
                """
                SELECT
                    plant_name,
                    primary_fuel,
                    capacity_mw_total,
                    ST_Distance(
                        geom::geography,
                        ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
                    ) / 1609.344 AS dist_mi,
                    ST_Y(geom::geometry) AS plt_lat,
                    ST_X(geom::geometry) AS plt_lon
                FROM eia_power_plants
                WHERE ST_DWithin(
                    geom::geography,
                    ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                    %s
                )
                  AND operating_status = 'OP'
                ORDER BY dist_mi
                LIMIT 25
                """,
                (lon, lat, lon, lat, _MAX_PLANT_MI * _MI_TO_M),
            )
            plant_rows = cur.fetchall()

    import json as _json

    # ── Assemble service territories ─────────────────────────────────────────
    service_territories = []
    for row in territory_rows:
        utility_name, eia_id, entity_type, state, geom_json = row
        service_territories.append({
            "utility_name": utility_name,
            "eia_id": eia_id,
            "entity_type": entity_type or "Unknown",
            "state": state,
            "geojson": _json.loads(geom_json) if geom_json else None,
        })

    # ── Assemble substations ─────────────────────────────────────────────────
    substations = []
    for row in substation_rows:
        raw_name, max_kv, min_kv, line_count, dist_mi, stn_lat, stn_lon = row
        name = _substation_name(raw_name)
        substations.append({
            "name": name,
            "display_name": name if name else "Unnamed substation",
            "max_voltage_kv": float(max_kv) if max_kv is not None else None,
            "min_voltage_kv": float(min_kv) if min_kv is not None else None,
            "line_count": int(line_count) if line_count is not None else None,
            "distance_mi": round(float(dist_mi), 1),
            "lat": float(stn_lat),
            "lon": float(stn_lon),
        })

    # ── Assemble transmission lines by voltage class ─────────────────────────
    # Collect all lines with geometry for map rendering; also track nearest per class
    tx_by_class: dict[str, dict] = {}
    tx_map_lines: list[dict] = []
    for row in tx_rows:
        voltage_kv, voltage_class, owner, dist_mi, geom_json = row
        kv = float(voltage_kv)
        class_label = "Other"
        for label, lo, hi in _VOLTAGE_CLASSES:
            if lo <= kv <= hi:
                class_label = label
                break
        if class_label not in tx_by_class:
            tx_by_class[class_label] = {
                "voltage_class": class_label,
                "voltage_kv": kv,
                "owner": owner or "Unknown",
                "distance_mi": round(float(dist_mi), 1),
            }
        # Collect geometry for map
        if geom_json:
            tx_map_lines.append({
                "voltage_class": class_label,
                "geojson": _json.loads(geom_json),
            })

    # Return in descending voltage order
    transmission_lines = [
        tx_by_class[label]
        for label, _, _ in _VOLTAGE_CLASSES
        if label in tx_by_class
    ]

    # ── Assemble plants ──────────────────────────────────────────────────────
    nearby_plants = []
    capacity_by_fuel: dict[str, float] = {}
    for row in plant_rows:
        plant_name, primary_fuel, capacity_mw, dist_mi, plt_lat, plt_lon = row
        fuel_label = _fuel_label(primary_fuel or "OTH")
        # Normalize coal variants to "Coal" for summary
        summary_fuel = "Coal" if "Coal" in fuel_label else fuel_label
        cap = float(capacity_mw) if capacity_mw is not None else 0.0
        capacity_by_fuel[summary_fuel] = capacity_by_fuel.get(summary_fuel, 0.0) + cap

        if len(nearby_plants) < 5:
            nearby_plants.append({
                "plant_name": plant_name,
                "fuel_label": fuel_label,
                "fuel_color": _fuel_color(fuel_label),
                "capacity_mw": round(cap, 1),
                "distance_mi": round(float(dist_mi), 1),
                "lat": float(plt_lat),
                "lon": float(plt_lon),
            })

    # Sort fuel summary by descending capacity
    capacity_by_fuel_sorted = [
        {"fuel": k, "capacity_mw": round(v, 1), "color": _fuel_color(k)}
        for k, v in sorted(capacity_by_fuel.items(), key=lambda x: -x[1])
    ]

    available = bool(service_territories or substations or transmission_lines or nearby_plants)

    return {
        "available": available,
        "service_territories": service_territories,
        "dual_territory": len(service_territories) > 1,
        "substations": substations,
        "transmission_lines": transmission_lines,
        "tx_map_lines": tx_map_lines,
        "nearby_plants": nearby_plants,
        "capacity_by_fuel": capacity_by_fuel_sorted,
        "total_capacity_mw": round(sum(v["capacity_mw"] for v in capacity_by_fuel_sorted), 1),
    }
