-- Migration 011: Water utility tables (drinking water)
--
-- Adds two tables covering public water systems and their service areas:
--   sdwis_water_systems    — EPA SDWIS public water system registry (tabular)
--   water_system_boundaries — EPA CWS service area polygon boundaries
--
-- Sources:
--   EPA SDWIS via ECHO bulk download — https://echo.epa.gov/tools/data-downloads/sdwa-download-summary
--   EPA CWS Service Area Boundaries  — https://www.epa.gov/ground-water-and-drinking-water/community-water-system-service-area-boundaries
-- Refresh: sdwis_water_systems = monthly; water_system_boundaries = annual

-- ---------------------------------------------------------------------------
-- EPA SDWIS Water Systems — one row per public water system (national)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sdwis_water_systems (
    pwsid               TEXT        PRIMARY KEY,    -- e.g. OK3000001
    pws_name            TEXT        NOT NULL,
    pws_type_code       TEXT,                       -- CWS / NTNC / TNC
    primary_source      TEXT,                       -- GW / SW / GU / SWP / GUP / GWP
    owner_type_code     TEXT,                       -- F=Federal L=Local M=Municipal N=Native P=Private S=State
    population_served   INTEGER,
    service_connections INTEGER,
    state_code          CHAR(2),
    primary_county      TEXT,
    city_served         TEXT,
    zip_codes           TEXT[],                     -- zip codes served (from GEOGRAPHIC_AREA)
    counties_served     TEXT[],                     -- county FIPS codes (from SERVICE_AREA)
    activity_code       TEXT,                       -- A=active I=inactive
    violation_count_5yr INTEGER     DEFAULT 0,      -- health-based violations last 5 years
    data_quarter        TEXT,                       -- reporting quarter e.g. "2025Q4"
    created_at          TIMESTAMPTZ DEFAULT now(),
    updated_at          TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sdwis_state    ON sdwis_water_systems (state_code);
CREATE INDEX IF NOT EXISTS idx_sdwis_type     ON sdwis_water_systems (pws_type_code);
CREATE INDEX IF NOT EXISTS idx_sdwis_source   ON sdwis_water_systems (primary_source);
CREATE INDEX IF NOT EXISTS idx_sdwis_activity ON sdwis_water_systems (activity_code);
CREATE INDEX IF NOT EXISTS idx_sdwis_counties ON sdwis_water_systems USING GIN (counties_served);

-- ---------------------------------------------------------------------------
-- EPA CWS Service Area Boundaries — polygon boundaries per community water system
--
-- Coverage: ~44,000 CWS polygons (~99% of US consumers served by CWS).
-- Boundaries are either state/utility-supplied or EPA-modeled for national completeness.
-- Join to sdwis_water_systems on pwsid for system metadata.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS water_system_boundaries (
    id              SERIAL      PRIMARY KEY,
    pwsid           TEXT        NOT NULL,           -- joins to sdwis_water_systems
    pws_name        TEXT,
    boundary_source TEXT,                           -- state_supplied / epa_modeled / utility_supplied
    state_code      CHAR(2),
    geom            GEOMETRY(MULTIPOLYGON, 4326) NOT NULL,
    source_date     TEXT,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_water_boundaries_geom  ON water_system_boundaries USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_water_boundaries_pwsid ON water_system_boundaries (pwsid);
CREATE INDEX IF NOT EXISTS idx_water_boundaries_state ON water_system_boundaries (state_code);
