# Water & Utility Infrastructure — Report Section Plan

**File:** `docs/plans/2026-03-13-Water-Plan.md`  
**Status:** Draft — pending approval

---

## Overview

Add **Section 7C: Water & Utility Infrastructure** to the Plinth report, using four already-ingested datasets:

| Table | Source | Rows |
|---|---|---|
| `sdwis_water_systems` | EPA SDWIS (Community Water Systems) | 96,913 |
| `water_system_boundaries` | EPA / OWRB service area polygons | 44,656 |
| `usgs_principal_aquifers` | USGS Principal Aquifers (national) | 4,637 |
| `usgs_groundwater_wells` | USGS NWIS monitoring wells | 914,330 |

This section targets two audiences:
- **Commercial developers**: utility availability, source reliability, connection capacity
- **AEC professionals**: groundwater depth for foundation design, dewatering risk, aquifer context for well permitting

---

## SDWIS System Types: CWS, NTNC, and TNC

EPA's Safe Drinking Water Information System classifies all public water systems into three types:

| Type | Full Name | Who It Serves | Example |
|---|---|---|---|
| **CWS** | Community Water System | Same population year-round | Municipal water utility, water district, private water company |
| **NTNC** | Non-Transient Non-Community | Same ≥25 people at least 6 months/year, but not residents | School, factory, hospital, office campus with its own well |
| **TNC** | Transient Non-Community | Transient/rotating populations | Gas station with a well, campground, highway rest stop |

**Why only CWS matters for Plinth:**
- CWS is the only type a commercial developer would connect to. It's the "utility" — the entity you call to apply for service, pay monthly bills, and extend mains.
- NTNC tells you that a *specific facility* chose not to connect to public water (or had no option) — it doesn't help answer "can I get water service for my development."
- TNC is irrelevant to site planning.

**What's actually in our data:**
Our `sdwis_water_systems` table has 96,913 records, all tagged CWS. The ingestor was written to also accept NTNC (`_INCLUDE_TYPES = {"CWS", "NTNC"}`), but the EPA ECHO bulk download does not appear to export NTNC/TNC records — the EPA ECHO REST API also returns 0 results for those types. NTNC and TNC systems are tracked in state drinking water programs but are not consistently in the ECHO bulk export.

**Recommendation: No change needed.** CWS-only is the correct scope for Plinth's use case. Even if NTNC data were available, it would only add noise to the "who is my water utility" question. The ingestor filter can remain as-is.

---

## Data Audit

### What We Have

**SDWIS / Service Boundaries**
- Community Water Systems (CWS) only — active systems (see above for why this is the right scope)
- Key fields: utility name, primary water source type, owner type, population served, service connections, 5-year violation count
- Service area polygons available for ~44,656 systems nationally
- Test coordinate (36.01769°N, 95.77990°W): inside **Broken Arrow Municipal Authority** (surface water, 116,330 pop served, 0 violations in 5yr)
- Adjacent systems: Wagoner Co. RWD #4 (0.6 mi), Wagoner Co. RWD #5 (2.6 mi), City of Tulsa (4.0 mi), Bixby PWA (4.1 mi)

**Source type codes:**
| Code | Meaning |
|---|---|
| `GW` | Groundwater |
| `SW` | Surface water (own intake) |
| `SWP` | Surface water purchased |
| `GWP` | Groundwater purchased |
| `GU` | Groundwater under direct surface-water influence |
| `GUP` | GU purchased |

**Owner type codes** (from EPA SDWIS Federal Reporting Services data dictionary):

| Code | Meaning | Count in our DB |
|---|---|---|
| P | Private | 54,301 |
| L | Local government | 31,898 |
| M | **Public/Private** (mixed ownership) | 2,848 |
| S | State or territorial government | 1,297 |
| N | Tribal government | 1,237 |
| F | Federal government | 896 |
| — | Unknown/not reported | 4,436 |

Note: codes A (private ancillary), B (private ancillary non-profit), Y (private for-profit), Z (private non-profit) exist in the SDWIS specification but do not appear in our loaded data.

**USGS Principal Aquifers**
- Named major aquifers only (USGS national layer) — does not capture state-level or local formations
- Aquifer types: unconsolidated sand/gravel, carbonate-rock, sandstone, semiconsolidated sand, igneous/metamorphic
- Test coordinate: overlies **"Other rocks"** (code 999 = bedrock not classified as a principal aquifer)
- Nearest named principal aquifer: **Ada-Vamoosa aquifer** (sandstone, 34.8 mi SE)

**USGS Groundwater Wells**
- 914,330 monitoring and supply wells nationally
- Well construction depth (`well_depth_ft`) available for ~841K wells
- Local aquifer formation code (`aquifer_cd`) and national aquifer code (`nat_aqfr_cd`) available for many wells
- Nearest wells to test coordinate: 3–7 miles, depths ranging 8–102 ft (alluvial/terrace deposits)

**Depth-to-Water (DTW) — Ingestor Bug & Fix:**
The `dtw_median_ft` column is NULL for all 914K wells due to a bug in `usgs_groundwater_wells.py`:
- `_download_state_stats()` is never called from `download()`
- It uses `statReportType: "site"` (invalid) and `stateCd` (not supported by the stats endpoint)

The stats endpoint at `https://waterservices.usgs.gov/nwis/stat/` only accepts `sites=` as a geographic filter — no state, county, or bbox filters. The fix is a two-step process per state:
1. Query `/nwis/site/` with `stateCd` + `parameterCd=72019` → get list of site_nos with DTW data (this endpoint DOES support stateCd)
2. Batch those site_nos 100 at a time to `/nwis/stat/?statReportType=MONTHLY` → get monthly mean DTW per year per site
3. Compute full stats per site: median, mean, **min** (shallowest / wet season), **max** (deepest / dry season)

Confirmed working (tested against Oklahoma sites). National runtime: ~300K sites / 100 per request × 0.5s = ~25 min one-time. No API calls at report time — all data stored in PostGIS.

**HydroFrame Gridded WTD:**
The **Ma et al. (2025/2026)** dataset provides a 30m (~24m) continuous raster of long-term mean water table depth for the entire CONUS, trained on ~1M well observations using a random forest model. Published in *Nature Communications Earth & Environment*, DOI: 10.1038/s43247-025-03094-3.

| Property | Value |
|---|---|
| Resolution | ~24m (1 arc-second Lambert Conformal Conic) |
| Coverage | Full CONUS |
| Variable | `water_table_depth` (meters) |
| Uncertainty | `wtd_uncertainty` (meters, also available) |
| Nature | **Modeled long-term mean** (not direct measurement) |
| Model accuracy | r=0.79, RMSE=14.94m (~49 ft) |
| License | CC-BY 4.0 |
| Access | `hf_hydrodata` Python package (requires free HydroFrame account) |
| Storage | MinIO COG (same pattern as NClimGrid, NLCD, 3DEP) |

The RMSE of ~49 ft is significant for shallow water tables, but for planning purposes the distinction between "expect water at ~10 ft" vs "~150 ft" is still actionable. Both the modeled estimate AND the uncertainty value should be shown, with a clear disclaimer.

Both data sources are all-local at report time — USGS well DTW from PostGIS, HydroFrame from MinIO COG.

### Key Limitations
- USGS principal aquifer layer covers only major national systems. Many areas sit on unlisted bedrock.
- Service area boundaries may lag actual utility service territory — always verify with utility directly.
- SDWIS only includes Community Water Systems (public). Industrial self-supply and private wells are not represented.
- USGS well DTW represents long-term median of annual means — not seasonal or current water level.
- HydroFrame WTD is a machine-learning modeled estimate (RMSE ~49 ft / ~15m). It indicates typical depth range but is not a substitute for a geotechnical investigation.

---

## Section Design: 7C — Water & Utility Infrastructure

### 7C-A: Public Water Supply

**Utility Provider kv-grid:**
- Utility name (bold)
- Owner / entity type (decoded: Local Government, Municipal Authority, Private, etc.)
- Primary water source (decoded: Surface Water, Groundwater, etc.)
- Population served
- Service connections
- 5-year violation count — flagged amber/warning if > 0, with note directing user to EPA ECHO for violation details

**If site is NOT inside any service area boundary:**
- Show nearest system(s) with distance
- Note that connection would require extension or onsite well/water supply

**Map — Water Service Areas:**
- Mapbox light basemap, ~8-mile radius
- Containing service area: filled polygon with semi-transparent blue + solid border, labeled
- Adjacent service areas: lighter fill, thinner border, labeled
- Site: red star marker
- Legend: color per utility (up to 4), site marker

### 7C-B: Groundwater & Aquifer Context

**Aquifer context kv-grid:**
- Whether site overlies a named USGS principal aquifer
  - If yes: aquifer name, type (e.g., "Unconsolidated sand and gravel"), distance = 0 / "Site within aquifer extent"
  - If no: "Site not within a mapped principal aquifer" + name and distance of nearest named aquifer
- Note: "USGS principal aquifers are major national formations. Local/state aquifers may exist — consult state geological survey."

**Modeled Water Table Depth (HydroFrame):**
- Single kv row: "Estimated Water Table Depth: X ft (±Y ft)" — sampled from the HydroFrame COG at the site location
- Labeled clearly: "Modeled long-term mean estimate (Ma et al., 2025). Not a measurement."
- If uncertainty value is > 30 ft, add inline note: "High uncertainty at this location — consult geotechnical investigation."

**Nearby Monitoring Wells table** (up to 8 wells within ~10 miles, ordered by distance):
| Station | Distance | Well Depth (ft) | DTW: Typical (ft) | DTW: High (ft) | DTW: Low (ft) | Aquifer |
|---|---|---|---|---|---|---|
| 17N-14E-15 ADA 1 | 4.4 mi | 31 ft | 13.7 ft | 5.8 ft | 18.6 ft | Alluvium |
| ... | | | | | | |

- Well depth = construction depth (how deep the well was drilled)
- DTW Typical = median of all monthly mean observations (long-term)
- DTW High = shallowest recorded monthly mean = highest water table (wet season peak)
- DTW Low = deepest recorded monthly mean = lowest water table (dry season trough)
- All three DTW columns show "—" if no DTW observations for that well
- Wells with no DTW data are still included if they have construction depth (useful drilling context)
- All data from PostGIS — no API calls at report time

**Map — Groundwater Context:**
- Mapbox terrain basemap, ~15-mile radius
- If site overlies principal aquifer: aquifer polygon shaded (translucent teal)
- If not: show nearest aquifer polygon at edge of frame if within 40 miles (lighter shading)
- Monitoring well dots: colored by DTW availability (teal = has DTW data, grey = construction depth only); size ∝ well depth (capped)
- Site: red star
- Legend: aquifer polygon, well types (DTW observed / depth only), site marker

**Inline disclaimer:**
> Groundwater data from USGS NWIS. Well locations reflect monitoring and supply wells registered with USGS, not all wells in the area. Median depth-to-water values are long-term medians derived from annual mean observations. Modeled water table depth from Ma et al. (2025) — a machine-learning estimate with RMSE of approximately 15 m (~49 ft); use for planning context only. USGS principal aquifer boundaries are generalized national-scale polygons. For site-specific groundwater conditions, a geotechnical investigation and consultation with the state geological survey is required.

---

## Implementation Phases

### Phase 0A — Fix USGS Groundwater Wells Ingestor (DTW)
**File:** `plinth/ingest/usgs_groundwater_wells.py`

Fix `_download_state_stats(state)` to use a two-step approach:
1. Query `/nwis/site/` with `stateCd`, `parameterCd=72019` to get site_nos that have DTW data for that state
2. Batch those site_nos 100 at a time to `/nwis/stat/?statReportType=MONTHLY&parameterCd=72019` to retrieve monthly mean DTW per year/month
3. Cache per-state results to `staging/dtw_stats_{state}.rdb`

Fix `_build_dtw_stats()` to parse MONTHLY RDB format (columns: `site_no`, `year_nu`, `month_nu`, `mean_va`, `count_nu`) and compute per-site aggregates from all monthly mean values:
- `dtw_median_ft` = median of all `mean_va` values — typical depth
- `dtw_mean_ft` = mean of all `mean_va` values
- `dtw_min_ft` = min `mean_va` = **shallowest / highest water table** (wet season peak)
- `dtw_max_ft` = max `mean_va` = **deepest / lowest water table** (dry season trough)
- `dtw_obs_count` = sum of `count_nu`
- `dtw_period_start` = first year in data
- `dtw_period_end` = last year in data

Using MONTHLY (not ANNUAL) gives 12× more data points per site with the same number of API requests, and populates the meaningful seasonal range in `dtw_min_ft` / `dtw_max_ft`. All four stat columns are already in the `usgs_groundwater_wells` schema.

Fix `download()` to call `_download_state_stats(state)` after `_download_state_sites(state)`. After fixing, re-run the ingestor nationally to populate all four DTW columns for wells with observed data.

### Phase 0B — HydroFrame WTD Ingestor
**File:** `plinth/ingest/hydroframe_wtd.py`

New ingestor: `HydroframeWtdIngestor` with `source_name = "hydroframe-wtd"`.

Storage: MinIO COG at key `hydroframe-wtd/ma2025/water_table_depth.tif` and `hydroframe-wtd/ma2025/wtd_uncertainty.tif`, indexed in `raster_tiles`.

Download strategy:
- Use the `hf_hydrodata` Python package (add to `pyproject.toml` dependencies)
- Requires a free HydroFrame account — store credentials in `.env` as `HYDROFRAME_USERNAME` and `HYDROFRAME_PASSWORD` (document in `.env.example`)
- Download the full CONUS `water_table_depth` and `wtd_uncertainty` variables from the `ma_2025` dataset
- Convert to COG (gdal_translate) and upload to MinIO
- Register both tiles in `raster_tiles` with `dataset="hydroframe-wtd"`, `tile_id="water_table_depth"` and `"wtd_uncertainty"`

> **Note:** Verify whether the full CONUS download via `hf_hydrodata` is practical (expected size: ~20–50GB). If the package only supports bounding-box subsets, tile by CONUS bounding box in one request or consider using the direct Zenodo download if available.

### Phase 1 — Query Module
**File:** `plinth/query/water_infrastructure.py`

Function: `query_water_infrastructure(lat, lon) -> dict`

Returns:
```python
{
  "available": bool,
  # PWS
  "pws_in_service_area": bool,
  "service_systems": [              # systems containing site, or [] if none
      {
          "pwsid": str,
          "utility_name": str,
          "owner_type": str,        # decoded label
          "source_type": str,       # decoded label
          "population_served": int,
          "service_connections": int | None,
          "violations_5yr": int,
          "geojson": str,           # simplified polygon for map
      }
  ],
  "nearby_systems": [               # nearest non-containing systems, up to 4
      { ...same fields..., "distance_mi": float }
  ],
  # Aquifer
  "in_named_aquifer": bool,
  "aquifer": {                      # None if not in named aquifer
      "name": str,
      "aquifer_type": str,
      "distance_mi": 0.0,
  } | None,
  "nearest_aquifer": {              # always populated
      "name": str,
      "aquifer_type": str,
      "distance_mi": float,
      "geojson": str,               # simplified polygon
  },
  # Wells (up to 8 within ~10 miles)
  "nearby_wells": [
      {
          "site_no": str,
          "station_name": str,
          "distance_mi": float,
          "well_depth_ft": float | None,
          "dtw_median_ft": float | None,   # typical depth; NULL if no DTW observations
          "dtw_min_ft": float | None,      # shallowest (wet season high water table)
          "dtw_max_ft": float | None,      # deepest (dry season low water table)
          "dtw_period_start": str | None,  # e.g. "2018"
          "dtw_period_end": str | None,    # e.g. "2024"
          "aquifer_label": str | None,
      }
  ],
  # Gridded WTD (HydroFrame COG sampled at site location)
  "wtd_modeled_ft": float | None,          # converted from meters; None if COG unavailable
  "wtd_uncertainty_ft": float | None,      # uncertainty in same units
}
```

The HydroFrame COG sampling follows the same pattern as `query_usgs_3dep`: find the tile in `raster_tiles`, fetch from MinIO, clip to a 1-pixel AOI, read the value.

### Phase 2 — Context Builder
**File:** `plinth/report/context.py`

Add `_build_water(water_q: dict) -> dict` and wire into `build_report_context()`.

### Phase 3 — Maps
**File:** `plinth/report/maps.py`

Add two functions:
- `fetch_water_service_map_b64(lat, lon, water_q) -> str | None`
  - Mapbox light, ~8-mile radius
  - Service area polygons (up to 4 systems), site star
- `fetch_groundwater_map_b64(lat, lon, water_q) -> str | None`
  - Mapbox terrain, ~15-mile radius
  - Aquifer polygon(s), monitoring well dots colored by DTW availability, site star

Both follow the same Pillow overlay pattern established for the electric map.

### Phase 4 — Template
**File:** `plinth/report/templates/report.html`

Add Section 7C after Section 7B (Electrical Infrastructure), before Section 8.
Page break before the section heading.

### Phase 5 — Data Sources & Registry
**File:** `plinth/report/context.py` (`_SOURCE_DISPLAY`)

Add entries to `_SOURCE_DISPLAY`:
```python
"epa-sdwis":              ("EPA Safe Drinking Water Information System (SDWIS)", "PostGIS",   None),
"epa-water-boundaries":   ("EPA Water System Service Boundaries",                "PostGIS",   None),
"usgs-aquifers":          ("USGS Principal Aquifers",                            "PostGIS",   None),
"usgs-groundwater-wells": ("USGS NWIS Groundwater Wells",                       "PostGIS",   None),
"hydroframe-wtd":         ("HydroFrame Water Table Depth (Ma et al., 2025)",     "MinIO COG", "Long-term mean"),
```

Also add `HYDROFRAME_USERNAME` and `HYDROFRAME_PASSWORD` to `.env.example`.

---

## Design Decisions

| Decision | Resolution |
|---|---|
| What if site not in any service area? | Show nearest 2–3 systems with distance; note service extension or private supply required |
| "Other rocks" aquifer (code 999)? | Display as "Not within a mapped principal aquifer" — do not show the internal code |
| Wells with no DTW data? | Include in table with "—" in DTW column; still useful for construction depth context |
| HydroFrame high uncertainty (> 30 ft)? | Show value with inline amber note: "High uncertainty at this location" |
| How many wells on map? | Up to 25 nearest within 10 miles; dots only (no labels, too cluttered) |
| Violation count > 0 display? | Show count with amber inline note: "See EPA ECHO for violation details." Link to ECHO search |
| Map radius for service areas? | ~8 miles; cap at 4 visible systems |
| Map radius for groundwater? | ~15 miles; show aquifer polygon if within 40 miles |
| Aquifer map basemap style? | `mapbox/outdoors-v12` (terrain context is useful for groundwater) |
| Service area map basemap style? | `mapbox/light-v11` (keeps utility boundaries readable) |
| HydroFrame vs. USGS well DTW — which to lead with? | HydroFrame is always available and gives site-specific value; well DTW gives observational context. Show HydroFrame first as the headline number, wells table below as supporting evidence. |

---

## What AEC Professionals and Developers Get

| Question | Answer Source |
|---|---|
| Who is the water utility? | SDWIS + service boundary lookup |
| Is the site in a service area? | `ST_Contains` on `water_system_boundaries` |
| What is the water source (surface vs. groundwater)? | `primary_source` in SDWIS |
| Any compliance issues with the utility? | `violation_count_5yr` in SDWIS |
| What aquifer underlies the site? | USGS principal aquifer lookup |
| What is the estimated water table depth at this site? | HydroFrame WTD COG (modeled, with uncertainty) |
| How deep are nearby wells? | `well_depth_ft` from USGS NWIS (construction depth) |
| What do nearby monitoring wells show for water table? | `dtw_median_ft` / `dtw_min_ft` / `dtw_max_ft` from USGS NWIS (observed seasonal range) |
| Is there a public water main nearby if not in service area? | Nearest system with distance |
