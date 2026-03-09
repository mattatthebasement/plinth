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
    # Population & Age
    "B01003_001E": "total_population",
    "B01002_001E": "median_age",
    "B25010_001E": "avg_household_size",
    # Households & Income
    "B11001_001E": "total_households",
    "B19013_001E": "median_hhi",
    "B19301_001E": "per_capita_income",
    "B17001_002E": "below_poverty_count",
    "B17001_001E": "poverty_universe",
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
    "B08136_001E": "total_travel_time",
    "B08101_001E": "total_workers",
    "B08301_003E": "drive_alone",
    "B08301_001E": "commute_universe",
    "B08301_021E": "work_from_home",
    "B23025_005E": "unemployed",
    "B23025_003E": "labor_force",
    "B23025_002E": "in_labor_force",
    "B23025_001E": "labor_force_universe",
    # Race & Ethnicity
    "B03002_001E": "total_race",
    "B03002_003E": "non_hispanic_white",
    "B03002_012E": "hispanic",
    "B03002_004E": "black",
    "B03002_006E": "asian",
    # Language
    "B16002_001E": "language_universe",
    "B16002_004E": "limited_english_spanish",
    "B16002_007E": "limited_english_other_indo",
    "B16002_010E": "limited_english_asian",
    "B16002_013E": "limited_english_other",
}

_VAR_CODES = list(ACS_VARS.keys())
_VAR_NAMES = list(ACS_VARS.values())


def _cache_key(year: int, geoid: str) -> str:
    return f"{_DATASET}:{year}:{geoid}"


def _parse_geoid(geoid: str) -> tuple[str, str, str, str]:
    """Split 12-digit GEOID into (state, county, tract, block_group)."""
    return geoid[:2], geoid[2:5], geoid[5:11], geoid[11:12]


def _fetch_block_group(
    state: str,
    county: str,
    tract: str,
    block_group: str,
    api_key: str,
    acs_year: int,
) -> dict[str, Any] | None:
    """Fetch ACS data for a single block group. Returns field dict or None on error."""
    get_str = "NAME," + ",".join(_VAR_CODES)
    url = (
        f"{_BASE}/{acs_year}/acs/acs5"
        f"?get={get_str}"
        f"&for=block+group:{block_group}"
        f"&in=state:{state}%20county:{county}%20tract:{tract}"
        f"&key={api_key}"
    )
    try:
        resp = httpx.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        log.warning("Census ACS fetch failed for %s%s%s%s: %s", state, county, tract, block_group, exc)
        return None

    if not data or len(data) < 2:
        return None

    # data[0] is header row, data[1] is the values row
    header = data[0]
    values = data[1]
    row = dict(zip(header, values))

    result: dict[str, float | None] = {}
    for code, field in ACS_VARS.items():
        raw = row.get(code)
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
    """Return ACS field dict for a GEOID, using query_cache."""
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
        "below_poverty_count", "poverty_universe",
        "public_assistance_count", "public_assistance_universe",
        "owner_occupied", "renter_occupied", "tenure_universe",
        "edu_universe", "hs_diploma", "ged", "some_college_lt1",
        "some_college_ge1", "associates", "bachelors", "masters",
        "professional", "doctorate",
        "total_workers", "drive_alone", "commute_universe", "work_from_home",
        "unemployed", "labor_force", "in_labor_force", "labor_force_universe",
        "total_race", "non_hispanic_white", "hispanic", "black", "asian",
        "language_universe", "limited_english_spanish",
        "limited_english_other_indo", "limited_english_asian",
        "limited_english_other",
    ]

    # Weighted average fields (use total_population as weight)
    avg_fields = [
        "median_age", "avg_household_size",
        "median_hhi", "per_capita_income",
        "median_home_value", "median_gross_rent", "median_year_built",
        "total_travel_time",  # aggregated then divided by total_workers
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

    # Mean travel time = total_travel_time / total_workers
    tt = count_sums.get("total_travel_time")
    tw = count_sums.get("total_workers")
    if tt and tw:
        agg["mean_travel_time_min"] = tt / tw
    else:
        agg["mean_travel_time_min"] = None

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
                    _decimal_row("Median Age", "median_age"),
                    _decimal_row("Average Household Size", "avg_household_size", 2),
                ],
            },
            {
                "heading": "Households & Income",
                "rows": [
                    _count_row("Total Households", "total_households"),
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
                        "% Limited English Proficiency",
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

    # Fetch (with cache) for each unique GEOID
    acs_data: dict[str, dict[str, Any]] = {}
    for geoid in all_geoids:
        result = _fetch_with_cache(geoid, api_key, acs_year)
        if result is not None:
            acs_data[geoid] = result

    if not acs_data:
        return {
            "available": False,
            "flag": "Census ACS data unavailable for this area.",
            "note": "",
            "acs_vintage": "",
            "groups": [],
        }

    # Aggregate for each radius
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
