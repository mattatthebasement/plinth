-- Migration 010: EIA power plants + HIFLD electric infrastructure
--
-- Adds four tables covering the US electricity system:
--   eia_power_plants            — EIA-860 generating units (points, national)
--   electric_service_territories — HIFLD retail utility service areas (polygons)
--   electric_transmission_lines  — HIFLD high-voltage transmission lines (lines)
--   electric_substations         — HIFLD electric power substations (points)
--
-- Sources:
--   EIA Form 860 — https://www.eia.gov/electricity/data/eia860/
--   HIFLD Open   — https://hifld-geoplatform.opendata.arcgis.com/
-- Refresh: Annual

-- ---------------------------------------------------------------------------
-- EIA-860 Power Plants — one row per EIA plant code (aggregated from generators)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS eia_power_plants (
    plant_id            INTEGER     PRIMARY KEY,    -- EIA Plant Code
    plant_name          TEXT        NOT NULL,
    utility_id          INTEGER,                    -- EIA Utility ID (joins to service territories)
    utility_name        TEXT,
    operator_name       TEXT,
    state               CHAR(2),
    county              TEXT,
    geom                GEOMETRY(POINT, 4326),
    data_year           SMALLINT    NOT NULL,
    capacity_mw_total   NUMERIC,                    -- sum of all generator nameplate MW
    capacity_mw_by_fuel JSONB,                      -- {"NG": 450.0, "SUN": 200.0, ...}
    primary_fuel        TEXT,                       -- fuel of highest-capacity generator
    technology_types    TEXT[],                     -- distinct technology types at plant
    operating_status    TEXT,                       -- OP / RE / SB / CN / etc.
    created_at          TIMESTAMPTZ DEFAULT now(),
    updated_at          TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_eia_plants_geom    ON eia_power_plants USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_eia_plants_fuel    ON eia_power_plants (primary_fuel);
CREATE INDEX IF NOT EXISTS idx_eia_plants_status  ON eia_power_plants (operating_status);
CREATE INDEX IF NOT EXISTS idx_eia_plants_state   ON eia_power_plants (state);

-- ---------------------------------------------------------------------------
-- HIFLD Electric Retail Service Territories — utility polygon boundaries
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS electric_service_territories (
    id            SERIAL      PRIMARY KEY,
    eia_id        TEXT,                       -- EIA utility ID (may be null for some entities)
    utility_name  TEXT        NOT NULL,
    state         CHAR(2),
    naics_code    TEXT,
    entity_type   TEXT,                       -- IOU / COOP / MUN / FED / OTHER
    address       TEXT,
    city          TEXT,
    zip           TEXT,
    phone         TEXT,
    geom          GEOMETRY(MULTIPOLYGON, 4326) NOT NULL,
    source_date   TEXT,
    created_at    TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_service_territories_geom   ON electric_service_territories USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_service_territories_eia_id ON electric_service_territories (eia_id);
CREATE INDEX IF NOT EXISTS idx_service_territories_state  ON electric_service_territories (state);

-- ---------------------------------------------------------------------------
-- HIFLD Electric Transmission Lines — high-voltage line segments (69 kV+)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS electric_transmission_lines (
    id            SERIAL      PRIMARY KEY,
    line_name     TEXT,
    owner         TEXT,
    voltage_kv    INTEGER,
    voltage_class TEXT,                       -- '100-161', '230', '345', '500', '735 And Above', etc.
    status        TEXT,                       -- IN SERVICE / UNDER CONSTRUCTION / etc.
    geom          GEOMETRY(MULTILINESTRING, 4326) NOT NULL,
    source_date   TEXT,
    created_at    TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_transmission_lines_geom    ON electric_transmission_lines USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_transmission_lines_voltage ON electric_transmission_lines (voltage_kv);

-- ---------------------------------------------------------------------------
-- HIFLD Electric Power Substations — substation point locations (69 kV+)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS electric_substations (
    id              SERIAL      PRIMARY KEY,
    substation_name TEXT,
    owner           TEXT,
    substation_type TEXT,                     -- TRANSFORMER / SWITCHING / etc.
    status          TEXT,                     -- IN SERVICE / UNDER CONSTRUCTION / etc.
    max_voltage_kv  INTEGER,
    state           CHAR(2),
    county          TEXT,
    city            TEXT,
    geom            GEOMETRY(POINT, 4326) NOT NULL,
    source_date     TEXT,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_substations_geom    ON electric_substations USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_substations_voltage ON electric_substations (max_voltage_kv);
CREATE INDEX IF NOT EXISTS idx_substations_state   ON electric_substations (state);
