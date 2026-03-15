-- Migration 017: USGS Hydrogeologic Framework (2025)
--
-- Adds two tables from the USGS 2025 national hydrogeologic framework data releases:
--   usgs_hydrogeologic_provinces  — 8 broad provinces covering all of CONUS
--   usgs_hydrogeologic_regions    — 126 named regions (57 principal aquifer + 69 secondary)
--
-- Together these provide full CONUS coverage with no unmapped gaps, unlike the
-- existing usgs_principal_aquifers which only covers named major formations.
--
-- Sources:
--   Provinces: https://www.sciencebase.gov/catalog/item/6807cab6d4be020d8168d576 (2025-07-28)
--   Regions:   https://www.sciencebase.gov/catalog/item/6863356fd4be025653d31f4d (2025-12-19)

CREATE TABLE IF NOT EXISTS usgs_hydrogeologic_provinces (
    id          SERIAL PRIMARY KEY,
    prov_name   TEXT NOT NULL,           -- e.g. "Coastal Plain", "Central Interior"
    geom        GEOMETRY(MULTIPOLYGON, 4326) NOT NULL,
    source_year SMALLINT DEFAULT 2025,
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_hydro_provinces_geom
    ON usgs_hydrogeologic_provinces USING GIST (geom);

CREATE TABLE IF NOT EXISTS usgs_hydrogeologic_regions (
    id          SERIAL PRIMARY KEY,
    reg_name    TEXT NOT NULL,           -- e.g. "High Plains aquifer", "Nebraska Sand Hills"
    reg_code    TEXT,                    -- USGS national aquifer code, e.g. "N100HGHPLN"
    reg_type    TEXT,                    -- "PA" = Principal Aquifer, "SHR" = Secondary Region
    lithology   TEXT,                    -- e.g. "Unconsolidated sand and gravel aquifers"
    geom        GEOMETRY(MULTIPOLYGON, 4326) NOT NULL,
    source_year SMALLINT DEFAULT 2025,
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_hydro_regions_geom
    ON usgs_hydrogeologic_regions USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_hydro_regions_type
    ON usgs_hydrogeologic_regions (reg_type);
