-- 002_phase2_vectors.sql
-- Phase 2: Vector data ingestion tables.
-- Applied once by: plinth-cli db migrate

-- ── Census TIGER ─────────────────────────────────────────────────────────────

-- Block-group geometries for radius-buffer demographic queries.
-- ACS values are fetched at query time via the Census API — not bulk-loaded here.
CREATE TABLE IF NOT EXISTS census_block_groups (
    geoid    TEXT PRIMARY KEY,
    statefp  TEXT NOT NULL,
    countyfp TEXT NOT NULL,
    tractce  TEXT NOT NULL,
    blkgrpce TEXT NOT NULL,
    aland    BIGINT,
    awater   BIGINT,
    geom     GEOMETRY(MultiPolygon, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS census_block_groups_geom_idx   ON census_block_groups USING GIST (geom);
CREATE INDEX IF NOT EXISTS census_block_groups_county_idx ON census_block_groups (statefp, countyfp);

-- Census tract geometries.  ACS values fetched at query time via Census API.
CREATE TABLE IF NOT EXISTS census_tracts (
    geoid    TEXT PRIMARY KEY,
    statefp  TEXT NOT NULL,
    countyfp TEXT NOT NULL,
    tractce  TEXT NOT NULL,
    aland    BIGINT,
    awater   BIGINT,
    geom     GEOMETRY(MultiPolygon, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS census_tracts_geom_idx   ON census_tracts USING GIST (geom);
CREATE INDEX IF NOT EXISTS census_tracts_county_idx ON census_tracts (statefp, countyfp);

-- ── FEMA NFHL ────────────────────────────────────────────────────────────────

-- Flood hazard area polygons from FEMA National Flood Hazard Layer.
CREATE TABLE IF NOT EXISTS fema_flood_zones (
    gid         SERIAL PRIMARY KEY,
    dfirm_id    TEXT,
    fld_zone    TEXT,
    zone_subty  TEXT,
    sfha_tf     TEXT,
    bfe_revert  NUMERIC,
    static_bfe  NUMERIC,
    county_fips TEXT,
    source_date DATE,
    geom        GEOMETRY(MultiPolygon, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS fema_flood_zones_geom_idx   ON fema_flood_zones USING GIST (geom);
CREATE INDEX IF NOT EXISTS fema_flood_zones_zone_idx   ON fema_flood_zones (fld_zone);
CREATE INDEX IF NOT EXISTS fema_flood_zones_county_idx ON fema_flood_zones (county_fips);

-- County boundary minus all flood-zone polygons.
-- CRITICAL: a site with no FEMA data must NEVER silently appear as Zone X.
-- ~15-20% of the US has no FEMA flood mapping; this table tracks those gaps.
CREATE TABLE IF NOT EXISTS fema_unmapped_areas (
    county_fips TEXT PRIMARY KEY,
    geom        GEOMETRY(MultiPolygon, 4326)
);
CREATE INDEX IF NOT EXISTS fema_unmapped_areas_geom_idx ON fema_unmapped_areas USING GIST (geom);

-- ── IECC Climate Zones ───────────────────────────────────────────────────────

-- DOE/PNNL IECC 2021 climate zone boundaries (national coverage).
-- Polygons for the same zone label are unioned into a single MultiPolygon.
CREATE TABLE IF NOT EXISTS iecc_climate_zones (
    zone_label       TEXT PRIMARY KEY,
    zone_description TEXT,
    geom             GEOMETRY(MultiPolygon, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS iecc_climate_zones_geom_idx ON iecc_climate_zones USING GIST (geom);

-- ── FEMA National Risk Index ──────────────────────────────────────────────────

-- Tract-level composite risk scores from FEMA NRI.
-- IMPORTANT: ALL report output using this table MUST be labeled
--            "Source: FEMA National Risk Index" — it is FEMA's composite model.
CREATE TABLE IF NOT EXISTS fema_nri (
    tract_id    TEXT PRIMARY KEY,
    county_fips TEXT,
    risk_score  NUMERIC,
    risk_ratng  TEXT,
    avln_score  NUMERIC,
    cfld_score  NUMERIC,
    cwav_score  NUMERIC,
    drgt_score  NUMERIC,
    erqk_score  NUMERIC,
    hail_score  NUMERIC,
    hwav_score  NUMERIC,
    hrcn_score  NUMERIC,
    istm_score  NUMERIC,
    lnds_score  NUMERIC,
    ltng_score  NUMERIC,
    rfld_score  NUMERIC,
    swnd_score  NUMERIC,
    trnd_score  NUMERIC,
    tsun_score  NUMERIC,
    vlcn_score  NUMERIC,
    wfir_score  NUMERIC,
    wntw_score  NUMERIC,
    geom        GEOMETRY(MultiPolygon, 4326)
);
CREATE INDEX IF NOT EXISTS fema_nri_geom_idx ON fema_nri USING GIST (geom) WHERE geom IS NOT NULL;

-- ── NHDPlus HR ───────────────────────────────────────────────────────────────

-- NHDPlus High Resolution flowlines (VPU 11, Arkansas-White-Red).
CREATE TABLE IF NOT EXISTS nhd_flowlines (
    permanent_identifier TEXT PRIMARY KEY,
    gnis_name            TEXT,
    lengthkm             NUMERIC,
    ftype                INTEGER,
    fcode                INTEGER,
    geom                 GEOMETRY(MultiLineString, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS nhd_flowlines_geom_idx ON nhd_flowlines USING GIST (geom);

-- NHDPlus High Resolution waterbodies.
CREATE TABLE IF NOT EXISTS nhd_waterbodies (
    permanent_identifier TEXT PRIMARY KEY,
    gnis_name            TEXT,
    areasqkm             NUMERIC,
    ftype                INTEGER,
    fcode                INTEGER,
    geom                 GEOMETRY(MultiPolygon, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS nhd_waterbodies_geom_idx ON nhd_waterbodies USING GIST (geom);

-- ── USDA SSURGO ──────────────────────────────────────────────────────────────

-- Map unit polygons from USDA SSURGO soil survey.
CREATE TABLE IF NOT EXISTS ssurgo_mapunits (
    mukey  TEXT PRIMARY KEY,
    musym  TEXT,
    muname TEXT,
    geom   GEOMETRY(MultiPolygon, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS ssurgo_mapunits_geom_idx ON ssurgo_mapunits USING GIST (geom);

-- Map unit aggregated attributes (tabular — no geometry).
CREATE TABLE IF NOT EXISTS ssurgo_muaggatt (
    mukey        TEXT PRIMARY KEY,
    hydgrpdcd    TEXT,
    drclassdcd   TEXT,
    slopegraddcp NUMERIC,
    taxclname    TEXT
);

-- Component-level data (tabular — no geometry).
CREATE TABLE IF NOT EXISTS ssurgo_component (
    cokey       TEXT PRIMARY KEY,
    mukey       TEXT NOT NULL,
    compname    TEXT,
    comppct_r   NUMERIC,
    majcompflag TEXT
);
CREATE INDEX IF NOT EXISTS ssurgo_component_mukey_idx ON ssurgo_component (mukey);
