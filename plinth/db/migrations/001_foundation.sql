-- 001_foundation.sql
-- Core tables required by all subsequent phases.
-- Applied once by: plinth-cli db migrate

-- Tracks every data source: version, download date, next review date.
-- One row per source; upserted by each ingestor's register() method.
CREATE TABLE IF NOT EXISTS data_source_registry (
    source_name       TEXT PRIMARY KEY,
    dataset_version   TEXT,
    last_downloaded   TIMESTAMPTZ,
    update_frequency  TEXT,    -- 'monthly', 'annual', 'decadal'
    next_review_date  DATE,
    coverage_region   TEXT,    -- 'ne-oklahoma', 'oklahoma', 'national'
    notes             TEXT
);

-- Spatial index of all COG tiles stored in MinIO.
-- PostGIS holds only tile bounds; the actual raster data lives in MinIO.
CREATE TABLE IF NOT EXISTS raster_tiles (
    id              SERIAL PRIMARY KEY,
    dataset         TEXT        NOT NULL,   -- e.g. 'usgs-3dep', 'nlcd'
    s3_key          TEXT        NOT NULL UNIQUE,
    bounds          GEOMETRY(Polygon, 4326) NOT NULL,
    resolution_m    NUMERIC,
    tile_id         TEXT,
    dataset_version TEXT,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS raster_tiles_bounds_idx  ON raster_tiles USING GIST (bounds);
CREATE INDEX IF NOT EXISTS raster_tiles_dataset_idx ON raster_tiles (dataset);

-- Cached results from API-based sources (NASA POWER, EPA AQS, Census ACS, etc.).
-- cache_key format is dataset-specific: e.g. 'nasa-power:{grid_cell}:{params}:{dates}'
CREATE TABLE IF NOT EXISTS query_cache (
    cache_key   TEXT PRIMARY KEY,
    dataset     TEXT        NOT NULL,
    input_lat   NUMERIC,
    input_lon   NUMERIC,
    result_json JSONB,
    cached_at   TIMESTAMPTZ DEFAULT now(),
    expires_at  TIMESTAMPTZ             -- NULL = no expiry
);

CREATE INDEX IF NOT EXISTS query_cache_expires_idx
    ON query_cache (expires_at)
    WHERE expires_at IS NOT NULL;

-- Archive of every generated report with a snapshot of source versions at generation time.
CREATE TABLE IF NOT EXISTS report_archive (
    report_id            TEXT PRIMARY KEY,
    generated_at         TIMESTAMPTZ DEFAULT now(),
    input_address        TEXT,
    lat                  NUMERIC,
    lon                  NUMERIC,
    source_versions_json JSONB,  -- snapshot of data_source_registry at report time
    pdf_storage_key      TEXT    -- MinIO key for the stored PDF
);
