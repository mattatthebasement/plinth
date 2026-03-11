"""Census ACS 5-Year Estimates API client — area-weighted demographic aggregation."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from plinth.db.cache import get_cached, set_cached

log = logging.getLogger(__name__)

_BASE = "https://api.census.gov/data"
_DATASET = "census-acs"
_TTL_DAYS = 365

# ACS variable codes → internal field names
ACS_VARS: dict[str, str] = {
    # Population, Sex & Age (B01001)
    "B01003_001E": "total_population",
    "B01002_001E": "median_age",
    "B01002_002E": "median_age_male",
    "B01002_003E": "median_age_female",
    "B25010_001E": "avg_household_size",
    "B01001_002E": "male_total",
    "B01001_026E": "female_total",
    # Male age brackets
    "B01001_003E": "m_under5", "B01001_004E": "m_5_9",
    "B01001_005E": "m_10_14", "B01001_006E": "m_15_17",
    "B01001_007E": "m_18_19", "B01001_008E": "m_20",
    "B01001_009E": "m_21", "B01001_010E": "m_22_24",
    "B01001_011E": "m_25_29", "B01001_012E": "m_30_34",
    "B01001_013E": "m_35_39", "B01001_014E": "m_40_44",
    "B01001_015E": "m_45_49", "B01001_016E": "m_50_54",
    "B01001_017E": "m_55_59", "B01001_018E": "m_60_61",
    "B01001_019E": "m_62_64", "B01001_020E": "m_65_66",
    "B01001_021E": "m_67_69", "B01001_022E": "m_70_74",
    "B01001_023E": "m_75_79", "B01001_024E": "m_80_84",
    "B01001_025E": "m_85plus",
    # Female age brackets
    "B01001_027E": "f_under5", "B01001_028E": "f_5_9",
    "B01001_029E": "f_10_14", "B01001_030E": "f_15_17",
    "B01001_031E": "f_18_19", "B01001_032E": "f_20",
    "B01001_033E": "f_21", "B01001_034E": "f_22_24",
    "B01001_035E": "f_25_29", "B01001_036E": "f_30_34",
    "B01001_037E": "f_35_39", "B01001_038E": "f_40_44",
    "B01001_039E": "f_45_49", "B01001_040E": "f_50_54",
    "B01001_041E": "f_55_59", "B01001_042E": "f_60_61",
    "B01001_043E": "f_62_64", "B01001_044E": "f_65_66",
    "B01001_045E": "f_67_69", "B01001_046E": "f_70_74",
    "B01001_047E": "f_75_79", "B01001_048E": "f_80_84",
    "B01001_049E": "f_85plus",
    # Households & Income
    "B11001_001E": "total_households",
    "B19013_001E": "median_hhi",
    "B19301_001E": "per_capita_income",
    "C17002_001E": "poverty_universe",
    "C17002_002E": "poverty_under_050",
    "C17002_003E": "poverty_050_099",
    "B19057_002E": "public_assistance_count",
    "B19057_001E": "public_assistance_universe",
    # Housing Stock
    "B25001_001E": "total_housing_units",
    "B25077_001E": "median_home_value",
    "B25064_001E": "median_gross_rent",
    "B25002_003E": "vacant_units",
    "B25002_001E": "total_housing_units_occ",
    "B25035_001E": "median_year_built",
    # Tenure
    "B25003_002E": "owner_occupied",
    "B25003_003E": "renter_occupied",
    "B25003_001E": "tenure_universe",
    # Education
    "B15003_001E": "edu_universe",
    "B15003_017E": "hs_diploma",
    "B15003_018E": "ged",
    "B15003_019E": "some_college_lt1",
    "B15003_020E": "some_college_ge1",
    "B15003_021E": "associates",
    "B15003_022E": "bachelors",
    "B15003_023E": "masters",
    "B15003_024E": "professional",
    "B15003_025E": "doctorate",
    # Commute & Employment
    "B08303_001E": "travel_time_total",
    "B08303_002E": "travel_time_lt5",
    "B08303_003E": "travel_time_5_9",
    "B08303_004E": "travel_time_10_14",
    "B08303_005E": "travel_time_15_19",
    "B08303_006E": "travel_time_20_24",
    "B08303_007E": "travel_time_25_29",
    "B08303_008E": "travel_time_30_34",
    "B08303_009E": "travel_time_35_39",
    "B08303_010E": "travel_time_40_44",
    "B08303_011E": "travel_time_45_59",
    "B08303_012E": "travel_time_60_89",
    "B08303_013E": "travel_time_90plus",
    "B08301_003E": "drive_alone",
    "B08301_001E": "commute_universe",
    "B08301_021E": "work_from_home",
    "B23025_005E": "unemployed",
    "B23025_003E": "labor_force",
    "B23025_002E": "in_labor_force",
    "B23025_001E": "labor_force_universe",
    # Occupation (C24010 — combined male+female top-level categories)
    "C24010_001E": "occ_total",
    "C24010_003E": "occ_m_mgmt", "C24010_019E": "occ_m_service",
    "C24010_027E": "occ_m_sales", "C24010_030E": "occ_m_natural",
    "C24010_034E": "occ_m_production",
    "C24010_039E": "occ_f_mgmt", "C24010_055E": "occ_f_service",
    "C24010_063E": "occ_f_sales", "C24010_066E": "occ_f_natural",
    "C24010_070E": "occ_f_production",
    # Industry (C24030 — combined male+female top-level categories)
    "C24030_001E": "ind_total",
    "C24030_003E": "ind_m_ag_mining", "C24030_006E": "ind_m_construction",
    "C24030_007E": "ind_m_manufacturing", "C24030_008E": "ind_m_wholesale",
    "C24030_009E": "ind_m_retail", "C24030_010E": "ind_m_transport_util",
    "C24030_013E": "ind_m_information", "C24030_014E": "ind_m_finance_re",
    "C24030_017E": "ind_m_professional", "C24030_021E": "ind_m_edu_health",
    "C24030_024E": "ind_m_arts_food", "C24030_027E": "ind_m_other_svc",
    "C24030_028E": "ind_m_public_admin",
    "C24030_030E": "ind_f_ag_mining", "C24030_033E": "ind_f_construction",
    "C24030_034E": "ind_f_manufacturing", "C24030_035E": "ind_f_wholesale",
    "C24030_036E": "ind_f_retail", "C24030_037E": "ind_f_transport_util",
    "C24030_040E": "ind_f_information", "C24030_041E": "ind_f_finance_re",
    "C24030_044E": "ind_f_professional", "C24030_048E": "ind_f_edu_health",
    "C24030_051E": "ind_f_arts_food", "C24030_054E": "ind_f_other_svc",
    "C24030_055E": "ind_f_public_admin",
    # Race & Ethnicity
    "B03002_001E": "total_race",
    "B03002_003E": "non_hispanic_white",
    "B03002_012E": "hispanic",
    "B03002_004E": "black",
    "B03002_006E": "asian",
    # Language (C16002 = household-level; available at block group)
    "C16002_001E": "language_universe",
    "C16002_004E": "limited_english_spanish",
    "C16002_007E": "limited_english_other_indo",
    "C16002_010E": "limited_english_asian",
    "C16002_013E": "limited_english_other",
}

_VAR_CODES = list(ACS_VARS.keys())
_VAR_NAMES = list(ACS_VARS.values())

# Census API allows ~50 variables per request; split into batches
_MAX_VARS_PER_REQUEST = 48
_VAR_BATCHES = [
    _VAR_CODES[i : i + _MAX_VARS_PER_REQUEST]
    for i in range(0, len(_VAR_CODES), _MAX_VARS_PER_REQUEST)
]


def _cache_key(year: int, geoid: str) -> str:
    return f"{_DATASET}:{year}:{geoid}"


def _parse_geoid(geoid: str) -> tuple[str, str, str, str]:
    """Split 12-digit GEOID into (state, county, tract, block_group)."""
    return geoid[:2], geoid[2:5], geoid[5:11], geoid[11:12]


class _NetworkError(Exception):
    """Raised when a Census API request fails due to a network/connectivity issue."""


def _fetch_block_group(
    state: str,
    county: str,
    tract: str,
    block_group: str,
    api_key: str,
    acs_year: int,
) -> dict[str, Any] | None:
    """Fetch ACS data for a single block group. Returns field dict or None on error.

    Raises _NetworkError on connectivity failures so the caller can fast-fail.
    Returns None when the API responds but has no usable data for this block group.
    """
    combined_row: dict[str, str] = {}
    for batch in _VAR_BATCHES:
        get_str = ",".join(batch)
        url = (
            f"{_BASE}/{acs_year}/acs/acs5"
            f"?get={get_str}"
            f"&for=block+group:{block_group}"
            f"&in=state:{state}%20county:{county}%20tract:{tract}"
            f"&key={api_key}"
        )
        try:
            resp = httpx.get(url, timeout=8)
            resp.raise_for_status()
            data = resp.json()
        except (httpx.ConnectError, httpx.TimeoutException, OSError) as exc:
            log.warning("Census ACS network error for %s%s%s%s: %s", state, county, tract, block_group, exc)
            raise _NetworkError(str(exc)) from exc
        except Exception as exc:
            log.warning("Census ACS fetch failed for %s%s%s%s: %s", state, county, tract, block_group, exc)
            return None

        if not data or len(data) < 2:
            return None

        header = data[0]
        values = data[1]
        combined_row.update(dict(zip(header, values)))

    result: dict[str, float | None] = {}
    for code, field in ACS_VARS.items():
        raw = combined_row.get(code)
        try:
            val = float(raw) if raw not in (None, "", "-666666666", "-999999999") else None
        except (TypeError, ValueError):
            val = None
        # Negative sentinel values from ACS indicate N/A
        if val is not None and val < 0:
            val = None
        result[field] = val

    return result


def _fetch_with_cache(
    geoid: str,
    api_key: str,
    acs_year: int,
) -> dict[str, Any] | None:
    """Return ACS field dict for a GEOID, using query_cache.

    Raises _NetworkError on connectivity failure (propagated from _fetch_block_group).
    Returns None when the API has no data for this block group.
    """
    cache_key = _cache_key(acs_year, geoid)
    cached = get_cached(cache_key)
    if cached is not None:
        return cached

    state, county, tract, bg = _parse_geoid(geoid)
    result = _fetch_block_group(state, county, tract, bg, api_key, acs_year)
    if result is None:
        return None

    set_cached(cache_key, _DATASET, result, _TTL_DAYS)
    return result


def _safe_div(num: float | None, denom: float | None) -> float | None:
    if num is None or denom is None or denom == 0:
        return None
    return num / denom


def _aggregate(
    block_groups: list[dict],
    acs_data: dict[str, dict[str, Any]],
) -> dict[str, float | None]:
    """
    Area-weighted aggregate of ACS fields across block groups.

    Count fields: weighted sum (weight = intersection_pct / 100).
    Median/mean fields: weighted average using total_population as weight.
    Percentage fields: computed from summed numerators and denominators.
    """
    agg: dict[str, float | None] = {name: None for name in _VAR_NAMES}

    # Weighted totals for count fields
    count_fields = [
        "total_population", "total_households", "total_housing_units",
        "total_housing_units_occ", "vacant_units",
        "male_total", "female_total",
        # Male age brackets
        "m_under5", "m_5_9", "m_10_14", "m_15_17",
        "m_18_19", "m_20", "m_21", "m_22_24",
        "m_25_29", "m_30_34", "m_35_39", "m_40_44",
        "m_45_49", "m_50_54", "m_55_59", "m_60_61",
        "m_62_64", "m_65_66", "m_67_69", "m_70_74",
        "m_75_79", "m_80_84", "m_85plus",
        # Female age brackets
        "f_under5", "f_5_9", "f_10_14", "f_15_17",
        "f_18_19", "f_20", "f_21", "f_22_24",
        "f_25_29", "f_30_34", "f_35_39", "f_40_44",
        "f_45_49", "f_50_54", "f_55_59", "f_60_61",
        "f_62_64", "f_65_66", "f_67_69", "f_70_74",
        "f_75_79", "f_80_84", "f_85plus",
        # Income
        "poverty_under_050", "poverty_050_099", "poverty_universe",
        "public_assistance_count", "public_assistance_universe",
        "owner_occupied", "renter_occupied", "tenure_universe",
        "edu_universe", "hs_diploma", "ged", "some_college_lt1",
        "some_college_ge1", "associates", "bachelors", "masters",
        "professional", "doctorate",
        "travel_time_total", "travel_time_lt5", "travel_time_5_9",
        "travel_time_10_14", "travel_time_15_19", "travel_time_20_24",
        "travel_time_25_29", "travel_time_30_34", "travel_time_35_39",
        "travel_time_40_44", "travel_time_45_59", "travel_time_60_89",
        "travel_time_90plus",
        "drive_alone", "commute_universe", "work_from_home",
        "unemployed", "labor_force", "in_labor_force", "labor_force_universe",
        # Occupation
        "occ_total",
        "occ_m_mgmt", "occ_m_service", "occ_m_sales", "occ_m_natural", "occ_m_production",
        "occ_f_mgmt", "occ_f_service", "occ_f_sales", "occ_f_natural", "occ_f_production",
        # Industry
        "ind_total",
        "ind_m_ag_mining", "ind_m_construction", "ind_m_manufacturing",
        "ind_m_wholesale", "ind_m_retail", "ind_m_transport_util",
        "ind_m_information", "ind_m_finance_re", "ind_m_professional",
        "ind_m_edu_health", "ind_m_arts_food", "ind_m_other_svc", "ind_m_public_admin",
        "ind_f_ag_mining", "ind_f_construction", "ind_f_manufacturing",
        "ind_f_wholesale", "ind_f_retail", "ind_f_transport_util",
        "ind_f_information", "ind_f_finance_re", "ind_f_professional",
        "ind_f_edu_health", "ind_f_arts_food", "ind_f_other_svc", "ind_f_public_admin",
        # Race & Language
        "total_race", "non_hispanic_white", "hispanic", "black", "asian",
        "language_universe", "limited_english_spanish",
        "limited_english_other_indo", "limited_english_asian",
        "limited_english_other",
    ]

    # Weighted average fields (use total_population as weight)
    avg_fields = [
        "median_age", "median_age_male", "median_age_female",
        "avg_household_size",
        "median_hhi", "per_capita_income",
        "median_home_value", "median_gross_rent", "median_year_built",
    ]

    count_sums: dict[str, float] = {f: 0.0 for f in count_fields}
    avg_numerators: dict[str, float] = {f: 0.0 for f in avg_fields}
    avg_pop_weights: float = 0.0

    for bg_info in block_groups:
        geoid = bg_info["geoid"]
        frac = (bg_info.get("intersection_pct") or 0.0) / 100.0
        data = acs_data.get(geoid)
        if data is None or frac == 0.0:
            continue

        pop = data.get("total_population")
        pop_weight = (pop or 0.0) * frac

        for field in count_fields:
            val = data.get(field)
            if val is not None:
                count_sums[field] = count_sums.get(field, 0.0) + val * frac

        for field in avg_fields:
            val = data.get(field)
            if val is not None and pop_weight > 0:
                avg_numerators[field] = avg_numerators.get(field, 0.0) + val * pop_weight

        avg_pop_weights += pop_weight

    for field in count_fields:
        agg[field] = count_sums[field] if count_sums[field] > 0 else None

    for field in avg_fields:
        if avg_pop_weights > 0 and avg_numerators.get(field):
            agg[field] = avg_numerators[field] / avg_pop_weights
        else:
            agg[field] = None

    # Mean travel time from B08303 bracket midpoints
    _TRAVEL_MIDPOINTS = [
        ("travel_time_lt5", 2.5), ("travel_time_5_9", 7.0),
        ("travel_time_10_14", 12.0), ("travel_time_15_19", 17.0),
        ("travel_time_20_24", 22.0), ("travel_time_25_29", 27.0),
        ("travel_time_30_34", 32.0), ("travel_time_35_39", 37.0),
        ("travel_time_40_44", 42.0), ("travel_time_45_59", 52.0),
        ("travel_time_60_89", 74.5), ("travel_time_90plus", 100.0),
    ]
    tt_total = count_sums.get("travel_time_total", 0.0)
    if tt_total > 0:
        weighted_min = sum(count_sums.get(f, 0.0) * mid for f, mid in _TRAVEL_MIDPOINTS)
        agg["mean_travel_time_min"] = weighted_min / tt_total
    else:
        agg["mean_travel_time_min"] = None

    # Below-poverty count from C17002 (under 0.50 + 0.50–0.99)
    agg["below_poverty_count"] = (
        (count_sums.get("poverty_under_050") or 0.0)
        + (count_sums.get("poverty_050_099") or 0.0)
    ) or None

    # ── Derived age groups (sum male + female brackets) ──────────────
    def _age_sum(*fields: str) -> float | None:
        total = sum(count_sums.get(f, 0.0) for f in fields)
        return total if total > 0 else None

    agg["age_under_18"] = _age_sum(
        "m_under5", "m_5_9", "m_10_14", "m_15_17",
        "f_under5", "f_5_9", "f_10_14", "f_15_17",
    )
    agg["age_18_34"] = _age_sum(
        "m_18_19", "m_20", "m_21", "m_22_24", "m_25_29", "m_30_34",
        "f_18_19", "f_20", "f_21", "f_22_24", "f_25_29", "f_30_34",
    )
    agg["age_35_54"] = _age_sum(
        "m_35_39", "m_40_44", "m_45_49", "m_50_54",
        "f_35_39", "f_40_44", "f_45_49", "f_50_54",
    )
    agg["age_55_74"] = _age_sum(
        "m_55_59", "m_60_61", "m_62_64", "m_65_66", "m_67_69", "m_70_74",
        "f_55_59", "f_60_61", "f_62_64", "f_65_66", "f_67_69", "f_70_74",
    )
    agg["age_75_plus"] = _age_sum(
        "m_75_79", "m_80_84", "m_85plus",
        "f_75_79", "f_80_84", "f_85plus",
    )

    # ── Combined occupation totals (male + female) ───────────────────
    agg["occ_mgmt"] = _age_sum("occ_m_mgmt", "occ_f_mgmt")
    agg["occ_service"] = _age_sum("occ_m_service", "occ_f_service")
    agg["occ_sales"] = _age_sum("occ_m_sales", "occ_f_sales")
    agg["occ_natural"] = _age_sum("occ_m_natural", "occ_f_natural")
    agg["occ_production"] = _age_sum("occ_m_production", "occ_f_production")

    # ── Combined industry totals (male + female) ─────────────────────
    agg["ind_ag_mining"] = _age_sum("ind_m_ag_mining", "ind_f_ag_mining")
    agg["ind_construction"] = _age_sum("ind_m_construction", "ind_f_construction")
    agg["ind_manufacturing"] = _age_sum("ind_m_manufacturing", "ind_f_manufacturing")
    agg["ind_wholesale"] = _age_sum("ind_m_wholesale", "ind_f_wholesale")
    agg["ind_retail"] = _age_sum("ind_m_retail", "ind_f_retail")
    agg["ind_transport_util"] = _age_sum("ind_m_transport_util", "ind_f_transport_util")
    agg["ind_information"] = _age_sum("ind_m_information", "ind_f_information")
    agg["ind_finance_re"] = _age_sum("ind_m_finance_re", "ind_f_finance_re")
    agg["ind_professional"] = _age_sum("ind_m_professional", "ind_f_professional")
    agg["ind_edu_health"] = _age_sum("ind_m_edu_health", "ind_f_edu_health")
    agg["ind_arts_food"] = _age_sum("ind_m_arts_food", "ind_f_arts_food")
    agg["ind_other_svc"] = _age_sum("ind_m_other_svc", "ind_f_other_svc")
    agg["ind_public_admin"] = _age_sum("ind_m_public_admin", "ind_f_public_admin")

    return agg


def _fmt_int(val: float | None) -> str:
    if val is None:
        return "N/A"
    return f"{int(round(val)):,}"


def _fmt_currency(val: float | None) -> str:
    if val is None:
        return "N/A"
    return f"${int(round(val)):,}"


def _fmt_pct(val: float | None) -> str:
    if val is None:
        return "N/A"
    return f"{val:.1f}%"


def _fmt_decimal(val: float | None, places: int = 1) -> str:
    if val is None:
        return "N/A"
    return f"{val:.{places}f}"


def _fmt_year(val: float | None) -> str:
    if val is None:
        return "N/A"
    return str(int(round(val)))


def _parse_pct(s: str) -> float:
    """Parse a formatted percentage string like '33.6%' to a float for sorting. N/A → -1."""
    if s == "N/A":
        return -1.0
    return float(s.rstrip("%"))


def _build_demographics_rows(aggs: dict[str, dict[str, Any]]) -> dict:
    """Convert aggregated values for three radii into the demographics groups structure."""

    def _row(variable: str, r1_val, r5_val, r10_val) -> dict:
        return {"variable": variable, "r1": r1_val, "r5": r5_val, "r10": r10_val}

    def _pct_from(num_key: str, denom_key: str, radius: str) -> float | None:
        a = aggs[radius]
        num = a.get(num_key)
        denom = a.get(denom_key)
        if num is None or denom is None or denom == 0:
            return None
        return (num / denom) * 100.0

    def _limited_english_pct(radius: str) -> float | None:
        a = aggs[radius]
        total = a.get("language_universe")
        if total is None or total == 0:
            return None
        lep = sum(
            (a.get(f) or 0.0)
            for f in [
                "limited_english_spanish",
                "limited_english_other_indo",
                "limited_english_asian",
                "limited_english_other",
            ]
        )
        return (lep / total) * 100.0

    def _pct_bachelor_plus(radius: str) -> float | None:
        a = aggs[radius]
        universe = a.get("edu_universe")
        if universe is None or universe == 0:
            return None
        college_plus = sum(
            (a.get(f) or 0.0)
            for f in ["bachelors", "masters", "professional", "doctorate"]
        )
        return (college_plus / universe) * 100.0

    def _pct_hs_plus(radius: str) -> float | None:
        a = aggs[radius]
        universe = a.get("edu_universe")
        if universe is None or universe == 0:
            return None
        hs_plus = sum(
            (a.get(f) or 0.0)
            for f in [
                "hs_diploma", "ged", "some_college_lt1", "some_college_ge1",
                "associates", "bachelors", "masters", "professional", "doctorate",
            ]
        )
        return (hs_plus / universe) * 100.0

    def _other_race_pct(radius: str) -> float | None:
        a = aggs[radius]
        total = a.get("total_race")
        if total is None or total == 0:
            return None
        accounted = sum(
            (a.get(f) or 0.0)
            for f in ["non_hispanic_white", "hispanic", "black", "asian"]
        )
        return max(0.0, (total - accounted) / total * 100.0)

    def _vacancy_rate(radius: str) -> float | None:
        a = aggs[radius]
        vacant = a.get("vacant_units")
        total = a.get("total_housing_units_occ")
        if vacant is None or total is None or total == 0:
            return None
        return (vacant / total) * 100.0

    radii = ["1mi", "5mi", "10mi"]

    def _for_radii(fn) -> tuple:
        return tuple(fn(r) for r in radii)

    def _count_row(variable: str, key: str) -> dict:
        vals = [_fmt_int(aggs[r].get(key)) for r in radii]
        return _row(variable, *vals)

    def _currency_row(variable: str, key: str) -> dict:
        vals = [_fmt_currency(aggs[r].get(key)) for r in radii]
        return _row(variable, *vals)

    def _decimal_row(variable: str, key: str, places: int = 1) -> dict:
        vals = [_fmt_decimal(aggs[r].get(key), places) for r in radii]
        return _row(variable, *vals)

    def _year_row(variable: str, key: str) -> dict:
        vals = [_fmt_year(aggs[r].get(key)) for r in radii]
        return _row(variable, *vals)

    def _pct_row(variable: str, num_key: str, denom_key: str) -> dict:
        vals = [_fmt_pct(_pct_from(num_key, denom_key, r)) for r in radii]
        return _row(variable, *vals)

    def _owner_pct_row() -> dict:
        vals = [
            _fmt_pct(_pct_from("owner_occupied", "tenure_universe", r))
            for r in radii
        ]
        return _row("% Owner-Occupied", *vals)

    def _renter_pct_row() -> dict:
        vals = [
            _fmt_pct(_pct_from("renter_occupied", "tenure_universe", r))
            for r in radii
        ]
        return _row("% Renter-Occupied", *vals)

    return {
        "groups": [
            {
                "heading": "Population & Age",
                "rows": [
                    _count_row("Total Population", "total_population"),
                    _count_row("Male", "male_total"),
                    _count_row("Female", "female_total"),
                    _decimal_row("Median Age – Total", "median_age"),
                    _decimal_row("Median Age – Male", "median_age_male"),
                    _decimal_row("Median Age – Female", "median_age_female"),
                    _row("% Under 18", *[_fmt_pct(_pct_from("age_under_18", "total_population", r)) for r in radii]),
                    _row("% 18–34", *[_fmt_pct(_pct_from("age_18_34", "total_population", r)) for r in radii]),
                    _row("% 35–54", *[_fmt_pct(_pct_from("age_35_54", "total_population", r)) for r in radii]),
                    _row("% 55–74", *[_fmt_pct(_pct_from("age_55_74", "total_population", r)) for r in radii]),
                    _row("% 75+", *[_fmt_pct(_pct_from("age_75_plus", "total_population", r)) for r in radii]),
                ],
            },
            {
                "heading": "Households & Income",
                "rows": [
                    _count_row("Total Households", "total_households"),
                    _decimal_row("Average Household Size", "avg_household_size", 2),
                    _currency_row("Median Household Income", "median_hhi"),
                    _currency_row("Per Capita Income", "per_capita_income"),
                    _row(
                        "% Below Poverty Level",
                        *[_fmt_pct(_pct_from("below_poverty_count", "poverty_universe", r)) for r in radii],
                    ),
                    _row(
                        "% Receiving Public Assistance",
                        *[_fmt_pct(_pct_from("public_assistance_count", "public_assistance_universe", r)) for r in radii],
                    ),
                ],
            },
            {
                "heading": "Housing Stock",
                "rows": [
                    _count_row("Total Housing Units", "total_housing_units"),
                    _currency_row("Median Home Value", "median_home_value"),
                    _currency_row("Median Gross Rent", "median_gross_rent"),
                    _row(
                        "Vacancy Rate",
                        *[_fmt_pct(_vacancy_rate(r)) for r in radii],
                    ),
                    _year_row("Median Year Built", "median_year_built"),
                ],
            },
            {
                "heading": "Tenure",
                "rows": [
                    _owner_pct_row(),
                    _renter_pct_row(),
                ],
            },
            {
                "heading": "Education",
                "rows": [
                    _row(
                        "% Bachelor's Degree or Higher",
                        *[_fmt_pct(_pct_bachelor_plus(r)) for r in radii],
                    ),
                    _row(
                        "% High School Diploma or Higher",
                        *[_fmt_pct(_pct_hs_plus(r)) for r in radii],
                    ),
                ],
            },
            {
                "heading": "Commute & Employment",
                "rows": [
                    _row(
                        "Mean Travel Time to Work (min)",
                        *[_fmt_decimal(aggs[r].get("mean_travel_time_min")) for r in radii],
                    ),
                    _row(
                        "% Drive Alone",
                        *[_fmt_pct(_pct_from("drive_alone", "commute_universe", r)) for r in radii],
                    ),
                    _row(
                        "% Work from Home",
                        *[_fmt_pct(_pct_from("work_from_home", "commute_universe", r)) for r in radii],
                    ),
                    _row(
                        "Unemployment Rate",
                        *[_fmt_pct(_pct_from("unemployed", "in_labor_force", r)) for r in radii],
                    ),
                    _row(
                        "Labor Force Participation Rate",
                        *[_fmt_pct(_pct_from("in_labor_force", "labor_force_universe", r)) for r in radii],
                    ),
                ],
            },
            {
                "heading": "Occupation",
                "rows": sorted(
                    [
                        _row("% Management, Business, Science & Arts", *[_fmt_pct(_pct_from("occ_mgmt", "occ_total", r)) for r in radii]),
                        _row("% Service", *[_fmt_pct(_pct_from("occ_service", "occ_total", r)) for r in radii]),
                        _row("% Sales & Office", *[_fmt_pct(_pct_from("occ_sales", "occ_total", r)) for r in radii]),
                        _row("% Natural Resources, Construction & Maintenance", *[_fmt_pct(_pct_from("occ_natural", "occ_total", r)) for r in radii]),
                        _row("% Production, Transportation & Material Moving", *[_fmt_pct(_pct_from("occ_production", "occ_total", r)) for r in radii]),
                    ],
                    key=lambda r: _parse_pct(r["r1"]),
                    reverse=True,
                ),
            },
            {
                "heading": "Industry",
                "rows": sorted(
                    [
                        _row("% Agriculture, Forestry, Mining", *[_fmt_pct(_pct_from("ind_ag_mining", "ind_total", r)) for r in radii]),
                        _row("% Construction", *[_fmt_pct(_pct_from("ind_construction", "ind_total", r)) for r in radii]),
                        _row("% Manufacturing", *[_fmt_pct(_pct_from("ind_manufacturing", "ind_total", r)) for r in radii]),
                        _row("% Wholesale Trade", *[_fmt_pct(_pct_from("ind_wholesale", "ind_total", r)) for r in radii]),
                        _row("% Retail Trade", *[_fmt_pct(_pct_from("ind_retail", "ind_total", r)) for r in radii]),
                        _row("% Transportation, Warehousing & Utilities", *[_fmt_pct(_pct_from("ind_transport_util", "ind_total", r)) for r in radii]),
                        _row("% Information", *[_fmt_pct(_pct_from("ind_information", "ind_total", r)) for r in radii]),
                        _row("% Finance, Insurance & Real Estate", *[_fmt_pct(_pct_from("ind_finance_re", "ind_total", r)) for r in radii]),
                        _row("% Professional, Scientific & Management", *[_fmt_pct(_pct_from("ind_professional", "ind_total", r)) for r in radii]),
                        _row("% Education, Health Care & Social Assistance", *[_fmt_pct(_pct_from("ind_edu_health", "ind_total", r)) for r in radii]),
                        _row("% Arts, Entertainment, Accommodation & Food", *[_fmt_pct(_pct_from("ind_arts_food", "ind_total", r)) for r in radii]),
                        _row("% Other Services", *[_fmt_pct(_pct_from("ind_other_svc", "ind_total", r)) for r in radii]),
                        _row("% Public Administration", *[_fmt_pct(_pct_from("ind_public_admin", "ind_total", r)) for r in radii]),
                    ],
                    key=lambda r: _parse_pct(r["r1"]),
                    reverse=True,
                ),
            },
            {
                "heading": "Race & Ethnicity",
                "rows": [
                    _row(
                        "% Non-Hispanic White",
                        *[_fmt_pct(_pct_from("non_hispanic_white", "total_race", r)) for r in radii],
                    ),
                    _row(
                        "% Hispanic or Latino",
                        *[_fmt_pct(_pct_from("hispanic", "total_race", r)) for r in radii],
                    ),
                    _row(
                        "% Black or African American",
                        *[_fmt_pct(_pct_from("black", "total_race", r)) for r in radii],
                    ),
                    _row(
                        "% Asian",
                        *[_fmt_pct(_pct_from("asian", "total_race", r)) for r in radii],
                    ),
                    _row(
                        "% Other / Multiracial",
                        *[_fmt_pct(_other_race_pct(r)) for r in radii],
                    ),
                ],
            },
            {
                "heading": "Language",
                "rows": [
                    _row(
                        "% Limited English Proficiency (Households)",
                        *[_fmt_pct(_limited_english_pct(r)) for r in radii],
                    ),
                ],
            },
        ]
    }


def fetch_area_weighted(
    block_groups_by_radius: dict[str, list[dict]],
    api_key: str,
    acs_year: int = 2023,
) -> dict[str, Any]:
    """
    Fetch ACS data for all block groups across three radii and return
    the aggregated demographics context dict.

    Args:
        block_groups_by_radius: Dict keyed by radius label ("1mi", "5mi", "10mi"),
            each containing a list of {geoid, intersection_pct} dicts.
        api_key: Census API key.
        acs_year: ACS 5-year vintage end year (default 2023 → 2019–2023).

    Returns:
        Full demographics dict matching the mock_data.py structure.
    """
    if not api_key:
        return {
            "available": False,
            "flag": "Census API key not configured (CENSUS_API_KEY).",
            "note": "",
            "acs_vintage": "",
            "groups": [],
        }

    # Collect all unique GEOIDs across all radii
    all_geoids: set[str] = set()
    for bg_list in block_groups_by_radius.values():
        for bg in bg_list:
            all_geoids.add(bg["geoid"])

    # Fetch (with cache) for each unique GEOID.
    # On the first network error, abort immediately — all remaining uncached
    # requests will fail the same way, and waiting them out wastes minutes.
    acs_data: dict[str, dict[str, Any]] = {}
    failed_geoids: list[str] = []
    network_error: str | None = None

    for geoid in all_geoids:
        try:
            result = _fetch_with_cache(geoid, api_key, acs_year)
        except _NetworkError as exc:
            network_error = str(exc)
            log.warning("Census ACS network unreachable — aborting remaining %d fetches", len(all_geoids) - len(acs_data) - 1)
            # Count all remaining un-fetched GEOIDs as failed
            failed_geoids = [g for g in all_geoids if g not in acs_data and g != geoid]
            failed_geoids.insert(0, geoid)
            break
        if result is not None:
            acs_data[geoid] = result
        else:
            failed_geoids.append(geoid)

    # Any missing block groups — network error or API no-data — make the
    # area-weighted aggregation unreliable. Suppress entirely rather than
    # showing numbers derived from incomplete coverage.
    if not acs_data or failed_geoids:
        if network_error:
            flag = f"Census ACS API unreachable — demographic data suppressed."
        elif not acs_data:
            flag = "Census ACS returned no data for this area."
        else:
            flag = (
                f"Census ACS data incomplete ({len(failed_geoids)} of {len(all_geoids)} "
                "block groups unavailable) — demographic data suppressed."
            )
        return {
            "available": False,
            "flag": flag,
            "note": "",
            "acs_vintage": "",
            "groups": [],
        }

    # All block groups fetched successfully — aggregate for each radius
    radii_order = ["1mi", "5mi", "10mi"]
    aggs: dict[str, dict[str, Any]] = {}
    for label in radii_order:
        bg_list = block_groups_by_radius.get(label, [])
        agg = _aggregate(bg_list, acs_data)
        # Compute mean_travel_time_min if not already set
        if "mean_travel_time_min" not in agg:
            tt = agg.get("total_travel_time")
            tw = agg.get("total_workers")
            agg["mean_travel_time_min"] = (tt / tw) if (tt and tw) else None
        aggs[label] = agg

    rows_data = _build_demographics_rows(aggs)
    vintage_start = acs_year - 4

    from plinth.db.registry import register_api_source
    register_api_source(
        _DATASET, version=f"{vintage_start}–{acs_year} ACS 5-Year",
        update_frequency="on-demand", notes="Block group level; area-weighted",
    )

    return {
        "available": True,
        "note": (
            "Area-weighted block group intersections. "
            "Straight-line radius buffers — physical barriers not accounted for."
        ),
        "acs_vintage": f"{vintage_start}–{acs_year} ACS 5-Year Estimates",
        "groups": rows_data["groups"],
        # Expose raw aggregates for use by build_context (e.g. population_5mi)
        "_aggs": aggs,
    }


def fetch_area_weighted_local(
    block_groups_by_radius: dict[str, list[dict]],
    acs_year: int = 2023,
) -> dict[str, Any]:
    """
    Fetch ACS data from the local ``acs_block_group_data`` table and return
    the aggregated demographics context dict.  No Census API key required.

    Identical output structure to ``fetch_area_weighted()``.

    Args:
        block_groups_by_radius: Dict keyed by radius label ("1mi", "5mi", "10mi"),
            each containing a list of {geoid, intersection_pct} dicts.
        acs_year: ACS 5-year vintage end year (default 2023 → 2019–2023).
    """
    from plinth.db.connection import get_connection

    all_geoids: set[str] = set()
    for bg_list in block_groups_by_radius.values():
        for bg in bg_list:
            all_geoids.add(bg["geoid"])

    if not all_geoids:
        return {
            "available": False,
            "flag": "No block groups found near this location.",
            "note": "", "acs_vintage": "", "groups": [],
        }

    geoid_list = sorted(all_geoids)
    placeholders = ",".join(["%s"] * len(geoid_list))

    # All data columns are exactly the ACS_VARS field names
    field_cols = ", ".join(_VAR_NAMES)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT geoid, {field_cols} FROM acs_block_group_data "
                f"WHERE geoid IN ({placeholders}) AND acs_year = %s",
                geoid_list + [acs_year],
            )
            rows = cur.fetchall()

    col_names = ["geoid"] + _VAR_NAMES
    acs_data: dict[str, dict[str, Any]] = {}
    for row in rows:
        row_dict = dict(zip(col_names, row))
        geoid = row_dict.pop("geoid")
        acs_data[geoid] = {
            k: float(v) if v is not None else None
            for k, v in row_dict.items()
        }

    if not acs_data:
        return {
            "available": False,
            "flag": (
                "Census ACS data not loaded for this area "
                "(no matching block groups in local database)."
            ),
            "note": "", "acs_vintage": "", "groups": [],
        }

    radii_order = ["1mi", "5mi", "10mi"]
    aggs: dict[str, dict[str, Any]] = {}
    for label in radii_order:
        bg_list = block_groups_by_radius.get(label, [])
        aggs[label] = _aggregate(bg_list, acs_data)

    rows_data = _build_demographics_rows(aggs)
    vintage_start = acs_year - 4

    return {
        "available": True,
        "note": (
            "Area-weighted block group intersections. "
            "Straight-line radius buffers — physical barriers not accounted for."
        ),
        "acs_vintage": f"{vintage_start}–{acs_year} ACS 5-Year Estimates",
        "groups": rows_data["groups"],
        "_aggs": aggs,
    }
