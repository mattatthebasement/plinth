# Plinth — Copilot Instructions

## What This Project Is

Plinth is a paid, on-demand PDF site intelligence report service for real estate developers. A user submits a US address, pays, and receives a downloadable PDF within minutes that aggregates 100+ site context variables (environmental risk, physical conditions, climate, solar, demographics) from public datasets. The PDF is the primary deliverable.

**Status:** Pre-development. The repository currently holds planning documents only. Code is being built against the POC plan in `docs/plans/`.

---

## Stack

| Layer | Technology |
|---|---|
| Language | Python, managed with **uv** (not pip, not poetry) |
| API server | FastAPI |
| Database | PostgreSQL 15 + PostGIS |
| Object storage | MinIO (self-hosted) — raster COG tiles |
| Orchestration | Prefect 3 |
| CLI | Click (`plinth-cli`) |
| PDF generation | WeasyPrint + Jinja2 |
| Maps | Mapbox Static Images API |
| Charts | matplotlib (saved as PNG, embedded in HTML→PDF) |
| Infrastructure | Docker Compose on a single self-hosted server (Ubuntu 24.04 LTS or macOS with OrbStack) |

---

## Development Commands

The stack runs entirely in Docker Compose. There is no local dev server — code runs inside containers.

```bash
# Start all services
docker compose up -d

# Full teardown + rebuild from scratch
docker compose down -v && ./scripts/bootstrap.sh

# Run CLI commands (always via uv run inside the worker container)
uv run plinth-cli db migrate
uv run plinth-cli db status
uv run plinth-cli ingest fema-nfhl --region ne-oklahoma
uv run plinth-cli ingest all --region ne-oklahoma
uv run plinth-cli raster index
uv run plinth-cli cache clear --dataset nasa-power
uv run plinth-cli query all --lat 36.322 --lon -95.842
uv run plinth-cli report generate --address "11822 E 116th St N, Collinsville, OK"

# Run all tests
uv run pytest

# Run a single test file
uv run pytest tests/test_ingest/test_fema_nfhl.py

# Run a single test by name
uv run pytest tests/test_ingest/test_fema_nfhl.py -k "test_function_name"
```

---

## Repository Structure

```
plinth/
├── docker-compose.yml
├── docker-compose.override.yml   # local dev overrides
├── .env.example                  # committed; .env is NOT committed
├── pyproject.toml                # uv-managed; defines plinth-cli entry point
├── uv.lock
├── Dockerfile.worker
├── scripts/bootstrap.sh          # one-shot env setup
├── docs/
│   ├── plans/                    # POC and feature plans
│   └── Plinth Requirements.md    # full product requirements
├── plinth/
│   ├── config.py                 # pydantic-settings; all env config
│   ├── cli/                      # Click entry points
│   ├── ingest/                   # one module per data source
│   │   ├── base.py               # BaseIngestor abstract class
│   │   ├── fema_nfhl.py, census_tiger.py, ...
│   │   └── api/                  # query-time API clients (not bulk)
│   ├── flows/                    # Prefect flows (scheduled refresh)
│   ├── db/
│   │   ├── connection.py
│   │   └── migrations/           # numbered .sql files (001_foundation.sql, ...)
│   ├── raster/
│   │   ├── cog.py                # gdal_translate COG conversion
│   │   ├── clip.py               # bounding-box clip with buffer
│   │   └── minio.py              # upload/download/presign helpers
│   └── query/                    # spatial lookup functions (one per dataset)
└── tests/
    ├── conftest.py
    ├── test_ingest/
    └── test_raster/
```

---

## Architecture

### Data Flow

1. **Ingestion** — Prefect flows run ingestors that download public datasets, validate them, and load into PostGIS (vector) or MinIO (raster COGs). The `data_source_registry` table tracks every source with version, download date, and next review date.

2. **Query layer** — At report time, a set of `query_*` functions accept `(lat, lon)` and return structured data. Vector data comes from PostGIS spatial queries; raster values are extracted by finding the matching tile in `raster_tiles`, fetching the COG from MinIO, and clipping to the AOI. API-based sources (NASA POWER, EPA AQS, etc.) are fetched live and cached in `query_cache`.

3. **Report generation** — All query results feed a Jinja2 HTML template rendered to PDF by WeasyPrint. Maps are Mapbox Static Images API PNGs. Charts are matplotlib PNGs.

### Key Database Tables

- `data_source_registry` — one row per dataset; tracks version, download date, coverage region
- `raster_tiles` — spatial index (GIST on bounds) of all COG tiles stored in MinIO
- `query_cache` — dataset-specific cached results with TTL; keys are structured (e.g., `nasa-power:{grid_cell_id}:{param_hash}:{date_range}`)
- `report_archive` — every generated report with a snapshot of source versions

### Services (Docker Compose)

| Service | Image | Ports |
|---|---|---|
| `postgres` | `postgis/postgis:15-3.4` | 5432 |
| `minio` | `minio/minio:latest` | 9000 (API), 9001 (Console) |
| `prefect-server` | `prefecthq/prefect:3-latest` | 4200 |
| `prefect-worker` | custom `Dockerfile.worker` | — |
| `api` | custom (FastAPI, later phase) | 8000 |

---

## Key Conventions

### Ingestors

Every data source has an ingestor that extends `BaseIngestor` and follows this contract in order:
1. **Download** — idempotent; use ETag/content-hash checks, never re-download unchanged files
2. **Validate** — file integrity + record count sanity check
3. **Load** — upsert into PostGIS (`INSERT ... ON CONFLICT DO UPDATE`); **never** `TRUNCATE + INSERT`
4. **Register** — upsert a row in `data_source_registry`

### Rasters

- All rasters stored as Cloud-Optimized GeoTIFFs (COGs) in MinIO
- MinIO key pattern: `{dataset}/{version}/{tile_id}.tif` (e.g., `usgs-3dep/2023/n37w096.tif`)
- PostGIS holds only the tile index (`raster_tiles`), not raster data
- When computing slope from a DEM, always buffer the clip by ≥1 grid cell (~10m for 3DEP) **before** running `gdal.DEMProcessing`. Clipping exactly to the AOI produces incorrect edge values.

### Query Cache

Cache keys are dataset-specific compound strings, **not** flat proximity hashes:
- `nasa-power:{grid_cell_id}:{param_hash}:{date_range}`
- `epa-aqs:{county_fips}:{year}`
- `usgs-eq:{grid_cell_100km}:{start_year}:{mag_threshold}`
- `fcc-broadband:{location_id}`

### FEMA Flood Data

FEMA NFHL must have a companion `fema_unmapped_areas` layer (county boundary minus all flood zone polygons). A site with no FEMA flood data **must never** silently appear as Zone X — ~15–20% of the US has no FEMA mapping.

### Census Demographics

ACS demographic values are fetched via Census API at query time and cached — they are **not** bulk-loaded. Only TIGER geometries (block groups, tracts) are stored in PostGIS. Radius buffers use area-weighted intersections with PostGIS `geography` type for geodesic accuracy.

### Report Output Constraints

- Present raw data values only — do not derive risk ratings, suitability assessments, or engineering determinations
- Every API-sourced data field has a defined failure behavior: inline data-availability flag (never silent blank, never error)
- FEMA NRI results must be labeled "Source: FEMA National Risk Index" — it's FEMA's composite model, not a derived rating
- FCC broadband data requires a mandatory disclaimer about ISP self-reporting in every report
- No color-coded risk rating system without explicit sourcing and legal review

### Environment / Secrets

- `.env` lives at project root; never committed
- `.env.example` is committed and documents every required variable
- Key variables: `MAPBOX_TOKEN`, `CENSUS_API_KEY`, `EPA_AQS_KEY`, `EPA_AQS_EMAIL`, `POSTGRES_PASSWORD`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`

---

## Test Coordinate

Use this coordinate as the canonical test input for all query functions, integration tests, and end-to-end validation:

| | |
|---|---|
| **Address** | 11822 E 116th St N, Collinsville, OK 74021 |
| **Lat/Lon** | 36.32197414685, -95.842032856739 |
| **County** | Tulsa County, OK (FIPS 40143) |
| **NHDPlus VPU** | 11 (Arkansas-White-Red) |
| **Expected IECC Zone** | 3A (Warm Humid) |

---

## Data Sources Reference

| Source | Storage | Refresh |
|---|---|---|
| FEMA NFHL (flood zones) | PostGIS | Monthly |
| Census TIGER (block groups, tracts) | PostGIS | Annual |
| IECC Climate Zones | PostGIS | Per code cycle |
| FEMA NRI | PostGIS (joined to TIGER tracts) | Annual |
| NHDPlus HR (hydrography) | PostGIS | Annual |
| USDA SSURGO (soil) | PostGIS | Annual |
| NOAA Climate Normals | PostGIS (point geometry) | Decadal |
| USGS 3DEP (DEM, ~10m) | MinIO COG | Annual |
| NLCD (land cover) | MinIO COG | Annual |
| USGS Seismic Hazard PGA | MinIO COG | Annual |
| USDA Wildfire Hazard Potential | MinIO COG | Annual |
| NASA POWER (climate/solar) | `query_cache` (30d TTL) | API at query time |
| EPA AQS (air quality) | `query_cache` (365d TTL) | API at query time |
| USGS Earthquake Catalog | `query_cache` (30d TTL) | API at query time |
| FCC Broadband | `query_cache` (90d TTL) | API at query time |
| Census ACS (demographics) | `query_cache` (365d TTL) | API at query time |
