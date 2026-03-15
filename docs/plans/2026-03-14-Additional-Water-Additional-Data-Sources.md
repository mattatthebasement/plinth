# Additional Water & Bedrock Data Sources Plan

**File:** `docs/plans/2026-03-14-Additional-Water-Additional-Data-Sources.md`  
**Status:** Draft

---

## Overview

This plan adds three new data domains:

1. **FEMA NFHL National Expansion** — expand the existing flood zone ingestor from NE-Oklahoma (8 counties) to all ~3,200 US counties
2. **USGS Hydrogeologic Framework** — a richer alternative to (and augmentation of) the existing principal aquifers layer, using USGS's 2025 national hydrogeologic regions and provinces datasets
3. **SoilGrids Depth to Bedrock** — two rasters from ISRIC SoilGrids at 250m resolution covering CONUS: absolute depth to bedrock (BDRICM) and probability of bedrock within 2m (BDRLOG)

**Out of scope:** Query functions and report integration (follow-on plan).

---

## Research Notes — What the User Asked For vs. What Exists

### USGS Ground Water Atlas: Minor Aquifers and Confining Units

The user asked for minor aquifer and confining unit data from the USGS Ground Water Atlas. Here is the reality of national data availability:

| Layer | Availability |
|---|---|
| **Principal aquifers** | ✅ National GIS shapefile — **already ingested** (migration 012, 4,637 polygons) |
| **Minor aquifers** | ❌ No national-scale GIS dataset. Minor aquifer mapping is conducted at the state or regional level by state geological surveys; there is no federal aggregation. |
| **Confining units** | ❌ No national GIS dataset. Confining unit delineation requires borehole data and regional interpretation that has not been compiled at national scale. |

**What we CAN add that is meaningful:**

USGS published two new national datasets in 2025 that represent a significant upgrade over the 2003 principal aquifers shapefile:

- **Hydrogeologic Provinces** — Divides CONUS into 8 broad hydrogeologic provinces based on geology and aquifer character (e.g., "Crystalline Rock," "Carbonate Rock," "Glacial Sediment," "Alluvial Valleys"). Useful for understanding the broader geological context of a site.
- **Hydrogeologic Regions** — Subdivides provinces into 24 regions, combining principal aquifer systems with secondary hydrogeologic areas. This dataset covers the entire CONUS without gaps (unlike the principal aquifers, which only show the named formations and leave large areas unmapped).

The key advantage of the hydrogeologic regions dataset: **full coverage**. The existing principal aquifer layer only covers mapped principal aquifer extents. A site in crystalline bedrock terrain (much of New England, Appalachians, Rockies) shows up as "no principal aquifer" — but it's not aquifer-free, it's just not a major sedimentary aquifer. The Hydrogeologic Regions layer gives a geologic context answer for every point in CONUS.

**Recommendation:** Add both hydrogeologic provinces and regions as new PostGIS layers. Keep the existing `usgs_principal_aquifers` as the authoritative principal aquifer layer (finer spatial detail for the major formations); add the 2025 layers for full-coverage context.

**Note on bedrock depth from aquifer data:** The aquifer/hydrogeologic layers describe aquifer *type* and *extent* but not depth to bedrock directly. Depth to bedrock comes from borehole data or modeled products — which is exactly what SoilGrids provides (see section 2 below).

---

## Dataset 1: USGS Hydrogeologic Framework (2025)

### 1a. Hydrogeologic Provinces

**Source:** USGS Data Release (2025)  
**URL:** `https://www.usgs.gov/data/hydrogeologic-provinces-conterminous-united-states`  
**ScienceBase item:** To be confirmed at ingest time  
**Format:** Shapefile  
**Geometry:** Polygon (8 provinces covering all of CONUS)  
**License:** CC0 1.0 (public domain)

**Fields of interest:**
- Province name (e.g., "Crystalline Rock Terrane," "Carbonate Rock Terrane," "Glacial Sediment and Alluvium")
- Province code / identifier

**What it tells us:**
- The fundamental hydrogeologic character of the terrain: whether groundwater is stored in porous sediment, fractured rock, karst limestone, etc.
- Pairs well with the principal aquifer name to give a complete picture: "Site is within the High Plains aquifer (Unconsolidated Sand and Gravel) — Alluvial Plains Province"

**Report use cases:**
- Hydrogeologic province classification for any site in CONUS
- Context for groundwater yield expectations (fractured rock vs. alluvial aquifer vs. karst)

### 1b. Hydrogeologic Regions

**Source:** USGS Data Release (2025)  
**URL:** `https://www.usgs.gov/data/hydrogeologic-regions-conterminous-united-states`  
**Format:** Shapefile  
**Geometry:** Polygon (24 regions, full CONUS coverage without gaps)  
**License:** CC0 1.0

**Fields of interest:**
- Region name
- Region code
- Secondary hydrogeologic type classification

**What it tells us:**
- More refined classification within each province (e.g., within the Western Interior Plains province: "Western Interior Grass Lands" vs. "Missouri Plateau Glaciated" vs. "Nebraska Sand Hills")
- Every point in CONUS gets a region label — no unmapped gaps

**Report use cases:**
- Fallback when site is not within a principal aquifer polygon — region provides geologic context
- Combined display: "[Region name] within [Province name] | Principal aquifer: [name or 'none mapped']"

---

## Dataset 2: SoilGrids Depth to Bedrock

### Source and Coverage

**Provider:** ISRIC World Soil Information — SoilGrids 250m  
**Reference:** Hengl, T. et al. (2017). SoilGrids250m: Global gridded soil information. *PLOS ONE* 12(2).  
**WCS Base URL:** `https://maps.isric.org/mapserv?SERVICE=WCS&VERSION=2.0.1`  
**Resolution:** 250m (~0.002°)  
**Projection:** Geographic (WGS84, EPSG:4326)  
**License:** CC-BY 4.0

### Two Layers

| Layer | Coverage ID | Units | Description |
|---|---|---|---|
| **BDRICM** | `BDRICM_M_250m_ll` | cm | Absolute depth to bedrock. **Censored at 200 cm** — a value of 200 means "bedrock is at or below 2 meters from surface." |
| **BDRLOG** | `BDRLOG_M_250m_ll` | 0–1 probability | Probability that bedrock occurs within the upper 200 cm. Values near 1.0 = bedrock likely within 2m; near 0.0 = bedrock likely deeper. |

### Why Both Layers

BDRICM alone is insufficient because it caps at 200cm. For most agricultural and geologically complex regions, bedrock is often deeper than 2m. The combination:
- BDRICM < 200: high confidence, we have an actual depth estimate (e.g., "bedrock at ~120 cm / ~4 ft")
- BDRICM = 200 AND BDRLOG high (>0.7): bedrock likely within or near 2m but depth uncertain
- BDRICM = 200 AND BDRLOG low (<0.3): bedrock is likely much deeper than 2m; this dataset can't resolve it

**Report use cases:**
- "Estimated depth to bedrock: ~1.2m (4 ft) — Source: SoilGrids 250m model"
- When BDRICM = 200: "Bedrock estimated deeper than 2m (SoilGrids model detection limit)"
- Combined with BDRLOG: "Probability of bedrock within 2m: 8% — bedrock likely deeper"
- Context for: foundation type selection, drilling/boring cost estimation, well development context, blasting risk

### Download Strategy: WCS Clip to CONUS

Rather than downloading the ~13 GB global raster, we will use the SoilGrids WCS service to retrieve a CONUS-clipped GeoTIFF for each layer:

**Bounding box (WGS84):** West=-125.0, South=24.0, East=-66.0, North=50.0

**WCS request pattern:**
```
https://maps.isric.org/mapserv?SERVICE=WCS&VERSION=2.0.1
  &REQUEST=GetCoverage
  &COVERAGEID=BDRICM_M_250m_ll
  &FORMAT=image/tiff
  &SUBSET=Long(-125,-66)
  &SUBSET=Lat(24,50)
```

**Expected CONUS output size:** ~2–3 GB per layer (roughly 1/4 of global file), before COG conversion.

**Storage pattern:**
- MinIO key: `soilgrids-bedrock/v2017/bdricm_conus.tif` and `bdrlog_conus.tif`
- Registered in `raster_tiles` with `dataset='soilgrids-bedrock'`

**Note:** ISRIC's WCS service has occasional downtime. The ingestor will use a retry loop with exponential backoff. If WCS is unavailable after exhausting retries, it will log a clear error and exit — the download can be retried by re-running the ingestor.

---

## Database Migrations

### Migration 017: USGS Hydrogeologic Framework
**File:** `plinth/db/migrations/017_hydrogeologic_framework.sql`

```sql
CREATE TABLE IF NOT EXISTS usgs_hydrogeologic_provinces (
    id           SERIAL PRIMARY KEY,
    prov_name    TEXT NOT NULL,       -- e.g. "Crystalline Rock Terrane"
    prov_code    TEXT,                -- USGS province code if present
    description  TEXT,               -- descriptive text from dataset
    geom         GEOMETRY(MULTIPOLYGON, 4326) NOT NULL,
    source_year  SMALLINT DEFAULT 2025,
    created_at   TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_hydro_provinces_geom
    ON usgs_hydrogeologic_provinces USING GIST (geom);

CREATE TABLE IF NOT EXISTS usgs_hydrogeologic_regions (
    id           SERIAL PRIMARY KEY,
    reg_name     TEXT NOT NULL,       -- e.g. "Nebraska Sand Hills"
    reg_code     TEXT,                -- USGS region code if present
    prov_name    TEXT,                -- parent province name (denormalized for query speed)
    prov_code    TEXT,
    description  TEXT,
    geom         GEOMETRY(MULTIPOLYGON, 4326) NOT NULL,
    source_year  SMALLINT DEFAULT 2025,
    created_at   TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_hydro_regions_geom
    ON usgs_hydrogeologic_regions USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_hydro_regions_prov
    ON usgs_hydrogeologic_regions (prov_code);
```

**No migration needed for SoilGrids** — rasters are indexed via the existing `raster_tiles` table with `dataset='soilgrids-bedrock'`.

---

## Ingestors

### `plinth/ingest/usgs_hydrogeologic_framework.py` — `UsgsHydrogeologicFrameworkIngestor`

```
source_name = "usgs-hydrogeologic-framework"
update_frequency = "decadal"
```

**Download:**
- Fetch ScienceBase item pages for both datasets to find the shapefile download URLs
- Download `hydrogeologic_provinces_conus.zip` and `hydrogeologic_regions_conus.zip`
- Use `_download_if_changed()` for ETag caching

**Validate:**
- ZIPs > 500 KB each
- Shapefiles present, geometry type polygon/multipolygon

**Load:**
- Extract ZIPs, run `ogr2ogr` → `usgs_hydrogeologic_provinces` and `usgs_hydrogeologic_regions`
- Full reload acceptable (small tables, decadal dataset)
- Map attribute names: inspect actual shapefile fields at ingest time, adapt column mapping

**Register:** `_upsert_registry("2025", "national", notes)`

---

### `plinth/ingest/soilgrids_bedrock.py` — `SoilgridsBedockIngestor`

```
source_name = "soilgrids-bedrock"
update_frequency = "decadal"
```

**Download:**
- WCS GetCoverage request for each layer (BDRICM, BDRLOG) clipped to CONUS
- Use `subprocess` + `curl` (or `urllib`) to execute WCS requests
- Cache downloaded GeoTIFF files in staging with ETag/file-size check

**Validate:**
- Each downloaded GeoTIFF is > 100 MB (sanity check against empty/error responses)
- `rasterio.open()` succeeds on each file; check band count and CRS

**Load:**
- Convert each GeoTIFF to COG using `to_cog()` helper (DEFLATE compression, PREDICTOR=2)
- Upload COGs to MinIO: `soilgrids-bedrock/v2017/bdricm_conus.tif` and `bdrlog_conus.tif`
- Register both in `raster_tiles` table:
  - `dataset='soilgrids-bedrock'`, `tile_id='bdricm'` and `tile_id='bdrlog'`
  - `bounds` = CONUS bounding box polygon
  - `minio_key` = MinIO path

**Register:** `_upsert_registry("v2017", "national", notes)`

---

## CLI Registration

Add to `plinth/cli/ingest.py`:
- `usgs-hydrogeologic-framework` subcommand
- `soilgrids-bedrock` subcommand
- Add both to `ingest_all` (national datasets, no region parameter)
- `fema-nfhl` already registered; update `ingest_all` to call it without a region filter for national run

---

## DBML Update

Add to `docs/plinth.dbml`:
- `usgs_hydrogeologic_provinces` table
- `usgs_hydrogeologic_regions` table
- Note in `raster_tiles` comment: SoilGrids bedrock tiles (`soilgrids-bedrock/v2017/bdricm_conus.tif`, `bdrlog_conus.tif`)

---

## What We Can Derive in the Report (Future Plan)

| Query | Data Source | Value to User |
|---|---|---|
| Principal aquifer name + type | existing `usgs_principal_aquifers` | "High Plains aquifer (Unconsolidated Sand & Gravel)" |
| Hydrogeologic province + region | new `usgs_hydrogeologic_provinces` + `usgs_hydrogeologic_regions` | Context when no principal aquifer mapped; broader geology classification |
| Estimated depth to bedrock | SoilGrids BDRICM COG | "~1.2m (4 ft)" — relevant to foundation and boring costs |
| Bedrock confidence | SoilGrids BDRLOG COG | "8% probability within 2m" — confidence qualifier |
| Combined groundwater context | All of the above + Ma WTD + NWIS well readings | Full groundwater section of report |

**Key display logic for bedrock depth:**
- BDRICM < 200 cm: Show value as feet and meters. "Estimated depth to bedrock: {bdricm/30.48:.0f} ft (~{bdricm/100:.1f} m)"
- BDRICM = 200 cm AND BDRLOG < 0.3: "Bedrock not detected within model range (>2m / >6.5 ft)"
- BDRICM = 200 cm AND BDRLOG >= 0.3: "Possible bedrock within 2m — model uncertainty is high (probability: {bdrlog*100:.0f}%)"
- All cases: cite SoilGrids, note that model is not a substitute for geotechnical investigation

---

## Design Decisions (Confirmed)

1. **Minor aquifers:** National GIS data does not exist. Hydrogeologic Provinces + Regions datasets are the accepted substitute. No state-level data at this time.

2. **Confining units:** No national layer. Hydrogeologic province/region classification (e.g., "Carbonate Rock Terrane" implies confined aquifer conditions) is the accepted proxy. Not shown as an explicit confining unit polygon.

3. **SoilGrids version:** BDRICM/BDRLOG are from SoilGrids v1 (2017 product). SoilGrids 2.0 has not re-released these layers. Appropriate since bedrock depth is slow-changing. Cite as "SoilGrids 250m (Hengl et al. 2017)" in report.

4. **BDRLOG use:** Used internally as an uncertainty flag only (not displayed directly to users). Display logic: BDRICM < 200 → show depth; BDRICM = 200 AND BDRLOG < 0.3 → "not detected within model range"; BDRICM = 200 AND BDRLOG ≥ 0.3 → "possible bedrock near surface, model uncertain."

5. **NHD floodplain layers:** NHDPlus HR does **not** contain floodplain polygons. NHDPlus has stream network geometry and catchments, not flood extent mapping. FEMA NFHL + `fema_unmapped_areas` is the definitive source for mapped flood hazard data — expanding it nationally is the right approach.

6. **FEMA download method:** Expand the existing REST API per-county pattern (which already works for NE Oklahoma) to national scale. No new download approach needed; the FEMA ArcGIS REST service is reliable for per-county queries. State-level GDB bulk downloads from FEMA Map Service Center are an option but require portal navigation and are harder to automate for monthly refreshes.

---

## Dataset 0: FEMA NFHL — National Expansion

### Current State

`plinth/ingest/fema_nfhl.py` already implements the full NFHL ingestion pipeline:
- Pages the FEMA ArcGIS REST API (layer 28 — Flood Hazard Zones) per county
- Loads via `ogr2ogr` into `fema_flood_zones`
- Computes `fema_unmapped_areas` (county boundary minus flood zones)
- Fully idempotent with date-based GeoJSON cache

The only limitation: county list is hardcoded to 8 NE-Oklahoma counties.

### What Changes

**In `fema_nfhl.py`:**
1. Replace `NE_OKLAHOMA_COUNTIES` hardcoded dict with a dynamic query against `census_counties` (or derive from `census_block_groups`) — pull all `(statefp || countyfp, name)` pairs for the contiguous US (exclude territories and Alaska/Hawaii if desired, or include all)
2. Add `ThreadPoolExecutor` (4–8 workers) for concurrent county fetches — sequential download of 3,200 counties would take ~3–5 hours; parallel cuts it to under an hour
3. Handle FEMA REST API rate limiting: add per-thread exponential backoff on 429/503
4. Update `register()` to set `coverage_region="national"` when running without region filter
5. Keep `--region ne-oklahoma` as a fast dev/test path (hardcoded or passed as filter)

**Prerequisite:** Census TIGER national data must be loaded before NFHL national run (needed for unmapped area computation). We already have a national census-tiger ingestor.

**No migration needed** — `fema_flood_zones` and `fema_unmapped_areas` are already national-scale tables (indexed by `county_fips`, no region filter in schema).

### Runtime Estimate (National)
- ~3,200 counties × ~2s each / 8 parallel workers ≈ ~13 minutes download time
- Loading + unmapped area computation: ~1–2 hours total
- FEMA GeoJSON cache files: ~50–200 KB per county → ~0.5–0.7 GB total staging

### What We Get
- Flood zone classifications (Zone A, AE, AH, AO, V, VE, X, X500, etc.) for every US county that FEMA has mapped
- `fema_unmapped_areas` for every county — critical for the "no FEMA data ≠ Zone X" rule
- ~15–20% of US has no FEMA mapping — these counties are captured as unmapped areas
- Monthly refresh: re-run ingestor to pick up new FIRMs (Flood Insurance Rate Maps) as they're published

### Report Use Cases (Future Plan)
- Primary flood zone classification: "Zone AE — 1% annual chance floodplain"
- Unmapped flag: "FEMA flood mapping not available for this area"
- Distance to nearest flood zone boundary
- Base Flood Elevation (BFE) where available in the ArcGIS layer

---

---

## Execution Order

```
Phase A — Migrations
  017_hydrogeologic_framework.sql          pending

Phase B — Ingestors
  fema_nfhl (national expansion)           pending (modify existing ingestor)
  usgs_hydrogeologic_framework             pending (provinces + regions)
  soilgrids_bedrock                        pending (BDRICM + BDRLOG WCS download)

Phase C — Registration
  CLI commands                             pending
  ingest_all update                        pending

Phase D — Housekeeping
  DBML update                             pending
```
