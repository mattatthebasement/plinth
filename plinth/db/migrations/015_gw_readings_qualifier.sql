-- Migration 015: Add qualifier column to usgs_groundwater_well_readings
-- Stores the USGS OGC API qualifier list (e.g. Static, Dry, Pumping, Flowing)
-- as a single text value so reports can surface why a reading has no depth value.
-- Also removes the now-unused lev_status_cd column (legacy RDB field not
-- returned by the new OGC API).

ALTER TABLE usgs_groundwater_well_readings
    ADD COLUMN IF NOT EXISTS qualifier TEXT;

-- Drop the legacy lev_status_cd — the new OGC API doesn't provide this;
-- qualifier supersedes it. (Use IF EXISTS for idempotency.)
ALTER TABLE usgs_groundwater_well_readings
    DROP COLUMN IF EXISTS lev_status_cd;

-- Unique constraint was on (site_no, lev_dt) — readings are still per-visit,
-- so a well can have multiple readings on the same date (different field visits).
-- Relax the unique constraint to (site_no, lev_dt, qualifier) to allow that.
DROP INDEX IF EXISTS idx_gw_readings_unique;
CREATE UNIQUE INDEX IF NOT EXISTS idx_gw_readings_unique
    ON usgs_groundwater_well_readings (site_no, lev_dt, COALESCE(qualifier, ''));
