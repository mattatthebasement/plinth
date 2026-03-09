"""Realistic hardcoded mock data for Step 7.1 PDF skeleton.

All values approximate the Collinsville, OK test coordinate.
Replace with live query results in Steps 7.2+.
"""

MOCK_CONTEXT = {
    # ── Site identity ────────────────────────────────────────────────────
    "address": "11822 E 116th St N",
    "city_state_zip": "Collinsville, OK 74021",
    "county": "Rogers County, Oklahoma",
    "lat": 36.04700,
    "lon": -95.81289,
    "report_id": "PLN-20260309-DEMO",
    "report_date": "March 9, 2026",
    "prepared_for": "— Demo Report —",

    # ── Section 1 — Executive Summary ───────────────────────────────────
    "exec_flags": [
        "FEMA Flood Zone X — area of minimal flood hazard per NFHL mapping.",
        "Seismic PGA 0.05g — low seismic hazard. See Section 2 for details.",
        "Wildfire Hazard Potential: Low (1,240 / 144,153 national index).",
        "NOAA station 11.2 mi away — values may not reflect site microclimate.",
    ],
    "iecc_zone": "3",
    "iecc_description": "Mixed-Humid",
    "population_5mi": "42,500",
    "risk_summary": [
        {"category": "Flood Risk",       "value": "Zone X — Minimal",           "source": "FEMA NFHL"},
        {"category": "Seismic PGA",      "value": "0.05g (MCE\u1d63)",           "source": "USGS NEHRP 2020"},
        {"category": "Wildfire WHP",     "value": "1,240 / 144,153",             "source": "USDA Forest Service 2023"},
        {"category": "Hydrologic Group", "value": "B/C — Moderate runoff",       "source": "USDA SSURGO"},
        {"category": "Air Quality",      "value": "PM\u2082.\u2085 8.2 \u00b5g/m\u00b3 (NAAQS: 9.0)", "source": "EPA AQS 2023"},
        {"category": "FEMA NRI Score",   "value": "14.2 — Relatively Low",       "source": "FEMA National Risk Index"},
    ],

    # ── Section 2 — Environmental Risk ──────────────────────────────────
    "flood": {
        "zone": "X",
        "subtype": "Area of Minimal Flood Hazard",
        "sfha": False,
        "bfe_ft": None,
        "nfhl_date": "2019-11-15",
        "mapped": True,
    },
    "seismic": {
        "pgam_g": 0.047,
        "ss_g": 0.112,
        "s1_g": 0.044,
        "eq_count": 4,
        "eq_max_mag": 4.2,
        "eq_years": 50,
        "eq_radius_mi": 50,
    },
    "wildfire": {
        "whp_value": 1240,
        "whp_national_max": 144153,
        "vintage": "2023",
        "resolution_m": 270,
    },
    "soil": {
        "muname": "Dennis-Pharoah complex, 1 to 3 percent slopes",
        "mukey": "378454",
        "hydrologic_group": "B/C",
        "drainage_class": "Well drained",
        "slope_pct": 2.0,
        "taxonomic_class": "Fine, mixed, active, thermic Oxyaquic Hapludalfs",
        "dominant_component": "Dennis",
        "dominant_component_pct": 55.0,
        "nearest_fallback": True,
    },
    "air_quality": {
        "available": False,
        "flag": "EPA AQS credentials not yet configured. Data unavailable for this demo.",
    },
    "fema_nri": {
        "tract_id": "40131950200",
        "risk_score": 14.2,
        "risk_ratng": "Relatively Low",
        "hazards": {
            "Riverine Flooding": 9.8,
            "Tornado": 21.4,
            "Hail": 18.7,
            "Strong Wind": 11.2,
            "Winter Weather": 7.3,
            "Wildfire": 3.1,
            "Earthquake": 2.4,
        },
    },

    # ── Section 3 — Physical Context ─────────────────────────────────────
    "elevation": {
        "elevation_m": 211.0,
        "elevation_ft": 692.3,
        "resolution_m": 10.0,
    },
    "slope": {
        "mean_slope_pct": 1.92,
        "max_slope_pct": 3.61,
        "radius_m": 100,
    },
    "land_cover": {
        "dominant_class": "Developed, Low Intensity",
        "dominant_class_code": 22,
        "impervious_pct_estimate": 31.2,
        "radius_m": 500,
        "distribution": [
            {"class": "Developed, Low Intensity", "pct": 41.8},
            {"class": "Grassland/Herbaceous",     "pct": 27.6},
            {"class": "Pasture/Hay",              "pct": 19.3},
            {"class": "Cultivated Crops",         "pct": 6.7},
            {"class": "Open Water",               "pct": 4.6},
        ],
    },
    "hydro": {
        "waterbody": {"name": "Verdigris River", "type": "LakePond", "distance_mi": 4.241},
        "flowline": {"name": "Bird Creek", "type": "StreamRiver", "distance_mi": 1.326},
        "search_radius_mi": 5,
    },

    # ── Section 4 — Climate & Weather ────────────────────────────────────
    "climate": {
        "station_name": "TULSA INTERNATIONAL AIRPORT",
        "station_id": "USC00348818",
        "distance_mi": 11.2,
        "period": "1991–2020",
        "months": ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
        "tmax_f": [48.2, 54.1, 63.4, 72.8, 80.4, 89.3, 94.2, 93.5, 84.6, 73.1, 59.8, 49.4],
        "tmin_f": [27.6, 31.8, 40.2, 49.3, 58.6, 67.5, 72.4, 71.2, 62.1, 50.4, 38.7, 29.1],
        "prcp_in": [1.73, 2.06, 3.14, 3.81, 5.42, 4.28, 3.10, 2.87, 4.21, 4.08, 2.84, 2.15],
        "snow_in": [1.4, 1.8, 0.6, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.4, 1.1],
        "hdd_annual": 3142,
        "cdd_annual": 2218,
        "rh_annual_pct": 64,
        "freeze_thaw_days": 62,
    },
    "iecc_note": "Local jurisdiction adoption may vary. Verify with AHJ.",

    # ── Section 5 — Solar ─────────────────────────────────────────────────
    "solar": {
        "peak_sun_hours": 4.83,
        "annual_ghi_kwh_m2_day": 4.83,
        "latitude": 36.047,
        "months": ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
        "sunrise": ["7:32", "7:06", "6:25", "6:37", "6:01", "5:50",
                    "5:58", "6:26", "6:57", "7:27", "7:00", "7:28"],
        "sunset":  ["5:32", "6:03", "6:33", "7:01", "7:29", "8:00",
                    "8:10", "7:46", "7:01", "6:17", "5:40", "5:26"],
        "ghi_monthly": [2.71, 3.42, 4.38, 5.41, 6.12, 6.88,
                        6.73, 6.21, 5.11, 4.02, 2.83, 2.41],
    },

    # ── Section 6 — Demographic & Market Context ─────────────────────────
    "demographics": {
        "note": "Area-weighted block group intersections. Straight-line radius buffers — physical barriers not accounted for.",
        "acs_vintage": "2019–2023 ACS 5-Year Estimates",
        "radii": [
            {
                "label": "1-Mile Radius",
                "population": 8200,
                "households": 3150,
                "median_hhi": "$62,400",
                "median_age": 36.2,
                "pct_owner_occupied": "71%",
                "pct_bachelor_plus": "28%",
            },
            {
                "label": "5-Mile Radius",
                "population": 42500,
                "households": 16800,
                "median_hhi": "$68,200",
                "median_age": 35.8,
                "pct_owner_occupied": "69%",
                "pct_bachelor_plus": "31%",
            },
            {
                "label": "10-Mile Radius",
                "population": 128000,
                "households": 51200,
                "median_hhi": "$61,800",
                "median_age": 36.4,
                "pct_owner_occupied": "65%",
                "pct_bachelor_plus": "29%",
            },
        ],
    },

    # ── Section 7 — Infrastructure & Access ─────────────────────────────
    "infrastructure": {
        "broadband": [
            {"provider": "Metronet",          "technology": "Fiber",  "max_down_mbps": 5000, "max_up_mbps": 5000},
            {"provider": "Cox Communications", "technology": "Cable",  "max_down_mbps": 1000, "max_up_mbps": 35},
            {"provider": "AT&T",              "technology": "Fiber",  "max_down_mbps": 1000, "max_up_mbps": 1000},
            {"provider": "T-Mobile",          "technology": "LTE",    "max_down_mbps": 100,  "max_up_mbps": 20},
            {"provider": "Viasat",            "technology": "Satellite","max_down_mbps": 150, "max_up_mbps": 12},
        ],
        "road_note": "Site is approximately 0.3 miles from US-20 (East Admiral Place) and 4.1 miles from US-412.",
        "transit_note": "No fixed-route public transit service identified within 5 miles of this location.",
        "water_sewer_note": "Verify water and sewer service availability directly with the City of Collinsville Public Works and Rogers County Rural Water District.",
    },

    # ── Section 8 — Data Sources & Methodology ───────────────────────────
    "sources": [
        {"name": "FEMA National Flood Hazard Layer (NFHL)", "version": "2019-11-15", "refresh": "Monthly", "storage": "PostGIS"},
        {"name": "USGS 3D Elevation Program (3DEP)", "version": "2023", "refresh": "Annual", "storage": "MinIO COG"},
        {"name": "USGS National Land Cover Database (NLCD)", "version": "2021", "refresh": "Annual", "storage": "MinIO COG"},
        {"name": "USGS NEHRP 2020 Seismic Hazard", "version": "2020", "refresh": "API (365d TTL)", "storage": "query_cache"},
        {"name": "USGS Earthquake Catalog (FDSN)", "version": "Real-time", "refresh": "API (30d TTL)", "storage": "query_cache"},
        {"name": "USDA NRCS SSURGO", "version": "2024-03", "refresh": "Annual", "storage": "PostGIS"},
        {"name": "USDA Forest Service Wildfire Hazard Potential", "version": "2023", "refresh": "Annual", "storage": "API (365d TTL)"},
        {"name": "FEMA National Risk Index", "version": "2023", "refresh": "Annual", "storage": "PostGIS"},
        {"name": "US Census TIGER/Line Block Groups", "version": "2023", "refresh": "Annual", "storage": "PostGIS"},
        {"name": "US Census ACS 5-Year Estimates", "version": "2019–2023", "refresh": "Annual", "storage": "API (365d TTL)"},
        {"name": "IECC Climate Zone Map (DOE/PNNL)", "version": "IECC 2021", "refresh": "Per code cycle", "storage": "PostGIS"},
        {"name": "NOAA US Climate Normals 1991–2020", "version": "2020", "refresh": "Decadal", "storage": "PostGIS"},
        {"name": "NASA POWER Climatology 2001–2020", "version": "2020", "refresh": "API (30d TTL)", "storage": "query_cache"},
        {"name": "NHDPlus High Resolution Hydrography", "version": "2023", "refresh": "Annual", "storage": "PostGIS"},
        {"name": "FCC National Broadband Map", "version": "2024-06", "refresh": "Semi-annual", "storage": "PostGIS"},
        {"name": "EPA Air Quality System (AQS)", "version": "2023", "refresh": "Annual", "storage": "query_cache"},
    ],
}
