# API-to-Local-Store Migration Plan
**Date:** 2026-03-11  
**Goal:** Eliminate all runtime API dependencies by bulk-ingesting seven data sources into local PostGIS tables or MinIO COG rasters. After ingestion the query layer is refactored to read local data exclusively.

---

## Problem

Seven data sources are fetched from remote APIs at report-generation time and cached in `query_cache`. This creates:
- Slow reports when cache is cold or network is degraded (~4 min observed)
- Complete section suppression when the API is unreachable
- API credential dependencies and potential rate-limiting in production
- Inability to query historical snapshots

All seven sources have bulk-download equivalents that can be ingested once and refreshed on a schedule.

---

## Source Audit

| Source | Current Approach | Bulk Alternative |
|--------|-----------------|-----------------|
| **Census ACS** | Per block group via Census API at query time | Census Bureau ACS 5-Year Summary File — pre-built national `.dat` files, no API key |
| **EPA AQS** | Per county via AQS API at query time | EPA pre-built annual summary CSV files (national, ~100 MB/year) |
| **FCC Broadband** | BDC API (confirmed broken — 405 errors) | FCC BDC state availability bulk ZIP download |
| **NASA POWER** | Per 0.5° grid cell via POWER API at query time | POWER **regional** climatology API: 1 call per parameter covers the entire bbox in one response |
| **USDA WHP** | geoplatform.gov ImageServer API (cached) | USDA USFS WHP 2023 GeoTIFF national download → MinIO COG |
| **USGS Earthquake** | FDSN API per point/radius at query time | USGS ComCat bulk CSV export by bounding box |
| **USGS Seismic PGA** | USGS Design Maps API (NEHRP 2020, cached) | USGS NSHM 2023 hazard grid raster download → MinIO COG |

> **Note:** The `docs/plinth.dbml` custom instruction and the Data Sources Reference table describe WHP and Seismic as "MinIO COG" but the current implementation uses live APIs with `query_cache`. This plan completes their intended implementation.

---

## Coverage Target

**NE Oklahoma counties:** Craig (40035), Delaware (40041), Mayes (40097), Nowata (40117), Ottawa (40115), Rogers (40131), Tulsa (40143), Wagoner (40145), Washington (40147)

**Bounding box (with 0.5° buffer):**  
- Lat: 35.0°N – 37.5°N  
- Lon: -97.5°W – -94.0°W

For datasets only available nationally (EPA AQS annual files, USDA WHP raster, USGS seismic raster, Census ACS Summary Files), load the full national dataset. For FCC Broadband, download the Oklahoma state file. For USGS Earthquakes, download the NE Oklahoma bounding box + 1° buffer. For NASA POWER, use the regional climatology API to fetch all grid cells in the bbox in 9 bulk calls (one per parameter).

---

## Phase 1 — Schema (Migration 007)

New tables to add. All fields from each source are stored regardless of current report usage.

### `acs_block_group_data`
One row per block group per ACS vintage year. ~125 columns matching the full `ACS_VARS` dict in `census_acs.py`, plus any additional Census variables worth storing.

```sql
CREATE TABLE acs_block_group_data (
    geoid          CHAR(12) NOT NULL,
    acs_year       SMALLINT NOT NULL,
    -- All ~125 ACS_VARS fields (NUMERIC, nullable)
    total_population NUMERIC, median_age NUMERIC, ...
    PRIMARY KEY (geoid, acs_year)
);
```

### `epa_aqs_sites`
One row per monitoring site. Loaded from the EPA annual summary CSV header data.

```sql
CREATE TABLE epa_aqs_sites (
    site_id         TEXT PRIMARY KEY,  -- state_code||county_code||site_num (9 chars)
    state_code      TEXT,
    county_code     TEXT,
    site_num        TEXT,
    local_site_name TEXT,
    address         TEXT,
    city            TEXT,
    county_name     TEXT,
    state_name      TEXT,
    latitude        NUMERIC,
    longitude       NUMERIC,
    geom            GEOMETRY(POINT, 4326)
);
CREATE INDEX epa_aqs_sites_geom_idx ON epa_aqs_sites USING GIST(geom);
```

### `epa_aqs_annual_summary`
One row per site × year × parameter × pollutant standard. Stores all fields from the EPA annual summary CSV (not just PM2.5/ozone).

```sql
CREATE TABLE epa_aqs_annual_summary (
    id                    BIGSERIAL PRIMARY KEY,
    site_id               TEXT NOT NULL REFERENCES epa_aqs_sites(site_id),
    year                  SMALLINT NOT NULL,
    parameter_code        TEXT NOT NULL,
    parameter_name        TEXT,
    pollutant_standard    TEXT,
    units                 TEXT,
    arithmetic_mean       NUMERIC,
    first_max_value       NUMERIC,
    first_max_hour        INTEGER,
    second_max_value      NUMERIC,
    third_max_value       NUMERIC,
    fourth_max_value      NUMERIC,
    ninety_eighth_pctile  NUMERIC,
    ninety_ninth_pctile   NUMERIC,
    aqi                   INTEGER,
    method_code           TEXT,
    method_name           TEXT,
    observation_count     INTEGER,
    observation_percent   NUMERIC,
    valid_day_count       INTEGER,
    required_day_count    INTEGER,
    exceptional_data_count INTEGER,
    UNIQUE(site_id, year, parameter_code, pollutant_standard)
);
CREATE INDEX epa_aqs_summary_site_year_idx ON epa_aqs_annual_summary(site_id, year);
```

### `fcc_broadband_availability`
One row per location × provider × technology from the FCC BDC availability file.

```sql
CREATE TABLE fcc_broadband_availability (
    id                       BIGSERIAL PRIMARY KEY,
    location_id              BIGINT NOT NULL,
    frn                      TEXT,
    provider_id              TEXT,
    brand_name               TEXT,
    technology_code          SMALLINT,
    max_download_speed       INTEGER,   -- Mbps
    max_upload_speed         INTEGER,   -- Mbps
    low_latency              BOOLEAN,
    business_residential_code CHAR(1),
    state_usps               TEXT,
    county_geoid             TEXT,
    block_geoid              TEXT,
    h3_res8_id               TEXT,
    geom                     GEOMETRY(POINT, 4326)
);
CREATE INDEX fcc_broadband_geom_idx ON fcc_broadband_availability USING GIST(geom);
CREATE INDEX fcc_broadband_location_idx ON fcc_broadband_availability(location_id);
CREATE INDEX fcc_broadband_county_idx ON fcc_broadband_availability(county_geoid);
```

### `nasa_power_climatology`
One row per 0.5° grid cell × month (month 0 = annual average). Stores all 11 current parameters plus extras.

```sql
CREATE TABLE nasa_power_climatology (
    grid_lat              NUMERIC(5,2) NOT NULL,  -- SW corner of cell
    grid_lon              NUMERIC(6,2) NOT NULL,
    month                 SMALLINT NOT NULL,       -- 1-12; 0 = annual
    t2m_mean_c            NUMERIC,
    t2m_max_c             NUMERIC,
    t2m_min_c             NUMERIC,
    t2mdew_c              NUMERIC,
    prectotcorr_mm_day    NUMERIC,
    allsky_sfc_sw_dwn     NUMERIC,  -- kWh/m²/day
    allsky_kt             NUMERIC,
    ws10m_m_s             NUMERIC,
    rh2m_pct              NUMERIC,
    hdd18_3               NUMERIC,
    cdd18_3               NUMERIC,
    -- Additional POWER parameters stored for completeness
    ws50m_m_s             NUMERIC,  -- Wind speed at 50m
    allsky_sfc_lw_dwn     NUMERIC,  -- Longwave radiation
    clrsky_sfc_sw_dwn     NUMERIC,  -- Clear-sky insolation
    t2mwet_c              NUMERIC,  -- Wet bulb temperature
    PRIMARY KEY (grid_lat, grid_lon, month)
);
```

### `usgs_earthquake_events`
One row per earthquake event. Loads all available M≥2.0 events for the region.

```sql
CREATE TABLE usgs_earthquake_events (
    event_id      TEXT PRIMARY KEY,
    occurred_at   TIMESTAMPTZ NOT NULL,
    magnitude     NUMERIC,
    magnitude_type TEXT,
    depth_km      NUMERIC,
    place         TEXT,
    status        TEXT,
    gap           NUMERIC,
    rms           NUMERIC,
    nst           INTEGER,
    url           TEXT,
    geom          GEOMETRY(POINT, 4326)
);
CREATE INDEX usgs_eq_geom_idx ON usgs_earthquake_events USING GIST(geom);
CREATE INDEX usgs_eq_occurred_idx ON usgs_earthquake_events(occurred_at);
CREATE INDEX usgs_eq_mag_idx ON usgs_earthquake_events(magnitude);
```

---

## Phase 2 — Bulk Ingestors

Each ingestor lives in `plinth/ingest/` and extends `BaseIngestor`. New bulk ingestors go in `plinth/ingest/` alongside the existing ones (not in `api/`).

### 2a. Census ACS — `plinth/ingest/census_acs_bulk.py`

**Source:** Census Bureau ACS 5-Year Summary File — no API key required  
**Base URL:** `https://www2.census.gov/programs-surveys/acs/summary_file/2023/table-based-SF/data/5YRData/`  
**Method:**
1. Download the geography reference file (`Geos20235YR.txt`) to get GEOID mappings.
2. For each ACS table used in `ACS_VARS` (~23 unique table prefixes: B01001, B01002, B01003, B03002, B08301, B08303, B11001, B15003, B19013, B19057, B19301, B23025, B25001, B25002, B25003, B25010, B25035, B25064, B25077, C16002, C17002, C24010, C24030), download `acsdt5y2023-<tableid>.dat`.
3. Filter rows to `SUMLEVEL=150` (block group). Load **all states** (not just Oklahoma) — files are national, and loading all block groups (~240,000 rows nationally) future-proofs coverage for any US address and is well within disk limits.
4. Join estimate columns across table files by GEO_ID. Upsert into `acs_block_group_data`.
5. Store both estimate (`_E`) and margin-of-error (`_M`) values for each variable.

**No API key required. No rate limits. ~1–2 GB total download across ~23 table files.**  
**CLI:** `plinth-cli ingest census-acs-bulk [--year 2023]`

### 2b. EPA AQS — `plinth/ingest/epa_aqs_bulk.py`

**Source:** `https://aqs.epa.gov/aqsweb/airdata/annual_conc_by_monitor_YYYY.zip`  
**Method:** Download annual summary ZIPs for the last 5 years. Parse CSV. Upsert sites into `epa_aqs_sites`; upsert summaries into `epa_aqs_annual_summary`. Filter to Oklahoma on import to keep table size manageable; load national if disk allows (files are ~100 MB/year compressed).  
**CLI:** `plinth-cli ingest epa-aqs-bulk [--years 5]`

### 2c. FCC Broadband — `plinth/ingest/fcc_broadband_bulk.py`

**Source:** `https://broadbandmap.fcc.gov/data-download` — Oklahoma fixed availability file  
**Method:** Download state ZIP (expected ~500 MB–2 GB compressed). Parse CSV. Bulk-load into `fcc_broadband_availability` using `COPY` for performance. The `curl`-based download workaround from the existing FCC ingestor may be reusable for authentication.  
**CLI:** `plinth-cli ingest fcc-broadband-bulk [--state ok]`  
**Note:** FCC releases new availability data twice yearly (June/December). The ingestor should check the `listAsOfDates` endpoint to detect when new data is available.

### 2d. NASA POWER — `plinth/ingest/nasa_power_bulk.py`

**Source:** NASA POWER **regional** climatology API  
**URL pattern:** `/api/temporal/climatology/regional?latitude-min=35&latitude-max=37.5&longitude-min=-97.5&longitude-max=-94&parameters=T2M&community=SB&format=CSV`  
**Method:** The regional endpoint is limited to **1 parameter per call**, but returns all grid cells in the bbox in a single response. With 9 parameters (T2M, T2M_MAX, T2M_MIN, T2MDEW, PRECTOTCORR, ALLSKY_SFC_SW_DWN, ALLSKY_KT, WS10M, RH2M), make 9 regional API calls total — one per parameter. Each response is a small CSV (~35–40 rows). Parse and upsert into `nasa_power_climatology`. Total: 9 API calls to cover the entire region.  
**Pre-computed climatology period:** 2001–2020 (20-year average, not subject to daily updates).  
**CLI:** `plinth-cli ingest nasa-power-bulk [--bbox "35.0,-97.5,37.5,-94.0"]`

### 2e. USGS Earthquakes — `plinth/ingest/usgs_earthquakes_bulk.py`

**Source:** USGS FDSN ComCat — `https://earthquake.usgs.gov/fdsnws/event/1/query?format=csv`  
**Method:** Download all M≥2.0 events within coverage bbox + 1° buffer (34.0–38.5°N, -98.5–-93.0°W), all available years. The FDSN API limits single responses to 20,000 events; paginate by year ranges. Upsert into `usgs_earthquake_events`.  
**CLI:** `plinth-cli ingest usgs-earthquakes-bulk [--min-mag 2.0]`  
**Estimate:** Oklahoma had high induced seismicity 2010–2018; expect 50,000–150,000 events.

### 2f. USDA WHP Raster — `plinth/ingest/usda_whp_raster.py`

**Source:** USDA Forest Service WHP 2023 GeoTIFF  
**URL:** `https://www.fs.usda.gov/rds/archive/catalog/RDS-2015-0047-4` (270 m, national)  
**Method:** Download national GeoTIFF. Convert to COG with `gdal_translate`. Upload to MinIO at `usda-whp/2023/whp_2023_national.tif`. Register in `raster_tiles`.  
**CLI:** `plinth-cli ingest usda-whp-raster`  
**Note:** National raster at 270 m is ~500 MB–2 GB. Store full national file — no clipping.

### 2g. USGS Seismic Hazard Raster — `plinth/ingest/usgs_seismic_raster.py`

**Source:** USGS National Seismic Hazard Model 2023 (NSHM 2023) PGA grid  
**URL:** `https://earthquake.usgs.gov/hazards/hazmaps/conterminous/` — 2% in 50 years PGA raster  
**Method:** Download national PGA grid (0.05° resolution, ~100 MB). Convert to COG. Upload to MinIO at `usgs-seismic/2023/pga_2pct50yr.tif`. Register in `raster_tiles`. Also store Ss (0.2s) and S1 (1.0s) spectral acceleration grids.  
**CLI:** `plinth-cli ingest usgs-seismic-raster`

---

## Phase 3 — Verification

Add a `plinth-cli verify <dataset>` subcommand (or `plinth-cli verify all`) that runs coverage checks and prints a pass/fail report.

### Per-dataset checks

| Dataset | Checks |
|---------|--------|
| **Census ACS** | Count BGs loaded; confirm all 9 NE OK counties present (~6,800 BGs in NE OK); check no NULL total_population for populated BGs |
| **EPA AQS** | Count sites within NE OK bbox; confirm at least 1 PM2.5 + 1 ozone monitor within 100 km of test coord; latest year present |
| **FCC Broadband** | Count locations in NE OK bbox; confirm multiple technology codes present; latest as-of-date matches FCC |
| **NASA POWER** | List all grid cells; confirm all 40 cells loaded; all 12 months × all parameters non-null |
| **USGS Earthquakes** | Count events in NE OK bbox; confirm date range; sample spot-check known large events (e.g. 2016-09-03 M5.8 Pawnee) |
| **USDA WHP** | Confirm tile registered in `raster_tiles`; sample point query at test coordinate returns non-null |
| **USGS Seismic** | Confirm tile registered in `raster_tiles`; sample point query at test coordinate returns non-null |

### Coverage report format (stderr)
```
  ── Dataset coverage ─────────────────────────
  census-acs-bulk     ✓  2,847 block groups (OK state)
  epa-aqs-bulk        ✓  38 sites in bbox; PM2.5 + O3 present; latest: 2023
  fcc-broadband-bulk  ✓  1,243,881 locations in OK; latest: 2024-12
  nasa-power-bulk     ✓  40 grid cells; 12 months each; all params present
  usgs-earthquakes    ✓  87,432 events (M≥2.0, 1970–2026) in bbox
  usda-whp-raster     ✓  1 national COG tile; test coord: 22,814
  usgs-seismic-raster ✓  3 national COG tiles (PGA, Ss, S1); test coord: 0.09g
  ─────────────────────────────────────────────
```

---

## Phase 4 — Query Layer Refactoring

Each refactored query function keeps the **exact same return dict structure** so the report context builder and template require no changes.

### 4a. `plinth/query/census_demographics.py`
Currently calls `fetch_area_weighted()` → Census API per block group.  
**After:** `query_census_block_groups()` already returns GEOIDs with intersection weights. New helper reads `acs_block_group_data` by geoid list. Remove `census_acs.py` API client dependency from the query path.

### 4b. `plinth/query/epa_aqs.py`
Currently calls EPA AQS API per county.  
**After:** Spatial nearest-monitor lookup against `epa_aqs_sites` → join to `epa_aqs_annual_summary` for the most recent year with data. Use ST_DWithin with a 100 km fallback radius (matching current `_NO_MONITOR_RADIUS_MI = 50`).

### 4c. `plinth/query/fcc_broadband.py`
Currently placeholder returning unavailable.  
**After:** ST_DWithin point query against `fcc_broadband_availability`. Return best available speeds by technology type.

### 4d. `plinth/query/nasa_power.py`
Currently calls NASA POWER API per 0.5° cell.  
**After:** Compute grid cell key (same `_grid_key()` logic) → SELECT from `nasa_power_climatology`. Zero network calls.

### 4e. `plinth/query/earthquakes.py`
Currently calls USGS FDSN API per point.  
**After:** PostGIS `ST_DWithin` query on `usgs_earthquake_events` with `magnitude >= 3.0` and a 30-year window. Same output structure.

### 4f. `plinth/query/wildfire_whp.py`
Currently calls geoplatform.gov ImageServer.  
**After:** Raster COG lookup from MinIO — same pattern as `query_elevation` / `query_land_cover`. Uses `raster_tiles` index to find the tile, fetches COG, samples the pixel value.

### 4g. `plinth/query/seismic_pga.py`
Currently calls USGS Design Maps API.  
**After:** Raster COG lookup from MinIO for PGA, Ss, S1 grids. Returns same `pgam_g`, `ss_g`, `s1_g` fields.

### Retire `plinth/ingest/api/` clients
Once query layer is refactored and verified:
- `usda_whp.py`, `usgs_seismic.py`, `nasa_power.py`, `epa_aqs.py`, `usgs_earthquakes.py` → delete or move to `plinth/ingest/api/legacy/`  
- `census_acs.py` → keep for the block-group fetch called by `census_acs_bulk.py` ingestor (reuse its `ACS_VARS`, `_VAR_BATCHES`, `_fetch_block_group()`)  
- `fcc_broadband.py` → delete (was already broken)
- Remove `query_cache` dependency for all 7 sources (cache still used by other future API sources if any)

---

## Phase 5 — CLI & Flow Integration

- Add all new ingestors to `plinth-cli ingest all --region ne-oklahoma`
- Add `plinth-cli verify [dataset | all]` command
- Add `plinth-cli ingest status` to show ingestion state of all datasets
- Update Prefect flows with scheduled refresh tasks:
  - Census ACS: annual (January)
  - EPA AQS: annual (March, after prior-year data released)
  - FCC Broadband: semi-annual (July, January)
  - NASA POWER: manual / on schema change
  - USGS Earthquakes: monthly
  - USDA WHP: annual
  - USGS Seismic: manual / on NSHM release (~5-year cycle)

---

## Phase 6 — Schema Documentation

Update `docs/plinth.dbml` to reflect the final database schema after all migrations are applied:
- Add all 8 new tables from Migration 007 (`acs_block_group_data`, `epa_aqs_sites`, `epa_aqs_annual_summary`, `fcc_broadband_availability`, `nasa_power_climatology`, `usgs_earthquake_events`, `usda_whp_raster_tiles`, `usgs_seismic_raster_tiles`)
- Add any new columns or constraints introduced alongside the new tables
- Verify all relationships (Ref: lines) are accurate with the final schema

This step runs after Phase 5 once all schema changes are stable.

---

## Size Estimates

| Dataset | Estimated Storage | Location |
|---------|------------------|----------|
| Census ACS (national BGs) | ~1–2 GB download; ~3–5 GB in PostgreSQL (~240k BGs × 125 vars) | PostgreSQL |
| EPA AQS (national, 5 years) | ~500 MB | PostgreSQL |
| FCC Broadband (OK state) | ~5–20 GB | PostgreSQL |
| NASA POWER (40 cells) | < 1 MB | PostgreSQL |
| USGS Earthquakes (NE OK bbox) | ~50–200 MB | PostgreSQL |
| USDA WHP raster (national) | ~1–2 GB | MinIO COG |
| USGS Seismic rasters (national, 3) | ~500 MB | MinIO COG |

All within the available capacity (several hundred GB PostgreSQL, ~4 TB MinIO).

---

## Sequence / Dependencies

```
Phase 1 (Migration 007)
  ↓
Phase 2a–2g (Ingestors) — can be done in parallel
  ↓
Phase 3 (Verification) — run after each ingestor completes
  ↓
Phase 4a–4g (Query refactor) — each independent once its ingestor is verified
  ↓
Phase 5 (CLI + Flows)
  ↓
Phase 6 (Update docs/plinth.dbml)
```

---

## Open Questions / Decisions Made

- **FCC data scope:** Oklahoma state file only (not national). Re-download per state when expanding coverage regions.
- **EPA AQS scope:** Oklahoma state records only from national annual files. Expand on demand.
- **Earthquake minimum magnitude:** Store M≥2.0 in DB; query layer continues to display M≥3.0 (matches current behavior).
- **NASA POWER coverage:** 40 cells covering 35.0–37.5°N, -97.5–-94.0°W. Re-run with expanded bbox when adding new regions.
- **USGS Seismic model version:** Use NSHM 2023 raster grid (supersedes the NEHRP 2020 Design Maps API values currently used).
- **`query_cache` table:** Retained for any future API-sourced data but no longer used by these 7 sources after refactor.
