-- Migration 016: replace lev_meth_cd with parameter_code in usgs_groundwater_well_readings
--
-- lev_meth_cd was a single NWIS legacy character code (S, V, A, etc.).
-- parameter_code is the USGS OGC API parameter identifier (72019, 62610, etc.)
-- and is more meaningful and directly queryable.

ALTER TABLE usgs_groundwater_well_readings
    DROP COLUMN IF EXISTS lev_meth_cd,
    ADD COLUMN parameter_code TEXT;

COMMENT ON COLUMN usgs_groundwater_well_readings.parameter_code IS
    'USGS OGC API parameter code: 72019=standard DTW, 62610=calib electric tape, 62611=analog recorder, 72150=alt electric tape';
