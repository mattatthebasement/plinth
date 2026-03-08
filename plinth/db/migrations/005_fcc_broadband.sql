-- 005_fcc_broadband.sql
-- Phase 2: FCC National Broadband Map availability data (bulk state CSVs).
-- Applied once by: plinth-cli db migrate

-- ── FCC Broadband Coverage ────────────────────────────────────────────────────
--
-- One row per (location, provider, technology). Populated by the FCC BDC bulk
-- ingestor from State/Location Coverage CSV files. Queried at report time by
-- joining block_geoid against census_block_groups.geoid (first 12 chars of
-- the 15-digit block_geoid = block group GEOID).
--
-- Satellite technologies (60 = GSO, 61 = NGSO) are excluded at ingest time;
-- they cover essentially all locations and are handled separately in the report.

CREATE TABLE IF NOT EXISTS fcc_broadband_coverage (
    id                          BIGSERIAL PRIMARY KEY,
    location_id                 BIGINT      NOT NULL,
    provider_id                 TEXT        NOT NULL,
    brand_name                  TEXT        NOT NULL,
    technology_code             SMALLINT    NOT NULL,
    max_download_mbps           INTEGER     NOT NULL,
    max_upload_mbps             INTEGER     NOT NULL,
    low_latency                 BOOLEAN     NOT NULL,
    business_residential_code   CHAR(1)     NOT NULL,
    block_geoid                 CHAR(15)    NOT NULL,
    state_fips                  CHAR(2)     NOT NULL,
    as_of_date                  DATE        NOT NULL,
    UNIQUE (location_id, provider_id, technology_code)
);

-- Primary spatial lookup: block_geoid prefix JOIN to census_block_groups.geoid
CREATE INDEX IF NOT EXISTS fcc_broadband_block_geoid_idx
    ON fcc_broadband_coverage (block_geoid);

-- For future per-location fabric lookups
CREATE INDEX IF NOT EXISTS fcc_broadband_location_id_idx
    ON fcc_broadband_coverage (location_id);

-- For state-level filtering / re-ingest
CREATE INDEX IF NOT EXISTS fcc_broadband_state_fips_idx
    ON fcc_broadband_coverage (state_fips);
