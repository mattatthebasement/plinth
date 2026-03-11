"""Report context builder — assembles all query results into the template context dict."""

from __future__ import annotations

import base64
import io
import logging
import math
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import matplotlib.ticker as mticker
import numpy as np
from timezonefinder import TimezoneFinder

from astral import LocationInfo, Observer
from astral.sun import sun, sunrise as astral_sunrise, sunset as astral_sunset, azimuth, elevation

from plinth import query as q_module

log = logging.getLogger(__name__)

_TF = TimezoneFinder()

_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

_DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

# FEMA NRI hazard score column → display name
_HAZARD_NAMES: dict[str, str] = {
    "avln_score": "Avalanche",
    "cfld_score": "Coastal Flooding",
    "cwav_score": "Cold Wave",
    "drgt_score": "Drought",
    "erqk_score": "Earthquake",
    "hail_score": "Hail",
    "hwav_score": "Heat Wave",
    "hrcn_score": "Hurricane",
    "istm_score": "Ice Storm",
    "lnds_score": "Landslide",
    "ltng_score": "Lightning",
    "rfld_score": "Riverine Flooding",
    "swnd_score": "Strong Wind",
    "trnd_score": "Tornado",
    "tsun_score": "Tsunami",
    "vlcn_score": "Volcanic Activity",
    "wfir_score": "Wildfire",
    "wntw_score": "Winter Weather",
}


# ── Helpers ──────────────────────────────────────────────────────────────────

def _pga_class(pgam_g: float | None) -> str:
    if pgam_g is None:
        return "Unknown"
    if pgam_g < 0.05:
        return "Very Low"
    if pgam_g < 0.15:
        return "Low"
    if pgam_g < 0.30:
        return "Moderate"
    if pgam_g < 0.60:
        return "High"
    return "Very High"


def _whp_class(whp_value: int | None) -> str:
    if whp_value is None:
        return "Unknown"
    if whp_value < 2250:
        return "Very Low"
    if whp_value < 9000:
        return "Low"
    if whp_value < 36000:
        return "Moderate"
    if whp_value < 144000:
        return "High"
    return "Very High"


def _monthly_values(monthly_list: list[dict] | None) -> list[float | None]:
    """Extract plain list of values from [{month, value}, ...] NOAA format."""
    if not monthly_list:
        return [None] * 12
    return [entry.get("value") for entry in monthly_list]


def _compute_freeze_thaw_days(
    tmax_list: list[float | None],
    tmin_list: list[float | None],
) -> int:
    """Count days in months where tmax > 32°F AND tmin < 32°F."""
    total = 0
    for i, (mx, mn) in enumerate(zip(tmax_list, tmin_list)):
        if mx is not None and mn is not None and mx > 32.0 and mn < 32.0:
            total += _DAYS_IN_MONTH[i]
    return total


def _get_local_tz(lat: float, lon: float) -> ZoneInfo:
    """Return the IANA timezone for a lat/lon, falling back to UTC offset."""
    tz_name = _TF.timezone_at(lat=lat, lng=lon)
    if tz_name:
        return ZoneInfo(tz_name)
    # Fallback: crude UTC offset from longitude
    offset_hours = round(lon / 15.0)
    return timezone(timedelta(hours=offset_hours))


def _compact_time(dt) -> str:
    """Format a datetime as '7:34a' or '5:32p' — compact AM/PM."""
    raw = dt.strftime("%-I:%M%p")  # e.g. "7:34AM"
    return raw[:-1].lower()  # "7:34a"


def _sunrise_sunset(lat: float, lon: float) -> tuple[list[str], list[str], list[str], str]:
    """Compute sunrise/sunset strings for the 15th of each month in local time.

    Returns (sunrises, sunsets, day_lengths, tz_abbrev).
    """
    local_tz = _get_local_tz(lat, lon)
    obs = Observer(latitude=lat, longitude=lon)
    sunrises, sunsets, day_lengths = [], [], []
    tz_abbrevs: set[str] = set()
    for month in range(1, 13):
        try:
            sr = astral_sunrise(obs, date=date(2025, month, 15)).astimezone(local_tz)
            ss = astral_sunset(obs, date=date(2025, month, 15)).astimezone(local_tz)
            sunrises.append(_compact_time(sr))
            sunsets.append(_compact_time(ss))
            # Use time-of-day only (astral may return previous day's sunset)
            day_min = (ss.hour * 60 + ss.minute) - (sr.hour * 60 + sr.minute)
            day_lengths.append(f"{day_min // 60}:{day_min % 60:02d}")
            tz_abbrevs.add(sr.strftime("%Z"))
        except Exception:
            sunrises.append("")
            sunsets.append("")
            day_lengths.append("")
    # Join abbreviations in a stable order (standard before daylight)
    tz_abbrev = "/".join(sorted(tz_abbrevs))
    return sunrises, sunsets, day_lengths, tz_abbrev


# ── Solar chart generation ───────────────────────────────────────────────────

# Representative dates: 21st of solstice/equinox months + a few intermediates
_SUN_PATH_DATES = [
    (date(2025, 6, 21), "Jun 21", "#d32f2f"),    # summer solstice
    (date(2025, 3, 20), "Mar 20", "#1976d2"),     # spring equinox
    (date(2025, 12, 21), "Dec 21", "#388e3c"),    # winter solstice
]


def _sun_path_polar_chart(lat: float, lon: float) -> str | None:
    """Generate a polar sun path diagram. Returns base64 PNG data URI."""
    local_tz = _get_local_tz(lat, lon)
    obs = Observer(latitude=lat, longitude=lon)

    fig, ax = plt.subplots(figsize=(2.8, 2.8), subplot_kw={"projection": "polar"})

    # Polar setup: 0° = North at top, clockwise azimuth
    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)

    # Radial axis = zenith angle (90 - altitude) so horizon is outer ring
    ax.set_rlim(0, 90)
    ax.set_yticks([0, 15, 30, 45, 60, 75, 90])
    ax.set_yticklabels(["90°", "75°", "60°", "45°", "30°", "15°", "0°"], fontsize=5, color="#666")
    ax.set_xticks(np.radians([0, 45, 90, 135, 180, 225, 270, 315]))
    ax.set_xticklabels(["N", "NE", "E", "SE", "S", "SW", "W", "NW"], fontsize=6, color="#444")
    ax.grid(True, linewidth=0.3, color="#ccc")

    for dt_date, label, color in _SUN_PATH_DATES:
        azimuths = []
        zenith_angles = []

        # Compute sun position every 10 minutes through the day
        start = datetime(dt_date.year, dt_date.month, dt_date.day, 0, 0, tzinfo=local_tz)
        for minutes in range(0, 24 * 60, 10):
            dt = start + timedelta(minutes=minutes)
            dt_utc = dt.astimezone(timezone.utc)
            try:
                alt = elevation(obs, dt_utc)
                az = azimuth(obs, dt_utc)
            except Exception:
                continue
            if alt > 0:
                azimuths.append(math.radians(az))
                zenith_angles.append(90 - alt)

        if azimuths:
            ax.plot(azimuths, zenith_angles, color=color, linewidth=1.2, label=label)

    # Hour markers and labels on all three curves
    for dt_date, _, color in _SUN_PATH_DATES:
        start = datetime(dt_date.year, dt_date.month, dt_date.day, 0, 0, tzinfo=local_tz)
        for hour in range(5, 21):
            dt = start + timedelta(hours=hour)
            dt_utc = dt.astimezone(timezone.utc)
            try:
                alt = elevation(obs, dt_utc)
                az = azimuth(obs, dt_utc)
            except Exception:
                continue
            if alt > 0:
                ax.plot(math.radians(az), 90 - alt, "o", color=color, markersize=2)
                if hour in (6, 8, 10, 12, 14, 16, 18, 20):
                    local_hr = dt.strftime("%-I%p").lower()
                    ax.annotate(
                        local_hr, (math.radians(az), 90 - alt),
                        fontsize=4.5, color="#555", ha="center", va="bottom",
                        xytext=(0, 3), textcoords="offset points",
                    )

    ax.legend(loc="upper right", fontsize=5.5, framealpha=0.9,
              bbox_to_anchor=(1.28, 1.08))
    ax.set_title("Sun Path Diagram", fontsize=7, pad=10, color="#333")

    plt.tight_layout(pad=0.3)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return "data:image/png;base64," + base64.b64encode(buf.read()).decode("ascii")


def _solar_altitude_chart(lat: float, lon: float) -> str | None:
    """Generate a solar altitude (elevation vs time) chart. Returns base64 PNG data URI."""
    local_tz = _get_local_tz(lat, lon)
    obs = Observer(latitude=lat, longitude=lon)

    fig, ax = plt.subplots(figsize=(2.8, 2.8))

    for dt_date, label, color in _SUN_PATH_DATES:
        hours = []
        altitudes = []

        start = datetime(dt_date.year, dt_date.month, dt_date.day, 0, 0, tzinfo=local_tz)
        for minutes in range(0, 24 * 60, 10):
            dt = start + timedelta(minutes=minutes)
            dt_utc = dt.astimezone(timezone.utc)
            try:
                alt = elevation(obs, dt_utc)
            except Exception:
                continue
            if alt > -5:  # include a bit below horizon for context
                hours.append(dt.hour + dt.minute / 60.0)
                altitudes.append(max(alt, 0))

        if hours:
            ax.plot(hours, altitudes, color=color, linewidth=1.2, label=label)

    ax.axhline(y=0, color="#999", linewidth=0.5)
    ax.set_xlim(4, 22)
    ax.set_ylim(0, 90)
    ax.set_xlabel("Local Time", fontsize=6, color="#555")
    ax.set_ylabel("Solar Altitude (°)", fontsize=6, color="#555")
    ax.set_title("Solar Altitude", fontsize=7, color="#333")

    # Format x axis as hours
    ax.set_xticks([4, 6, 8, 10, 12, 14, 16, 18, 20])
    ax.set_xticklabels(["4am", "6am", "8am", "10am", "12pm", "2pm", "4pm", "6pm", "8pm"],
                        fontsize=5, rotation=45)
    ax.tick_params(axis="y", labelsize=5.5)
    ax.yaxis.set_major_locator(mticker.MultipleLocator(15))
    ax.grid(True, linewidth=0.3, color="#ddd")
    ax.legend(loc="upper right", fontsize=5.5, framealpha=0.9)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    plt.tight_layout(pad=0.3)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return "data:image/png;base64," + base64.b64encode(buf.read()).decode("ascii")


def _safe_query(name: str, fn, *args, fallback: dict, timings: dict | None = None, **kwargs) -> dict:
    """Call a query function; return fallback dict on any exception. Records elapsed time in timings."""
    t0 = time.perf_counter()
    try:
        result = fn(*args, **kwargs)
        if result is None:
            log.warning("Query %s returned None — using fallback", name)
            return fallback
        return result
    except Exception as exc:
        log.warning("Query %s failed: %s", name, exc)
        return fallback
    finally:
        if timings is not None:
            timings[name] = time.perf_counter() - t0


# ── Section builders ─────────────────────────────────────────────────────────

def _build_flood(flood_q: dict) -> dict:
    if not flood_q.get("available", False):
        return {
            "zone": "Unknown",
            "subtype": "",
            "sfha": False,
            "bfe_ft": None,
            "nfhl_date": "",
            "mapped": flood_q.get("mapped", False),
        }
    bfe = flood_q.get("bfe_ft")
    # FEMA NFHL uses -9999 as a sentinel for "BFE not established"
    if bfe is not None and bfe <= -9990:
        bfe = None
    return {
        "zone": flood_q.get("zone", "Unknown"),
        "subtype": flood_q.get("zone_subty", ""),
        "sfha": flood_q.get("sfha", False),
        "bfe_ft": bfe,
        "nfhl_date": flood_q.get("source_date", ""),
        "mapped": flood_q.get("mapped", True),
    }


def _build_seismic(seismic_q: dict, eq_q: dict) -> dict:
    pgam = seismic_q.get("pgam_g", 0) if seismic_q.get("available") else 0
    ss = seismic_q.get("ss_g", 0) if seismic_q.get("available") else 0
    s1 = seismic_q.get("s1_g", 0) if seismic_q.get("available") else 0
    return {
        "pgam_g": round(pgam or 0, 3),
        "ss_g": round(ss or 0, 3),
        "s1_g": round(s1 or 0, 3),
        "pga_class": _pga_class(pgam),
        "eq_count": eq_q.get("event_count", 0),
        "eq_max_mag": eq_q.get("max_magnitude"),
        "eq_years": eq_q.get("search_years", 50),
        "eq_radius_mi": eq_q.get("search_radius_mi", 50),
    }


def _build_wildfire(wf_q: dict) -> dict:
    if not wf_q.get("available", False):
        return {
            "whp_value": None,
            "whp_national_max": 144153,
            "whp_class": "Unknown",
            "vintage": "2023",
            "resolution_m": 270,
        }
    whp_val = wf_q.get("whp_value")
    return {
        "whp_value": whp_val,
        "whp_national_max": wf_q.get("whp_national_max", 144153),
        "whp_class": _whp_class(whp_val),
        "vintage": "2023",
        "resolution_m": wf_q.get("resolution_m", 270),
    }


_HYDRO_GROUP_LABELS: dict[str, str] = {
    "A": "A — High infiltration rate; low runoff potential (deep, well-drained sands and gravels)",
    "B": "B — Moderate infiltration rate; moderately well-drained",
    "C": "C — Slow infiltration rate; moderately fine to fine texture or impeding layer",
    "D": "D — Very slow infiltration rate; highest runoff potential (high clay, high water table, or shallow impervious layer)",
    "C/D": "C/D — Dual class: behaves as Group D when wet; can drain to Group C behavior with drainage improvements",
    "A/D": "A/D — Dual class: behaves as Group D when wet; drains to Group A behavior",
    "B/D": "B/D — Dual class: behaves as Group D when wet; drains to Group B behavior",
}


def _fmt_hydro_group(raw: str | None) -> str:
    """Return the hydrologic group letter(s) with an inline description."""
    if not raw:
        return "—"
    return _HYDRO_GROUP_LABELS.get(raw.strip(), raw.strip())


def _fmt_eng_rating(rating: str | None, limiters: list[str]) -> str:
    """Format an engineering suitability rating with optional limiting factors.

    Examples:
      "Not limited"
      "Very limited (limited by: depth to saturated zone, shrink-swell)"
    """
    if not rating:
        return "—"
    if not limiters:
        return rating
    limiter_str = ", ".join(l.lower() for l in limiters if l)
    return f"{rating} (limited by: {limiter_str})"


def _build_soil(soil_q: dict) -> dict:
    if not soil_q.get("available", False):
        return {
            "available": False,
            "muname": "",
            "mukey": "",
            "hydrologic_group": "",
            "hydrologic_group_code": None,
            "drainage_class": "",
            "slope_pct": None,
            "taxonomic_class": "",
            "dominant_component": "",
            "dominant_component_pct": None,
            "nearest_fallback": False,
            # Physical
            "flood_frequency": None,
            "water_table_depth_cm": None,
            "bedrock_depth_cm": None,
            # Farmland & water
            "land_capability_class": None,
            "available_water_storage_in": None,
            "erosion_hazard": None,
            # Engineering suitability
            "septic": "—",
            "dwellings_no_basement": "—",
            "dwellings_with_basement": "—",
            "local_roads": "—",
        }

    cointerp = soil_q.get("cointerp", {})

    def _eng(key: str, fallback_rating: str | None) -> str:
        ci = cointerp.get(key, {})
        rating = ci.get("rating") or fallback_rating
        limiters = ci.get("limiters", [])
        return _fmt_eng_rating(rating, limiters)

    return {
        "available": True,
        "muname": soil_q.get("muname", ""),
        "mukey": soil_q.get("mukey", ""),
        # Physical conditions
        "hydrologic_group": _fmt_hydro_group(soil_q.get("hydrologic_group")),
        "hydrologic_group_code": (soil_q.get("hydrologic_group") or "").strip() or None,
        "drainage_class": soil_q.get("drainage_class", ""),
        "slope_pct": soil_q.get("slope_pct"),
        "flood_frequency": soil_q.get("flood_frequency"),
        "water_table_depth_cm": soil_q.get("water_table_depth_cm"),
        "bedrock_depth_cm": soil_q.get("bedrock_depth_cm"),
        # Component
        "dominant_component": soil_q.get("dominant_component", ""),
        "dominant_component_pct": soil_q.get("dominant_component_pct"),
        # Farmland & water
        "land_capability_class": soil_q.get("land_capability_class"),
        "available_water_storage_in": soil_q.get("available_water_storage_in"),
        "erosion_hazard": soil_q.get("erosion_hazard"),
        # Engineering suitability (cointerp limiters preferred; muaggatt dominant as fallback)
        "septic": _eng("septic", soil_q.get("septic_rating")),
        "dwellings_no_basement": _eng("dwellings_no_basement", soil_q.get("dwellings_no_basement_rating")),
        "dwellings_with_basement": _eng("dwellings_with_basement", soil_q.get("dwellings_with_basement_rating")),
        "local_roads": _eng("local_roads", soil_q.get("local_roads_rating")),
        # Taxonomic classification
        "taxonomic_class": soil_q.get("taxonomic_class", ""),
        "nearest_fallback": "flag" in soil_q,
    }


def _build_air_quality(aqs_q: dict) -> dict:
    if not aqs_q.get("available", False):
        return {
            "available": False,
            "flag": aqs_q.get(
                "flag",
                aqs_q.get("error", "EPA AQS data unavailable for this location."),
            ),
        }
    pm25 = aqs_q.get("pm25", {})
    ozone = aqs_q.get("ozone", {})
    result: dict[str, Any] = {
        "available": True,
        "year": aqs_q.get("year"),
    }
    if pm25.get("available"):
        result["pm25_annual"] = round(pm25.get("arithmetic_mean", 0), 1)
        result["monitor_name"] = pm25.get("monitor_name", "—")
        result["monitor_id"] = pm25.get("monitor_id")
    if ozone.get("available"):
        # API returns ppm; convert to ppb for display
        mean_ppm = ozone.get("arithmetic_mean", 0)
        result["ozone_ppb"] = round(mean_ppm * 1000, 1)
        if not result.get("monitor_name"):
            result["monitor_name"] = ozone.get("monitor_name", "—")
        result["ozone_monitor_id"] = ozone.get("monitor_id")
    return result


def _nri_hazard_bar_chart(hazards: dict[str, float]) -> str | None:
    """
    Generate a horizontal bar chart for NRI hazard component scores.
    Returns a base64-encoded PNG data URI, or None if hazards is empty.

    Bars use a green→yellow→red gradient keyed to score (0=green, 50=yellow, 100=red).
    """
    if not hazards:
        return None

    labels = list(hazards.keys())
    scores = [hazards[k] for k in labels]
    sorted_pairs = sorted(zip(scores, labels), reverse=True)
    scores_sorted, labels_sorted = zip(*sorted_pairs)

    n = len(labels_sorted)
    bar_height = 0.32
    fig_height = max(2.0, n * 0.26 + 0.5)
    fig, ax = plt.subplots(figsize=(5.5, fig_height))

    # Build per-bar colors from a green→yellow→red colormap
    cmap = mcolors.LinearSegmentedColormap.from_list(
        "nri_gradient",
        [(0.0, "#2e7d32"), (0.5, "#f9a825"), (1.0, "#c62828")],
    )
    colors = [cmap(s / 100.0) for s in scores_sorted]

    bars = ax.barh(
        range(n),
        scores_sorted,
        height=bar_height,
        color=colors,
        edgecolor="none",
    )

    # Score labels at right tip of each bar
    for bar, score in zip(bars, scores_sorted):
        ax.text(
            bar.get_width() + 0.8,
            bar.get_y() + bar.get_height() / 2,
            f"{score:.1f}",
            va="center",
            ha="left",
            fontsize=7,
            color="#333333",
        )

    ax.set_yticks(range(n))
    ax.set_yticklabels(labels_sorted, fontsize=7.5)
    ax.set_xlim(0, 110)
    ax.set_xlabel("FEMA NRI Score (0–100 percentile)", fontsize=7, color="#555555")
    ax.tick_params(axis="x", labelsize=7, colors="#555555")
    ax.tick_params(axis="y", colors="#333333")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.xaxis.grid(True, linestyle="--", linewidth=0.4, color="#dddddd", zorder=0)
    ax.set_axisbelow(True)

    plt.tight_layout(pad=0.4)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return "data:image/png;base64," + base64.b64encode(buf.read()).decode("ascii")


def _build_fema_nri(nri_q: dict) -> dict:
    if not nri_q.get("available", False):
        return {
            "tract_id": nri_q.get("tract_id", ""),
            "risk_score": None,
            "risk_ratng": "N/A",
            "hazards": {},
        }
    # The query returns hazard_scores keyed by display name
    hazard_scores_raw = nri_q.get("hazard_scores", {})
    hazards = {
        name: round(score, 1)
        for name, score in hazard_scores_raw.items()
        if score is not None and score > 0
    }
    raw_score = nri_q.get("risk_score")
    return {
        "tract_id": nri_q.get("tract_id", ""),
        "risk_score": round(raw_score, 1) if raw_score is not None else None,
        "risk_ratng": nri_q.get("risk_ratng", ""),
        "hazards": hazards,
        "hazard_chart": _nri_hazard_bar_chart(hazards),
    }


def _build_elevation(elev_q: dict) -> dict:
    if not elev_q.get("available", False):
        return {"elevation_m": None, "elevation_ft": None, "resolution_m": 10.0}
    elev_m = elev_q.get("elevation_m")
    return {
        "elevation_m": elev_m,
        "elevation_ft": round(elev_m * 3.28084, 1) if elev_m is not None else None,
        "resolution_m": elev_q.get("resolution_m", 10.0),
    }


def _build_slope(slope_q: dict) -> dict:
    if not slope_q.get("available", False):
        return {"mean_slope_pct": None, "max_slope_pct": None, "radius_m": 100}
    return {
        "mean_slope_pct": slope_q.get("mean_slope_pct"),
        "max_slope_pct": slope_q.get("max_slope_pct"),
        "radius_m": slope_q.get("radius_m", 100),
    }


def _build_land_cover(lc_q: dict) -> dict:
    if not lc_q.get("available", False):
        return {
            "dominant_class": "",
            "dominant_class_code": None,
            "impervious_pct_estimate": 0,
            "radius_m": 500,
            "distribution": [],
        }
    return {
        "dominant_class": lc_q.get("dominant_class", ""),
        "dominant_class_code": lc_q.get("dominant_class_code"),
        "impervious_pct_estimate": lc_q.get("impervious_pct_estimate", 0),
        "radius_m": lc_q.get("radius_m", 500),
        "distribution": [
            {"class": k, "pct": v}
            for k, v in lc_q.get("class_distribution_pct", {}).items()
        ],
    }


def _build_hydro(hydro_q: dict) -> dict:
    if not hydro_q.get("available", False):
        return {"waterbody": None, "flowline": None, "search_radius_mi": 5}

    def _feature(feat: dict | None) -> dict | None:
        if feat is None:
            return None
        return {
            "name": feat.get("gnis_name") or "Unnamed",
            "type": feat.get("ftype", ""),
            "distance_mi": feat.get("distance_mi"),
        }

    return {
        "waterbody": _feature(hydro_q.get("waterbody")),
        "flowline": _feature(hydro_q.get("flowline")),
        "search_radius_mi": 5,
    }


def _build_climate(noaa_q: dict, nasa_q: dict) -> dict:
    if not noaa_q.get("available", False):
        base = {
            "station_name": "",
            "station_id": "",
            "distance_mi": None,
            "period": "1991–2020",
            "months": _MONTHS,
            "tmax_f": [None] * 12,
            "tmin_f": [None] * 12,
            "prcp_in": [None] * 12,
            "snow_in": [None] * 12,
            "hdd_annual": None,
            "cdd_annual": None,
            "rh_annual_pct": None,
            "freeze_thaw_days": None,
        }
        if nasa_q.get("available"):
            rh = nasa_q.get("rel_humidity", {})
            base["rh_annual_pct"] = round(rh.get("annual")) if rh.get("annual") is not None else None
        return base

    tmax_f = _monthly_values(noaa_q.get("tmax_f"))
    tmin_f = _monthly_values(noaa_q.get("tmin_f"))
    prcp_in = _monthly_values(noaa_q.get("prcp_in"))
    snow_in = _monthly_values(noaa_q.get("snow_in"))
    hdd_monthly = _monthly_values(noaa_q.get("heating_degree_days"))
    cdd_monthly = _monthly_values(noaa_q.get("cooling_degree_days"))

    hdd_annual = int(sum(v for v in hdd_monthly if v is not None))
    cdd_annual = int(sum(v for v in cdd_monthly if v is not None))
    freeze_thaw = _compute_freeze_thaw_days(tmax_f, tmin_f)

    rh_annual_pct = None
    if nasa_q.get("available"):
        rh = nasa_q.get("rel_humidity", {})
        ann = rh.get("annual")
        if ann is not None:
            rh_annual_pct = round(ann)

    result: dict[str, Any] = {
        "station_name": noaa_q.get("station_name", ""),
        "station_id": noaa_q.get("station_id", ""),
        "distance_mi": noaa_q.get("distance_mi"),
        "period": "1991–2020",
        "months": _MONTHS,
        "tmax_f": tmax_f,
        "tmin_f": tmin_f,
        "prcp_in": prcp_in,
        "snow_in": snow_in,
        "hdd_annual": hdd_annual,
        "cdd_annual": cdd_annual,
        "rh_annual_pct": rh_annual_pct,
        "freeze_thaw_days": freeze_thaw,
    }
    return result


def _build_solar(nasa_q: dict, lat: float, lon: float) -> dict:
    sunrises, sunsets, day_lengths, tz_abbrev = _sunrise_sunset(lat, lon)

    # Generate sun path charts
    sun_path_chart = _sun_path_polar_chart(lat, lon)
    altitude_chart = _solar_altitude_chart(lat, lon)

    if not nasa_q.get("available", False):
        return {
            "peak_sun_hours": None,
            "annual_ghi_kwh_m2_day": None,
            "latitude": lat,
            "months": _MONTHS,
            "sunrise": sunrises,
            "sunset": sunsets,
            "day_length": day_lengths,
            "tz_abbrev": tz_abbrev,
            "ghi_monthly": [None] * 12,
            "sun_path_chart": sun_path_chart,
            "altitude_chart": altitude_chart,
        }

    solar = nasa_q.get("solar_kwh_m2_day", {})
    annual_ghi = solar.get("annual")
    monthly_ghi = solar.get("monthly", [None] * 12)

    return {
        "peak_sun_hours": annual_ghi,
        "annual_ghi_kwh_m2_day": annual_ghi,
        "latitude": lat,
        "months": _MONTHS,
        "sunrise": sunrises,
        "sunset": sunsets,
        "day_length": day_lengths,
        "tz_abbrev": tz_abbrev,
        "ghi_monthly": monthly_ghi,
        "sun_path_chart": sun_path_chart,
        "altitude_chart": altitude_chart,
    }


def _build_infrastructure(fcc_q: dict) -> dict:
    providers = []
    if fcc_q.get("available", False):
        for p in fcc_q.get("providers", []):
            providers.append({
                "provider": p.get("brand_name", ""),
                "technology": p.get("technology", ""),
                "max_down_mbps": p.get("max_download_mbps"),
                "max_up_mbps": p.get("max_upload_mbps"),
            })
    return {
        "broadband": providers,
        "road_note": "Road access data not yet available.",
        "transit_note": "Transit proximity data not yet available.",
        "water_sewer_note": (
            "Verify water and sewer service availability directly with local utility providers."
        ),
    }


def _build_iecc(iecc_q: dict) -> tuple[str, str]:
    """Return (iecc_zone, iecc_description)."""
    if not iecc_q.get("available", False):
        return "", ""
    label = iecc_q.get("zone_label", "")
    description = iecc_q.get("zone_description", "")
    # Extract numeric zone — label might be "3", "3A", "Mixed-Humid", etc.
    zone_number = ""
    for ch in label:
        if ch.isdigit():
            zone_number += ch
        else:
            break
    if not zone_number:
        zone_number = label
    return zone_number, description


def _build_exec_flags(
    flood: dict,
    seismic: dict,
    wildfire: dict,
    noaa_q: dict,
) -> list[str]:
    flags: list[str] = []

    # Flood
    zone = flood.get("zone", "")
    if zone:
        sfha = flood.get("sfha", False)
        if sfha:
            flags.append(f"FEMA Flood Zone {zone} — Special Flood Hazard Area.")
        else:
            flags.append(f"FEMA Flood Zone {zone} — area of minimal flood hazard per NFHL mapping.")
    else:
        flags.append("FEMA flood zone data unavailable for this location.")

    # Seismic
    pgam = seismic.get("pgam_g", 0)
    pga_cls = seismic.get("pga_class", "Unknown")
    flags.append(f"Seismic PGA {pgam:.3f}g — {pga_cls} seismic hazard. See Section 2 for details.")

    # Wildfire
    whp = wildfire.get("whp_value")
    whp_max = wildfire.get("whp_national_max", 144153)
    whp_cls = wildfire.get("whp_class", "Unknown")
    if whp is not None:
        flags.append(
            f"Wildfire Hazard Potential: {whp_cls} ({whp:,} / {whp_max:,} national index)."
        )
    else:
        flags.append("Wildfire Hazard Potential data unavailable.")

    # NOAA station distance flag
    if noaa_q.get("available") and noaa_q.get("flag"):
        dist = noaa_q.get("distance_mi", "")
        flags.append(
            f"NOAA station {dist} mi away — values may not reflect site microclimate."
        )

    return flags


def _build_risk_summary(
    flood: dict,
    seismic: dict,
    wildfire: dict,
    soil: dict,
    air_quality: dict,
    fema_nri: dict,
) -> list[dict]:
    rows: list[dict] = []

    # Flood
    zone = flood.get("zone", "Unknown")
    sfha = flood.get("sfha", False)
    flood_label = f"Zone {zone} — {'SFHA' if sfha else 'Minimal'}"
    rows.append({"category": "Flood Risk", "value": flood_label, "source": "FEMA NFHL"})

    # Seismic
    pgam = seismic.get("pgam_g", 0)
    rows.append({
        "category": "Seismic PGA",
        "value": f"{pgam:.3f}g (MCE\u1d63)",
        "source": "USGS NEHRP 2020",
    })

    # Wildfire
    whp = wildfire.get("whp_value")
    whp_max = wildfire.get("whp_national_max", 144153)
    whp_val_str = f"{whp:,} / {whp_max:,}" if whp is not None else "N/A"
    rows.append({"category": "Wildfire WHP", "value": whp_val_str, "source": "USDA Forest Service 2023"})

    # Soil — show unavailable clearly when no data within threshold
    if soil.get("available"):
        hyd_grp = soil.get("hydrologic_group_code", "") or ""
        drain = soil.get("drainage_class", "")
        soil_val = f"{hyd_grp} — {drain}" if hyd_grp or drain else "N/A"
    else:
        soil_val = "Unavailable — developed/urban area"
    rows.append({"category": "Hydrologic Group", "value": soil_val, "source": "USDA SSURGO"})

    # Air Quality — suppress entirely when unavailable (no API key or no monitor)
    if air_quality.get("available"):
        pm25 = air_quality.get("pm25_annual")
        if pm25 is not None:
            rows.append({
                "category": "Air Quality",
                "value": f"PM\u2082.\u2085 {pm25:.1f} \u00b5g/m\u00b3 (NAAQS: 9.0) · O\u2083 {air_quality.get('ozone_ppb', 'N/A')} ppb (NAAQS: 70)",
                "source": f"EPA AQS {air_quality.get('year', '')}",
            })

    # FEMA NRI
    nri_score = fema_nri.get("risk_score")
    nri_ratng = fema_nri.get("risk_ratng", "")
    nri_val = f"{nri_score:.1f} — {nri_ratng}" if nri_score is not None else "N/A"
    rows.append({"category": "FEMA NRI Score", "value": nri_val, "source": "FEMA National Risk Index"})

    return rows

_SOURCE_DISPLAY = {
    "census-acs":          ("Census ACS (Demographics)", "API → cache"),
    "census-tiger":        ("Census TIGER (Geometries)", "PostGIS"),
    "epa-aqs":             ("EPA AQS (Air Quality)", "API → cache"),
    "fcc-broadband":       ("FCC Broadband Availability", "PostGIS + API"),
    "fema-nfhl":           ("FEMA NFHL (Flood Zones)", "PostGIS"),
    "fema-nri":            ("FEMA National Risk Index", "PostGIS"),
    "iecc-climate-zones":  ("IECC Climate Zones", "PostGIS"),
    "nasa-power":          ("NASA POWER (Climate / Solar)", "API → cache"),
    "nhd-hr":              ("NHDPlus HR (Hydrography)", "PostGIS"),
    "nlcd":                ("NLCD (Land Cover)", "MinIO COG"),
    "noaa-normals":        ("NOAA Climate Normals", "PostGIS"),
    "usda-ssurgo":         ("USDA SSURGO (Soils)", "PostGIS"),
    "usda-whp":            ("USDA Wildfire Hazard Potential", "API"),
    "usgs-3dep":           ("USGS 3DEP (Elevation / Slope)", "MinIO COG"),
    "usgs-eq":             ("USGS Earthquake Catalog", "API → cache"),
    "usgs-seismic":        ("USGS Seismic Hazard (PGA)", "API → cache"),
}


def _build_sources_table() -> list[dict[str, str]]:
    """Read data_source_registry and return rows for the template."""
    from plinth.db.registry import get_all_sources

    rows: list[dict[str, str]] = []
    for src in get_all_sources():
        key = src["source_name"]
        display_name, storage = _SOURCE_DISPLAY.get(key, (key, "—"))
        version = src.get("dataset_version") or "—"
        refresh = src.get("update_frequency") or "—"
        rows.append({
            "name": display_name,
            "version": version,
            "refresh": refresh,
            "storage": storage,
        })
    return rows


# ── Main entry point ─────────────────────────────────────────────────────────

def build_context(
    lat: float,
    lon: float,
    address: str,
    city_state_zip: str,
    county: str = "",
    prepared_for: str = "",
    report_id: str | None = None,
    report_date: str | None = None,
) -> dict[str, Any]:
    """
    Build the full Jinja2 template context for a Plinth site intelligence report.

    All 16 query functions are called and their results transformed into the
    context structure expected by the report template. Every query is wrapped
    in try/except to ensure the report is always generated even when individual
    data sources are unavailable.
    """
    if report_id is None:
        report_id = f"PLN-{date.today().strftime('%Y%m%d')}-{uuid.uuid4().hex[:5].upper()}"
    if report_date is None:
        report_date = date.today().strftime("%B %-d, %Y")
    report_year = date.today().year

    timings: dict[str, float] = {}

    # ── Run all queries ───────────────────────────────────────────────────
    flood_q = _safe_query("flood_zone", q_module.query_flood_zone, lat, lon,
                          fallback={"available": False, "flag": "Flood zone data unavailable."}, timings=timings)
    fema_nri_q = _safe_query("fema_nri", q_module.query_fema_nri, lat, lon,
                             fallback={"available": False, "flag": "FEMA NRI data unavailable."}, timings=timings)
    iecc_q = _safe_query("iecc_zone", q_module.query_iecc_zone, lat, lon,
                         fallback={"available": False, "flag": "IECC zone data unavailable."}, timings=timings)
    bg_q = _safe_query("census_block_groups", q_module.query_census_block_groups, lat, lon,
                       fallback={"available": False, "flag": "Census block group data unavailable."}, timings=timings)
    soil_q = _safe_query("soil", q_module.query_soil, lat, lon,
                         fallback={"available": False, "flag": "Soil data unavailable."}, timings=timings)
    hydro_q = _safe_query("hydro", q_module.query_hydro, lat, lon,
                          fallback={"available": False, "flag": "Hydrography data unavailable."}, timings=timings)
    noaa_q = _safe_query("noaa_normals", q_module.query_noaa_normals, lat, lon,
                         fallback={"available": False, "flag": "NOAA climate data unavailable."}, timings=timings)
    elev_q = _safe_query("elevation", q_module.query_elevation, lat, lon,
                         fallback={"available": False, "flag": "Elevation data unavailable."}, timings=timings)
    slope_q = _safe_query("slope", q_module.query_slope, lat, lon,
                          fallback={"available": False, "flag": "Slope data unavailable."}, timings=timings)
    lc_q = _safe_query("land_cover", q_module.query_land_cover, lat, lon,
                       fallback={"available": False, "flag": "Land cover data unavailable."}, timings=timings)
    seismic_q = _safe_query("seismic_pga", q_module.query_seismic_pga, lat, lon,
                            fallback={"available": False, "flag": "Seismic data unavailable."}, timings=timings)
    wf_q = _safe_query("wildfire_whp", q_module.query_wildfire_whp, lat, lon,
                       fallback={"available": False, "flag": "Wildfire data unavailable."}, timings=timings)
    nasa_q = _safe_query("nasa_power", q_module.query_nasa_power, lat, lon,
                         fallback={"available": False, "flag": "NASA POWER data unavailable."}, timings=timings)
    eq_q = _safe_query("earthquakes", q_module.query_earthquakes, lat, lon,
                       fallback={"available": False, "flag": "Earthquake data unavailable.", "event_count": 0}, timings=timings)
    aqs_q = _safe_query("epa_aqs", q_module.query_epa_aqs, lat, lon,
                        fallback={"available": False, "flag": "EPA AQS data unavailable."}, timings=timings)
    fcc_q = _safe_query("fcc_broadband", q_module.query_fcc_broadband, lat, lon,
                        fallback={"available": False, "flag": "FCC broadband data unavailable."}, timings=timings)

    # ── Transform each section ────────────────────────────────────────────
    flood = _build_flood(flood_q)
    seismic = _build_seismic(seismic_q, eq_q)
    wildfire = _build_wildfire(wf_q)
    soil = _build_soil(soil_q)
    air_quality = _build_air_quality(aqs_q)
    fema_nri = _build_fema_nri(fema_nri_q)
    elevation = _build_elevation(elev_q)
    slope = _build_slope(slope_q)
    land_cover = _build_land_cover(lc_q)
    hydro = _build_hydro(hydro_q)
    climate = _build_climate(noaa_q, nasa_q)
    solar = _build_solar(nasa_q, lat, lon)
    infrastructure = _build_infrastructure(fcc_q)
    iecc_zone, iecc_description = _build_iecc(iecc_q)

    # ── Demographics ──────────────────────────────────────────────────────
    demographics: dict[str, Any]
    _t0_demo = time.perf_counter()
    if bg_q.get("available", False):
        try:
            from plinth.ingest.api.census_acs import fetch_area_weighted_local
            demographics = fetch_area_weighted_local(
                block_groups_by_radius=bg_q.get("radii", {}),
            )
        except Exception as exc:
            log.warning("Census ACS fetch failed: %s", exc)
            demographics = {
                "available": False,
                "flag": f"Census ACS data unavailable: {exc}",
                "note": "",
                "acs_vintage": "",
                "groups": [],
            }
    else:
        log.warning("Census block groups unavailable — skipping demographics")
        demographics = {
            "available": False,
            "flag": bg_q.get("flag", "Census block group data unavailable."),
            "note": "",
            "acs_vintage": "",
            "groups": [],
        }
    timings["demographics"] = time.perf_counter() - _t0_demo

    # ── population_5mi from demographics ─────────────────────────────────
    population_5mi = "N/A"
    if demographics.get("available") and "_aggs" in demographics:
        pop = demographics["_aggs"].get("5mi", {}).get("total_population")
        if pop is not None:
            population_5mi = f"{int(round(pop)):,}"

    # ── Executive summary ─────────────────────────────────────────────────
    exec_flags = _build_exec_flags(flood, seismic, wildfire, noaa_q)
    risk_summary = _build_risk_summary(flood, seismic, wildfire, soil, air_quality, fema_nri)

    # ── Maps ──────────────────────────────────────────────────────────────
    _t0_maps = time.perf_counter()
    try:
        from plinth.report.maps import fetch_all_maps, fetch_demographics_map_b64, fetch_demographics_closeup_map_b64
        maps = fetch_all_maps(lat, lon)
        maps["demographics"] = fetch_demographics_map_b64(lat, lon)
        maps["demographics_closeup"] = fetch_demographics_closeup_map_b64(lat, lon)
    except Exception as exc:
        log.warning("Map fetch failed: %s", exc)
        maps = {"cover": None, "terrain": None, "solar": None, "demographics": None}
    timings["maps"] = time.perf_counter() - _t0_maps

    # Strip internal key before returning
    demographics.pop("_aggs", None)

    return {
        # Site identity
        "address": address,
        "city_state_zip": city_state_zip,
        "county": county,
        "lat": lat,
        "lon": lon,
        "report_id": report_id,
        "report_date": report_date,
        "report_year": report_year,
        "prepared_for": prepared_for,

        # Section 1 — Executive Summary
        "exec_flags": exec_flags,
        "iecc_zone": iecc_zone,
        "iecc_description": iecc_description,
        "population_5mi": population_5mi,
        "risk_summary": risk_summary,

        # Section 2 — Environmental Risk
        "flood": flood,
        "seismic": seismic,
        "wildfire": wildfire,
        "soil": soil,
        "air_quality": air_quality,
        "fema_nri": fema_nri,

        # Section 3 — Physical Context
        "elevation": elevation,
        "slope": slope,
        "land_cover": land_cover,
        "hydro": hydro,

        # Section 4 — Climate & Weather
        "climate": climate,
        "iecc_note": "Local jurisdiction adoption may vary. Verify with AHJ.",

        # Section 5 — Solar
        "solar": solar,

        # Section 6 — Demographic & Market Context
        "demographics": demographics,

        # Section 7 — Infrastructure & Access
        "infrastructure": infrastructure,

        # Section 8 — Data Sources
        "sources": _build_sources_table(),

        # Maps (Mapbox Static Images, or None if unavailable)
        "maps": maps,

        # Timing data (stripped before PDF rendering)
        "_timings": timings,
    }
