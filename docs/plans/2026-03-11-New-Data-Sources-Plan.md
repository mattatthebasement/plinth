# New Data Sources Plan
**File:** `docs/plans/2026-03-11-New-Data-Sources-Plan.md`

## Scope

Database migrations and bulk ingestion for four new data domains:

1. **NOAA NClimGrid** — 5km gridded monthly climate normals (1991–2020)
2. **EIA + HIFLD Power** — Power plants, utility service territories, transmission lines, substations
3. **Water Utilities** — EPA SDWIS public water systems + service area boundaries
4. **USGS Groundwater** — Principal aquifer polygons + NWIS monitoring wells

**Out of scope for this plan:** Query functions, report template integration (separate follow-on plan).

---

## What We're Getting (and Why)

### 1. NOAA NClimGrid Monthly Gridded Climate Normals (1991–2020)

**Source:** NOAA NCEI / AWS S3 public bucket (`s3://noaa-normals-pds/`)  
**Format:** 4 NetCDF files, 1/24° (~5km) resolution, CONUS coverage  
**Variables:** `tmax`, `tmin`, `tavg` (°C), `prcp` (mm) — each has 12 monthly values  
**Storage approach:** Raster COGs in MinIO — 4 COGs × 12 bands each  
**Update cadence:** Decadal

**Why it's better than the existing NOAA station normals:**  
The existing `noaa_climate_normals` table stores station-interpolated point data (~8,000 weather stations). For a site in rural Oklahoma with the nearest station 30 miles away, we get a "nearest-station" value with a quality flag. The NClimGrid dataset provides a continuous gridded surface at ~5km resolution derived from all stations using spatial interpolation — every point in the CONUS has a high-quality value. This will substantially improve climate normal accuracy for any arbitrary location.

**Report use cases:**
- Monthly mean high/low temperature at site
- Monthly precipitation normal (better than station)
- Growing degree days (derived from gridded tmax/tmin)
- Freeze/frost season length

**Download URLs (public HTTPS, no auth):**
```
https://noaa-normals-pds.s3.amazonaws.com/normals-monthly-gridded/1991-2020/nClimGrid_tavg-1991_2020-monthly-normals-v1.0.nc
https://noaa-normals-pds.s3.amazonaws.com/normals-monthly-gridded/1991-2020/nClimGrid_tmax-1991_2020-monthly-normals-v1.0.nc
https://noaa-normals-pds.s3.amazonaws.com/normals-monthly-gridded/1991-2020/nClimGrid_tmin-1991_2020-monthly-normals-v1.0.nc
https://noaa-normals-pds.s3.amazonaws.com/normals-monthly-gridded/1991-2020/nClimGrid_prcp-1991_2020-monthly-normals-v1.0.nc
```

---

### 2. EIA + HIFLD Power Infrastructure

Four datasets combined into one domain:

#### 2a. EIA-860 Annual Electric Generator Report (Power Plants)

**Source:** U.S. Energy Information Administration  
**URL:** `https://www.eia.gov/electricity/data/eia860/` (annual ZIP with Excel sheets)  
**Format:** `.xlsx` via ZIP — parse `2___Plant_Y{year}.xlsx` and `3_1_Generator_Y{year}.xlsx`  
**Content:**
- Plant name, lat/lon, state, county, operator name
- Nameplate capacity (MW) per generator
- Technology type (combined cycle, wind, solar PV, nuclear, etc.)
- Primary fuel type (NG, coal, uranium, wind, solar, etc.)
- Operating status (operating / planned / retired)
- Owner utility name + EIA utility ID

**New dependency:** `openpyxl>=3.1` (for reading `.xlsx` files)

**Report use cases:**
- Distance and bearing to nearest power plant(s) by type
- Total generation capacity within 10/25/50 miles
- Nearest natural gas plant, nearest renewable installation
- Context for grid stability, load centers

#### 2b. HIFLD Electric Retail Service Territories (Utility Polygons)

**Source:** Homeland Infrastructure Foundation-Level Data (DOE/DHS)  
**URL:** `https://hifld-geoplatform.opendata.arcgis.com/datasets/geoplatform::electric-retail-service-territories` (shapefile, ~70MB)  
**Format:** Shapefile (ogr2ogr → PostGIS polygon)  
**Content:**
- ~3,200 utility service territory polygons (IOUs, co-ops, municipals, public power)
- Utility name, EIA utility ID (joinable to EIA-860), NAICS code, entity type
- State, ownership type (investor-owned, cooperative, municipal, federal, other)

**Report use cases:**
- Exact identification of electric utility serving the site via `ST_Contains`
- Utility type (investor-owned vs. co-op vs. municipal — relevant to permitting, rates context)
- Join to EIA-860 for utility capacity profile

#### 2c. HIFLD Electric Transmission Lines

**Source:** Homeland Infrastructure Foundation-Level Data (DOE/DHS)  
**URL:** `https://hifld-geoplatform.opendata.arcgis.com/datasets/geoplatform::transmission-lines` (shapefile, ~200MB)  
**Format:** Shapefile (ogr2ogr → PostGIS linestring)  
**Content:**
- ~70,000+ transmission line segments (69 kV and above)
- Voltage class (69kV, 115kV, 138kV, 230kV, 345kV, 500kV+)
- Owner/operator name, operational status
- Line name/circuit ID where available

**Report use cases:**
- Distance to nearest transmission line (and voltage class)
- High-voltage transmission within X miles (relevant for large commercial/industrial loads)

#### 2d. HIFLD Electric Power Substations

**Source:** Homeland Infrastructure Foundation-Level Data (DOE/DHS)  
**URL:** `https://hifld-geoplatform.opendata.arcgis.com/datasets/geoplatform::electric-power-transmission-substations` (shapefile, ~5MB)  
**Format:** Shapefile → PostGIS point  
**Content:**
- ~80,000 substations (69 kV and above)
- Substation name, owner/operator
- Type (transformer, switching, etc.)
- Max voltage (kV) where recorded
- Operational status

**Report use cases:**
- Distance and direction to nearest substation(s)
- Nearest high-voltage substation (≥115kV) — relevant for large commercial/industrial power interconnection
- Complements transmission line proximity: a site near a high-voltage line but far from any substation has limited access to grid capacity

---

### 3. Water Utilities (Drinking Water)

Two datasets combined:

#### 3a. EPA SDWIS via ECHO Bulk Download

**Source:** EPA ECHO (Environmental Compliance History Online) bulk download  
**URL:** `https://echo.epa.gov/tools/data-downloads/sdwa-download-summary`  
**Format:** ZIP containing multiple CSVs (WATER_SYSTEM, SERVICE_AREA, VIOLATIONS, etc.)  
**Key tables:**
- `WATER_SYSTEM.csv` — PWSID, system name, type (CWS/NTNC/TNC), source type (GW/SW/GU), population served, owner type, primary state agency
- `SERVICE_AREA.csv` — PWSID → county/state mapping, service area type
- `VIOLATIONS.csv` — recent health-based violations (can be denormalized to summary counts)
- `GEOGRAPHIC_AREA.csv` — PWSID → zip code, city, county FIPS

**Note on system types:**
- CWS = Community Water System (piped to residences/businesses)
- NTNC = Non-Transient Non-Community (schools, offices)
- TNC = Transient Non-Community (campgrounds, gas stations)
- Source: GW = groundwater, SW = surface water, GU = groundwater under direct surface influence

**Report use cases:**
- Is there a CWS serving this area?
- PWS name and system type
- Water source type (groundwater vs. surface water)
- Violation history summary (recent health-based violations — count only, per the "no ratings" policy)

#### 3b. EPA Community Water System Service Area Boundaries

**Source:** EPA ArcGIS Open Data  
**URL:** `https://epa.maps.arcgis.com/home/item.html?id=80c6912ef14f46e480f5afd807767b4b` (shapefile export)  
**Format:** Shapefile (ogr2ogr → PostGIS polygon), PWSID as join key to SDWIS  
**Coverage:** ~44,000 CWS polygons (~99% of US consumers). Boundaries are either state/utility-supplied or EPA-modeled for completeness.  
**Freshness:** Updated ~annually by EPA (last update Feb 2026)

**Report use cases:**
- `ST_Contains(geom, site_point)` → which CWS polygon contains the site
- Join PWSID → SDWIS for system name, source type, population served
- "Site is within [utility name] service area (source: groundwater)"

---

### 4. USGS Groundwater

Two datasets:

#### 4a. USGS Principal Aquifers Shapefile

**Source:** USGS Ground Water Atlas (national, 1:2,500,000 scale)  
**URL:** `https://catalog.data.gov/dataset/aquifers1` (shapefile, ~5MB)  
**Format:** Shapefile (ogr2ogr → PostGIS polygon)  
**Content:**
- Polygon boundaries of all principal aquifer systems
- Formation name (e.g., "High Plains aquifer", "Mississippi River Valley alluvial aquifer")
- Aquifer type: unconsolidated sand and gravel / semiconsolidated sand / sandstone / carbonate / other
- Rock type text description

**Note on scale:** This is a 1:2.5M national dataset — it shows the general geology, not precise aquifer edges. A site "within" an aquifer polygon is in the general geological formation but surface conditions vary greatly.

**Report use cases:**
- Principal aquifer name (or "No principal aquifer mapped — may rely on local/minor aquifer")
- Aquifer type classification
- Context for groundwater availability potential

#### 4b. USGS NWIS Groundwater Monitoring Wells

**Source:** USGS National Water Information System  
**URL:** `https://waterdata.usgs.gov/nwis/si` (site inventory) + groundwater levels API  
**Format:** Tab-delimited RDB format (USGS standard) → parse to CSV  
**Download strategy:**
1. Bulk download all NWIS groundwater monitoring site inventory for CONUS via REST API: `https://waterservices.usgs.gov/nwis/site/?siteType=GW&siteStatus=all&hasDataTypeCd=gw&format=rdb`
2. For each site (or batch), download recent statistics (depth-to-water median, min, max) via: `https://waterservices.usgs.gov/nwis/stat/?sites={site_no}&statTypeCd=median,mean,min,max&parameterCd=72019`
   - `72019` = Depth to water level, feet below land surface

**Scale note:** ~800K groundwater sites nationally. We'll store site metadata for all, but only pre-aggregate depth-to-water statistics (not raw time series). Raw observations are available at query time via NWIS API if needed.

**Report use cases:**
- Nearest USGS groundwater monitoring wells (within 10 miles)
- Median depth to water table at nearest wells
- Aquifer code at each monitoring well (cross-reference with aquifer polygons)
- "Data available from X monitoring wells within 10 miles; median depth to water: Y feet"

---

## Database Migrations

### Migration 009: NOAA NClimGrid
**File:** `plinth/db/migrations/009_noaa_nclimgrid.sql`

NClimGrid rasters are stored as COGs in MinIO and indexed via the existing `raster_tiles` table — no new tables needed. Migration adds a comment/note only, OR can be skipped entirely and handled via registry only. **Decision: skip dedicated migration; use existing raster_tiles infrastructure.**

Actually: add a simple migration that documents the expected MinIO key pattern in a comment and ensures `raster_tiles` is sufficient (it is). Migration 009 will just be a schema comment migration marking the addition.

### Migration 010: EIA Power + HIFLD Electric
**File:** `plinth/db/migrations/010_eia_power.sql`

```sql
CREATE TABLE IF NOT EXISTS eia_power_plants (
    plant_id          INTEGER PRIMARY KEY,        -- EIA Plant Code
    plant_name        TEXT NOT NULL,
    utility_id        INTEGER,                    -- EIA Utility ID (joins to service territories)
    utility_name      TEXT,
    operator_name     TEXT,
    state             CHAR(2),
    county            TEXT,
    lat               NUMERIC(9,6),
    lon               NUMERIC(9,6),
    geom              GEOMETRY(POINT, 4326),
    install_year      SMALLINT,
    data_year         SMALLINT NOT NULL,
    -- aggregated from generator sheet (summed at plant level)
    capacity_mw_total NUMERIC,
    capacity_mw_by_fuel JSONB,                    -- {"NG": 450.0, "SUN": 200.0, ...}
    primary_fuel      TEXT,                       -- fuel of highest-capacity generator
    technology_types  TEXT[],                     -- distinct technologies at plant
    operating_status  TEXT,                       -- OP/RE/SB/CN etc.
    created_at        TIMESTAMPTZ DEFAULT now(),
    updated_at        TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_eia_plants_geom ON eia_power_plants USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_eia_plants_fuel ON eia_power_plants (primary_fuel);
CREATE INDEX IF NOT EXISTS idx_eia_plants_status ON eia_power_plants (operating_status);

CREATE TABLE IF NOT EXISTS electric_service_territories (
    id                SERIAL PRIMARY KEY,
    eia_id            TEXT,                        -- EIA utility ID (may be null for some)
    utility_name      TEXT NOT NULL,
    state             CHAR(2),
    naics_code        TEXT,
    entity_type       TEXT,                        -- IOU, COOP, MUN, FED, OTHER
    address           TEXT,
    city              TEXT,
    zip               TEXT,
    phone             TEXT,
    geom              GEOMETRY(MULTIPOLYGON, 4326) NOT NULL,
    source_date       TEXT,
    created_at        TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_service_territories_geom ON electric_service_territories USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_service_territories_eia_id ON electric_service_territories (eia_id);

CREATE TABLE IF NOT EXISTS electric_transmission_lines (
    id                SERIAL PRIMARY KEY,
    line_name         TEXT,
    owner             TEXT,
    voltage_kv        INTEGER,
    voltage_class     TEXT,                        -- '100-161', '230', '345', '500', '735 And Above', etc.
    status            TEXT,                        -- IN SERVICE, UNDER CONSTRUCTION, etc.
    geom              GEOMETRY(MULTILINESTRING, 4326) NOT NULL,
    source_date       TEXT,
    created_at        TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_transmission_lines_geom ON electric_transmission_lines USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_transmission_lines_voltage ON electric_transmission_lines (voltage_kv);

CREATE TABLE IF NOT EXISTS electric_substations (
    id                SERIAL PRIMARY KEY,
    substation_name   TEXT,
    owner             TEXT,
    substation_type   TEXT,                        -- TRANSFORMER, SWITCHING, etc.
    status            TEXT,                        -- IN SERVICE, UNDER CONSTRUCTION, etc.
    max_voltage_kv    INTEGER,
    state             CHAR(2),
    county            TEXT,
    city              TEXT,
    geom              GEOMETRY(POINT, 4326) NOT NULL,
    source_date       TEXT,
    created_at        TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_substations_geom ON electric_substations USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_substations_voltage ON electric_substations (max_voltage_kv);
```

### Migration 011: Water Utilities
**File:** `plinth/db/migrations/011_water_utilities.sql`

```sql
CREATE TABLE IF NOT EXISTS sdwis_water_systems (
    pwsid             TEXT PRIMARY KEY,            -- e.g. OK3000001
    pws_name          TEXT NOT NULL,
    pws_type_code     TEXT,                        -- CWS, NTNC, TNC
    primary_source    TEXT,                        -- GW, SW, GU, SWP, GUP, GWP
    owner_type_code   TEXT,                        -- F, L, M, N, P, S
    population_served INTEGER,
    service_connections INTEGER,
    state_code        CHAR(2),
    primary_county    TEXT,
    city_served       TEXT,
    zip_codes         TEXT[],
    counties_served   TEXT[],                      -- county FIPS codes from SERVICE_AREA
    activity_code     TEXT,                        -- A=active, I=inactive
    violation_count_5yr INTEGER DEFAULT 0,         -- health-based violations last 5 years
    data_quarter      TEXT,                        -- "2025Q4" — SDWIS reporting quarter
    created_at        TIMESTAMPTZ DEFAULT now(),
    updated_at        TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_sdwis_state ON sdwis_water_systems (state_code);
CREATE INDEX IF NOT EXISTS idx_sdwis_type ON sdwis_water_systems (pws_type_code);
CREATE INDEX IF NOT EXISTS idx_sdwis_source ON sdwis_water_systems (primary_source);
CREATE INDEX IF NOT EXISTS idx_sdwis_county ON sdwis_water_systems USING GIN (counties_served);

CREATE TABLE IF NOT EXISTS water_system_boundaries (
    id                SERIAL PRIMARY KEY,
    pwsid             TEXT NOT NULL,               -- joins to sdwis_water_systems
    pws_name          TEXT,
    boundary_source   TEXT,                        -- 'state_supplied', 'epa_modeled', 'utility_supplied'
    state_code        CHAR(2),
    geom              GEOMETRY(MULTIPOLYGON, 4326) NOT NULL,
    source_date       TEXT,
    created_at        TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_water_boundaries_geom ON water_system_boundaries USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_water_boundaries_pwsid ON water_system_boundaries (pwsid);
```

### Migration 012: USGS Groundwater
**File:** `plinth/db/migrations/012_groundwater.sql`

```sql
CREATE TABLE IF NOT EXISTS usgs_principal_aquifers (
    id                SERIAL PRIMARY KEY,
    aq_name           TEXT NOT NULL,               -- e.g. "High Plains aquifer"
    aq_code           TEXT,                        -- USGS aquifer code
    rock_type         TEXT,                        -- formation rock type description
    aquifer_type      TEXT,                        -- unconsolidated sand and gravel / carbonate / etc.
    geom              GEOMETRY(MULTIPOLYGON, 4326) NOT NULL,
    created_at        TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_aquifers_geom ON usgs_principal_aquifers USING GIST (geom);

CREATE TABLE IF NOT EXISTS usgs_groundwater_wells (
    site_no           TEXT PRIMARY KEY,            -- USGS site number
    station_nm        TEXT,
    state_cd          CHAR(2),
    county_cd         TEXT,
    aquifer_cd        TEXT,                        -- USGS local aquifer code
    well_depth_ft     NUMERIC,                     -- total well depth
    hole_depth_ft     NUMERIC,
    nat_aqfr_cd       TEXT,                        -- national aquifer code
    geom              GEOMETRY(POINT, 4326) NOT NULL,
    -- Pre-aggregated depth-to-water statistics (parameter 72019, ft below land surface)
    dtw_median_ft     NUMERIC,                     -- median depth to water (positive = below surface)
    dtw_mean_ft       NUMERIC,
    dtw_min_ft        NUMERIC,
    dtw_max_ft        NUMERIC,
    dtw_obs_count     INTEGER,                     -- number of observations
    dtw_period_start  DATE,
    dtw_period_end    DATE,
    created_at        TIMESTAMPTZ DEFAULT now(),
    updated_at        TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_gw_wells_geom ON usgs_groundwater_wells USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_gw_wells_aquifer ON usgs_groundwater_wells (nat_aqfr_cd);
CREATE INDEX IF NOT EXISTS idx_gw_wells_state ON usgs_groundwater_wells (state_cd);
```

---

## Ingestors

### `plinth/ingest/noaa_nclimgrid.py` — `NoaaNclimgridIngestor`

```
source_name = "noaa-nclimgrid"
update_frequency = "decadal"
```

**Download:**
- 4 NetCDF files from NOAA S3 HTTPS endpoint (public, no auth)
- Use `_download_if_changed()` for ETag-based idempotency

**Validate:**
- Each `.nc` file exists and > 1 MB
- Rasterio can open as NetCDF subdataset

**Load:**
- For each variable (tmax, tmin, tavg, prcp):
  1. Open via rasterio: `rasterio.open(f"NETCDF:{path}:{variable_name}")` — GDAL NetCDF driver exposes 12 monthly bands automatically
  2. Write 12-band float32 GeoTIFF
  3. Convert to COG via existing `to_cog()` helper
  4. Upload to MinIO key: `noaa-nclimgrid/1991-2020/{variable}.tif`
  5. Register in `raster_tiles` table with `dataset="noaa-nclimgrid"`, `tile_id=variable`
- Band order: 1=Jan, 2=Feb, ..., 12=Dec

**Register:** `_upsert_registry("1991-2020-v1.0", "national", notes)`

**No new dependencies** — rasterio already handles NetCDF via GDAL.

---

### `plinth/ingest/eia_860.py` — `Eia860Ingestor`

```
source_name = "eia-860"
update_frequency = "annual"
```

**Download:**
- Discover latest year from EIA-860 landing page (or hardcode latest year with env var override)
- Download `eia860{year}.zip` from `https://www.eia.gov/electricity/data/eia860/`
- Use `_download_if_changed()` for ETag caching

**Validate:**
- ZIP exists and > 1 MB
- Expected sheets present: `2___Plant_Y{year}.xlsx`, `3_1_Generator_Y{year}.xlsx`

**Load:**
- Parse plant sheet → dict keyed by plant_id
- Parse generator sheet → aggregate to plant level: sum MW capacity by fuel, collect unique technologies
- Build combined plant rows → upsert `eia_power_plants` with `INSERT … ON CONFLICT (plant_id) DO UPDATE`
- Geometry: `ST_SetSRID(ST_MakePoint(lon, lat), 4326)`

**Register:** `_upsert_registry(f"{year}", "national", notes)`

**New dependency needed:** `openpyxl>=3.1` → add to `pyproject.toml`

---

### `plinth/ingest/hifld_electric_territories.py` — `HifldElectricTerritoriesIngestor`

```
source_name = "hifld-electric-territories"
update_frequency = "annual"
```

**Download:**
- Download shapefile ZIP from HIFLD ArcGIS Open Data via direct download URL
- URL: `https://opendata.arcgis.com/api/v3/datasets/[item_id]/downloads/data?format=shp&spatialRefId=4326`
- Use `_download_if_changed()` for ETag

**Validate:** ZIP > 1 MB, shapefile present, geometry type is polygon

**Load:**
- Extract ZIP to staging dir
- Use `_ogr2ogr_to_staging_table()` → load raw into staging
- Or: use `ogr2ogr` subprocess directly to `electric_service_territories`
- Reproject to EPSG:4326 (shapefile may be WGS84 already)
- Upsert on `eia_id` or full replace (small enough table)

**Register:** `_upsert_registry("2025", "national", notes)`

---

### `plinth/ingest/hifld_transmission_lines.py` — `HifldTransmissionLinesIngestor`

```
source_name = "hifld-transmission-lines"
update_frequency = "annual"
```

Same pattern as territories ingestor but targeting `electric_transmission_lines`. Shapefile is ~200MB, expect longer processing time. ogr2ogr handles geometry → MULTILINESTRING.

---

### `plinth/ingest/hifld_substations.py` — `HifldSubstationsIngestor`

```
source_name = "hifld-substations"
update_frequency = "annual"
```

**Download:**
- Shapefile from HIFLD ArcGIS Open Data (~5MB): `https://hifld-geoplatform.opendata.arcgis.com/datasets/geoplatform::electric-power-transmission-substations`
- Use `_download_if_changed()` for ETag

**Validate:** ZIP > 500KB, point geometry type, NAME field present

**Load:**
- Extract → ogr2ogr → `electric_substations`
- Column mapping: `NAME` → `substation_name`, `OWNER` → `owner`, `TYPE` → `substation_type`, `STATUS` → `status`, `MAX_VOLT` → `max_voltage_kv`, `STATE` → `state`, `COUNTY` → `county`, `CITY` → `city`
- Full reload acceptable (small dataset, annual cadence)

**Register:** `_upsert_registry("2025", "national", notes)`

---

### `plinth/ingest/epa_sdwis.py` — `EpaSdwisIngestor`

```
source_name = "epa-sdwis"
update_frequency = "monthly"
```

**Download:**
- Bulk SDWA CSV ZIP from ECHO: `https://echo.epa.gov/files/echodownloads/SDWA_latest_downloads.zip`
- Use `_download_if_changed()` for ETag

**Validate:** ZIP > 10 MB, key CSVs present (WATER_SYSTEM, SERVICE_AREA, VIOLATIONS, GEOGRAPHIC_AREA)

**Load:**
1. Parse `WATER_SYSTEM.csv` → filter `PWS_TYPE_CODE IN ('CWS','NTNC')` (skip transient)
2. Parse `SERVICE_AREA.csv` → group by PWSID, collect county FIPS list
3. Parse `VIOLATIONS.csv` → count health-based violations per PWSID in last 5 years
4. Parse `GEOGRAPHIC_AREA.csv` → collect zip codes per PWSID
5. Join all → upsert `sdwis_water_systems` with `INSERT … ON CONFLICT (pwsid) DO UPDATE`

**Register:** `_upsert_registry(reporting_quarter, "national", notes)` — quarter extracted from CSV header

---

### `plinth/ingest/epa_water_boundaries.py` — `EpaWaterBoundariesIngestor`

```
source_name = "epa-water-boundaries"
update_frequency = "annual"
```

**Download:**
- EPA ArcGIS FeatureServer export: download as GeoJSON or shapefile from EPA's ArcGIS item `80c6912ef14f46e480f5afd807767b4b`
- Use the `/query` endpoint to paginate all features: `https://services.arcgis.com/cJ9YHowT8TU7DUyn/ArcGIS/rest/services/Water_System_Boundaries/FeatureServer/0/query?where=1=1&outFields=*&f=geojson&resultOffset={offset}`
- Save as paginated GeoJSON files, merge to single file

**Validate:** Features > 10,000, PWSID field present

**Load:**
- Use `ogr2ogr` to load merged GeoJSON → `water_system_boundaries`
- Upsert on `pwsid`

**Register:** `_upsert_registry("2026-02", "national", notes)`

---

### `plinth/ingest/usgs_aquifers.py` — `UsgsAquifersIngestor`

```
source_name = "usgs-aquifers"
update_frequency = "decadal"
```

**Download:**
- USGS Principal Aquifers shapefile from data.gov:
  `https://water.usgs.gov/GIS/dsdl/aquifers_us.zip` (USGS direct link, ~5MB)
- Use `_download_if_changed()` for ETag

**Validate:** ZIP > 500KB, shapefile present

**Load:**
- Extract ZIP → ogr2ogr → `usgs_principal_aquifers`
- Full reload acceptable (small table, decadal dataset)
- Column mapping: `AQ_NAME` → `aq_name`, `AQ_CODE` → `aq_code`, `ROCK_TYPE` → `rock_type`, etc.

**Register:** `_upsert_registry("2003", "national", notes)`

---

### `plinth/ingest/usgs_groundwater_wells.py` — `UsgsGroundwaterWellsIngestor`

```
source_name = "usgs-groundwater-wells"
update_frequency = "annual"
```

**Download (two-step):**

Step 1 — Site inventory (all groundwater monitoring sites, CONUS):
```
https://waterservices.usgs.gov/nwis/site/?siteType=GW&siteStatus=all&hasDataTypeCd=gw
  &stateCd={state}&format=rdb&siteOutput=expanded
```
Loop over all 50 states + DC. Save per-state RDB files to staging. ~800K sites total but many have no water level data.

Step 2 — Depth-to-water statistics per site (parameter 72019):
```
https://waterservices.usgs.gov/nwis/stat/?format=rdb&statTypeCd=median,mean,min,max
  &parameterCd=72019&siteType=GW&statReportType=annual
```
This returns pre-computed annual statistics. Filter to sites with observations.
Use state-by-state loop with rate limiting.

**Validate:** At least 500K site records, at least 100K with depth-to-water data

**Load:**
- Parse RDB (tab-delimited, skip `#` comment lines and type-descriptor row)
- Filter out sites missing lat/lon
- Upsert all sites → `usgs_groundwater_wells` with `INSERT … ON CONFLICT (site_no) DO UPDATE`
- Depth-to-water stats from step 2: update `dtw_*` columns for matching site_no

**Register:** `_upsert_registry(f"{current_year}", "national", notes)`

---

## CLI Registration

Add to `plinth/cli/ingest.py`:

**9 new subcommands:** `noaa-nclimgrid`, `eia-860`, `hifld-electric-territories`, `hifld-transmission-lines`, `hifld-substations`, `epa-sdwis`, `epa-water-boundaries`, `usgs-aquifers`, `usgs-groundwater-wells`

**Update `ingest_all`:** Append all national ingestors (note: the new ingestors are all national datasets, not region-scoped, so they run without a region parameter).

---

## New Dependency

Add to `pyproject.toml` dependencies:
```
"openpyxl>=3.1",    # EIA-860 Excel file parsing
```

All other new ingestors use: rasterio (NetCDF/COG), subprocess ogr2ogr (shapefiles/GeoJSON), csv/RDB parsing (SDWIS/NWIS) — all already available.

---

## DBML Update

Add to `docs/plinth.dbml`:
- `eia_power_plants` table
- `electric_service_territories` table
- `electric_transmission_lines` table
- `electric_substations` table
- `sdwis_water_systems` table
- `water_system_boundaries` table
- `usgs_principal_aquifers` table
- `usgs_groundwater_wells` table

---

## Data Sources Display Names

Add the following entry to `_SOURCE_DISPLAY` in `plinth/report/context.py` for the NClimGrid dataset. The dataset key must match `source_name = "noaa-nclimgrid"` in the ingestor.

```python
"noaa-nclimgrid": ("NOAA Monthly Gridded Climate Normals 1991–2020 (NClimGrid)", "MinIO COG", "1991–2020"),
```

> **Note:** NClimGrid rasters are stored in MinIO (not PostGIS), so the storage column reads `"MinIO COG"` rather than `"PostGIS"`. All other new sources (EIA, HIFLD, EPA, USGS vector datasets) are in PostGIS and are documented in their respective plan files.

---

## Future Query Functions (Out of Scope — Next Plan)

Once data is ingested, a follow-on plan will add query functions:

| Function | Returns |
|---|---|
| `query_noaa_nclimgrid(lat, lon)` | Monthly tmax/tmin/tavg/prcp at 5km grid cell |
| `query_electric_utility(lat, lon)` | Serving utility name/type; nearest plants by type; nearest transmission line; nearest substation |
| `query_water_utility(lat, lon)` | CWS name, source type, violation count; fallback county lookup |
| `query_groundwater(lat, lon)` | Principal aquifer name/type; nearest wells + median depth to water |

---

## Execution Order

```
Phase A — Migrations
  009_noaa_nclimgrid.sql   (comment migration, no new tables)
  010_eia_power.sql
  011_water_utilities.sql
  012_groundwater.sql

Phase B — Ingestors (can run in parallel within domain)
  Domain 1: noaa_nclimgrid (national raster)
  Domain 2: eia_860, hifld_electric_territories, hifld_transmission_lines, hifld_substations
  Domain 3: epa_sdwis, epa_water_boundaries
  Domain 4: usgs_aquifers, usgs_groundwater_wells

Phase C — Registration
  CLI subcommands
  ingest_all update

Phase D — Housekeeping
  openpyxl dependency + uv lock update
  DBML update
```

---

## Data Sizes / Storage Estimates

| Dataset | Format | Est. Size | Storage |
|---|---|---|---|
| NOAA NClimGrid (4 variables) | 4 COGs × 12 bands | ~80–120 MB in MinIO | MinIO |
| EIA-860 Power Plants | ~10,000 plant rows | < 5 MB in PG | PostGIS |
| HIFLD Service Territories | ~3,200 polygons | ~100–200 MB in PG | PostGIS |
| HIFLD Transmission Lines | ~70,000 line segments | ~300–500 MB in PG | PostGIS |
| HIFLD Substations | ~80,000 point features | ~20 MB in PG | PostGIS |
| SDWIS Water Systems | ~150,000 PWS rows | ~50 MB in PG | PostGIS |
| EPA CWS Boundaries | ~44,000 polygons | ~200–400 MB in PG | PostGIS |
| USGS Principal Aquifers | ~70 polygon features | < 5 MB in PG | PostGIS |
| USGS Groundwater Wells | ~800,000 point rows | ~300–500 MB in PG | PostGIS |
