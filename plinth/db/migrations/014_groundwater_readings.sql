-- Migration 014: USGS groundwater well recent discrete readings
-- Stores the last 3 years of discrete DTW measurements per monitoring well.
-- Up to 5 most recent readings per site are retained.
-- Used in reports to cross-check modeled water table depth (Ma et al. 2025)
-- against real observed values at nearby wells.

CREATE TABLE IF NOT EXISTS usgs_groundwater_well_readings (
    id            SERIAL PRIMARY KEY,
    site_no       TEXT NOT NULL REFERENCES usgs_groundwater_wells(site_no) ON DELETE CASCADE,
    lev_dt        DATE NOT NULL,
    lev_va        NUMERIC,              -- depth to water, ft below land surface
    lev_meth_cd   CHAR(1),             -- measurement method (S=steel tape, A=airline, etc.)
    lev_status_cd CHAR(1),             -- blank=normal, P=partial
    created_at    TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_gw_readings_site ON usgs_groundwater_well_readings (site_no);
CREATE INDEX IF NOT EXISTS idx_gw_readings_date ON usgs_groundwater_well_readings (lev_dt DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_gw_readings_unique ON usgs_groundwater_well_readings (site_no, lev_dt);
