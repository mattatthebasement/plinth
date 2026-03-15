-- Migration 013: Expand noaa_climate_normals with all available NCEI monthly fields.
--
-- Adds 93 new NUMERIC[] array columns (12 elements each, index 1=Jan..12=Dec)
-- to capture the full breadth of the NCEI 1991-2020 monthly normals dataset.
--
-- Groups:
--   Temperature std dev & diurnal range
--   Days tmax above thresholds (32–100°F)
--   Days tmax below 32°F
--   Days tmin below thresholds (0–70°F)
--   Probability tmin below thresholds (16–36°F) — frost probability
--   Heating degree days (alternative bases: 40–60°F)
--   Cooling degree days (alternative bases: 40–72°F)
--   Growing degree days (bases 40–72°F + corn/soy TB variants)
--   Precipitation percentiles (20th–80th) and threshold-day counts
--   Snowfall percentiles (20th–80th) and threshold-day counts
--   Snow depth threshold-day counts

-- ── Temperature standard deviations & diurnal range ───────────────────────
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS tavg_stddev  numeric[];
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS tmax_stddev  numeric[];
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS tmin_stddev  numeric[];
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS dutr         numeric[];  -- diurnal temp range (tmax-tmin), °F
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS dutr_stddev  numeric[];

-- ── Days max temp above thresholds ────────────────────────────────────────
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS tmax_days_gt32  numeric[];  -- avg days tmax > 32°F
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS tmax_days_gt40  numeric[];
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS tmax_days_gt50  numeric[];
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS tmax_days_gt60  numeric[];
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS tmax_days_gt70  numeric[];
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS tmax_days_gt80  numeric[];
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS tmax_days_gt90  numeric[];  -- avg days tmax > 90°F
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS tmax_days_gt100 numeric[];
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS tmax_days_lt32  numeric[];  -- avg days tmax < 32°F

-- ── Days min temp below thresholds ────────────────────────────────────────
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS tmin_days_lt0   numeric[];  -- avg days tmin < 0°F
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS tmin_days_lt10  numeric[];
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS tmin_days_lt20  numeric[];
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS tmin_days_lt32  numeric[];  -- avg days tmin < 32°F (frost)
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS tmin_days_lt40  numeric[];
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS tmin_days_lt50  numeric[];
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS tmin_days_lt60  numeric[];
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS tmin_days_lt70  numeric[];

-- ── Frost probability: probability tmin falls below threshold ─────────────
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS tmin_prob_lt16  numeric[];  -- prob tmin < 16°F (hard freeze)
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS tmin_prob_lt20  numeric[];
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS tmin_prob_lt24  numeric[];
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS tmin_prob_lt28  numeric[];
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS tmin_prob_lt32  numeric[];  -- prob frost
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS tmin_prob_lt36  numeric[];

-- ── Heating degree days (alternative bases) ───────────────────────────────
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS htdd_base40  numeric[];
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS htdd_base45  numeric[];
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS htdd_base50  numeric[];
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS htdd_base55  numeric[];
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS htdd_base57  numeric[];
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS htdd_base60  numeric[];
-- htdd (base 65) already exists

-- ── Cooling degree days (alternative bases) ───────────────────────────────
-- cldd (base 65) already exists
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS cldd_base40  numeric[];
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS cldd_base45  numeric[];
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS cldd_base50  numeric[];
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS cldd_base55  numeric[];
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS cldd_base57  numeric[];
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS cldd_base60  numeric[];
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS cldd_base70  numeric[];
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS cldd_base72  numeric[];

-- ── Growing degree days ───────────────────────────────────────────────────
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS grdd_base40   numeric[];
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS grdd_base45   numeric[];
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS grdd_base50   numeric[];
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS grdd_base55   numeric[];
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS grdd_base57   numeric[];
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS grdd_base60   numeric[];
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS grdd_base65   numeric[];
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS grdd_base70   numeric[];
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS grdd_base72   numeric[];
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS grdd_tb4886   numeric[];  -- corn GDD (base 48, cap 86)
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS grdd_tb5086   numeric[];  -- soybean GDD (base 50, cap 86)

-- ── Precipitation percentiles ─────────────────────────────────────────────
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS prcp_20pctl  numeric[];
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS prcp_25pctl  numeric[];
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS prcp_33pctl  numeric[];
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS prcp_40pctl  numeric[];
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS prcp_50pctl  numeric[];  -- median precipitation
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS prcp_60pctl  numeric[];
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS prcp_67pctl  numeric[];
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS prcp_75pctl  numeric[];
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS prcp_80pctl  numeric[];

-- ── Precipitation threshold days ──────────────────────────────────────────
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS prcp_days_ge001  numeric[];  -- avg days precip ≥ 0.01 in
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS prcp_days_ge010  numeric[];  -- avg days precip ≥ 0.10 in
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS prcp_days_ge025  numeric[];  -- avg days precip ≥ 0.25 in
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS prcp_days_ge050  numeric[];  -- avg days precip ≥ 0.50 in
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS prcp_days_ge100  numeric[];  -- avg days precip ≥ 1.00 in
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS prcp_days_ge200  numeric[];  -- avg days precip ≥ 2.00 in
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS prcp_days_ge400  numeric[];  -- avg days precip ≥ 4.00 in
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS prcp_days_ge600  numeric[];  -- avg days precip ≥ 6.00 in

-- ── Snowfall percentiles ──────────────────────────────────────────────────
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS snow_20pctl  numeric[];
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS snow_25pctl  numeric[];
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS snow_33pctl  numeric[];
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS snow_40pctl  numeric[];
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS snow_50pctl  numeric[];  -- median snowfall
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS snow_60pctl  numeric[];
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS snow_67pctl  numeric[];
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS snow_75pctl  numeric[];
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS snow_80pctl  numeric[];

-- ── Snowfall threshold days ───────────────────────────────────────────────
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS snow_days_ge001  numeric[];  -- avg days snowfall ≥ 0.1 in
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS snow_days_ge010  numeric[];  -- avg days snowfall ≥ 1.0 in
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS snow_days_ge020  numeric[];
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS snow_days_ge030  numeric[];
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS snow_days_ge040  numeric[];
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS snow_days_ge050  numeric[];  -- avg days snowfall ≥ 5.0 in
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS snow_days_ge100  numeric[];  -- avg days snowfall ≥ 10.0 in
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS snow_days_ge200  numeric[];

-- ── Snow depth threshold days ─────────────────────────────────────────────
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS snwd_days_ge001  numeric[];  -- avg days snow depth ≥ 1 in
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS snwd_days_ge002  numeric[];
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS snwd_days_ge003  numeric[];
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS snwd_days_ge004  numeric[];
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS snwd_days_ge005  numeric[];
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS snwd_days_ge010  numeric[];  -- avg days snow depth ≥ 10 in
ALTER TABLE noaa_climate_normals ADD COLUMN IF NOT EXISTS snwd_days_ge020  numeric[];  -- avg days snow depth ≥ 20 in
