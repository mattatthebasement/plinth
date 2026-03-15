-- Migration 012: USGS groundwater tables
--
-- Adds two tables covering groundwater availability and aquifer systems:
--   usgs_principal_aquifers  — USGS national aquifer polygon boundaries
--   usgs_groundwater_wells   — USGS NWIS groundwater monitoring well inventory
--
-- Sources:
--   USGS Ground Water Atlas principal aquifers — https://water.usgs.gov/GIS/dsdl/aquifers_us.zip
--   USGS NWIS groundwater site inventory       — https://waterservices.usgs.gov/nwis/site/
-- Refresh: usgs_principal_aquifers = decadal; usgs_groundwater_wells = annual

-- ---------------------------------------------------------------------------
-- USGS Principal Aquifers — national aquifer formation polygons
--
-- ~70 polygon features at 1:2,500,000 national scale from the USGS Ground
-- Water Atlas. Shows the general geological aquifer systems underlying CONUS.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS usgs_principal_aquifers (
    id           SERIAL  PRIMARY KEY,
    aq_name      TEXT    NOT NULL,      -- e.g. "High Plains aquifer"
    aq_code      TEXT,                  -- USGS aquifer code
    rock_type    TEXT,                  -- formation rock type description
    aquifer_type TEXT,                  -- unconsolidated sand and gravel / carbonate / sandstone / etc.
    geom         GEOMETRY(MULTIPOLYGON, 4326) NOT NULL,
    created_at   TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_aquifers_geom ON usgs_principal_aquifers USING GIST (geom);

-- ---------------------------------------------------------------------------
-- USGS NWIS Groundwater Monitoring Wells — point locations with depth statistics
--
-- ~800K groundwater monitoring sites nationally. Depth-to-water statistics
-- (parameter 72019 = depth below land surface, ft) are pre-aggregated at
-- ingest time so query functions do not require NWIS API calls at report time.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS usgs_groundwater_wells (
    site_no          TEXT        PRIMARY KEY,   -- USGS site number
    station_nm       TEXT,
    state_cd         CHAR(2),
    county_cd        TEXT,                      -- 5-digit county FIPS
    aquifer_cd       TEXT,                      -- USGS local aquifer code
    nat_aqfr_cd      TEXT,                      -- national aquifer code
    well_depth_ft    NUMERIC,                   -- total well depth (ft)
    hole_depth_ft    NUMERIC,                   -- borehole depth (ft)
    geom             GEOMETRY(POINT, 4326)  NOT NULL,
    -- Pre-aggregated depth-to-water statistics (positive = below land surface, ft)
    dtw_median_ft    NUMERIC,
    dtw_mean_ft      NUMERIC,
    dtw_min_ft       NUMERIC,
    dtw_max_ft       NUMERIC,
    dtw_obs_count    INTEGER,
    dtw_period_start DATE,
    dtw_period_end   DATE,
    created_at       TIMESTAMPTZ DEFAULT now(),
    updated_at       TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_gw_wells_geom    ON usgs_groundwater_wells USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_gw_wells_aquifer ON usgs_groundwater_wells (nat_aqfr_cd);
CREATE INDEX IF NOT EXISTS idx_gw_wells_state   ON usgs_groundwater_wells (state_cd);
CREATE INDEX IF NOT EXISTS idx_gw_wells_county  ON usgs_groundwater_wells (county_cd);
