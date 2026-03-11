-- Migration 007: API-to-local bulk storage tables
--
-- Adds six new tables to replace seven runtime API dependencies with
-- locally-ingested data:
--   acs_block_group_data   — Census ACS 5-year estimates (all block groups, national)
--   epa_aqs_sites          — EPA air quality monitoring site registry
--   epa_aqs_annual_summary — EPA annual pollutant summary by site/year/parameter
--   fcc_broadband_availability — FCC BDC broadband availability by location
--   nasa_power_climatology — NASA POWER 20-year monthly climatology by grid cell
--   usgs_earthquake_events — USGS ComCat earthquake catalog (M≥2.0, regional)
--
-- USDA WHP and USGS Seismic rasters are stored as COG tiles in MinIO and
-- registered in the existing raster_tiles table (no new table needed).

-- ---------------------------------------------------------------------------
-- Census ACS 5-Year Estimates — one row per block group per vintage year.
-- All 148 estimate variables plus their margins of error are stored.
-- geoid is the standard 12-digit Census block group GEOID (state+county+tract+bg).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS acs_block_group_data (
    geoid                            CHAR(12)  NOT NULL,
    acs_year                         SMALLINT  NOT NULL,
    -- Population, Sex & Age (B01001, B01002, B01003)
    total_population                 NUMERIC,  total_population_moe                 NUMERIC,
    median_age                       NUMERIC,  median_age_moe                       NUMERIC,
    median_age_male                  NUMERIC,  median_age_male_moe                  NUMERIC,
    median_age_female                NUMERIC,  median_age_female_moe                NUMERIC,
    avg_household_size               NUMERIC,  avg_household_size_moe               NUMERIC,
    male_total                       NUMERIC,  male_total_moe                       NUMERIC,
    female_total                     NUMERIC,  female_total_moe                     NUMERIC,
    -- Male age brackets
    m_under5                         NUMERIC,  m_under5_moe                         NUMERIC,
    m_5_9                            NUMERIC,  m_5_9_moe                            NUMERIC,
    m_10_14                          NUMERIC,  m_10_14_moe                          NUMERIC,
    m_15_17                          NUMERIC,  m_15_17_moe                          NUMERIC,
    m_18_19                          NUMERIC,  m_18_19_moe                          NUMERIC,
    m_20                             NUMERIC,  m_20_moe                             NUMERIC,
    m_21                             NUMERIC,  m_21_moe                             NUMERIC,
    m_22_24                          NUMERIC,  m_22_24_moe                          NUMERIC,
    m_25_29                          NUMERIC,  m_25_29_moe                          NUMERIC,
    m_30_34                          NUMERIC,  m_30_34_moe                          NUMERIC,
    m_35_39                          NUMERIC,  m_35_39_moe                          NUMERIC,
    m_40_44                          NUMERIC,  m_40_44_moe                          NUMERIC,
    m_45_49                          NUMERIC,  m_45_49_moe                          NUMERIC,
    m_50_54                          NUMERIC,  m_50_54_moe                          NUMERIC,
    m_55_59                          NUMERIC,  m_55_59_moe                          NUMERIC,
    m_60_61                          NUMERIC,  m_60_61_moe                          NUMERIC,
    m_62_64                          NUMERIC,  m_62_64_moe                          NUMERIC,
    m_65_66                          NUMERIC,  m_65_66_moe                          NUMERIC,
    m_67_69                          NUMERIC,  m_67_69_moe                          NUMERIC,
    m_70_74                          NUMERIC,  m_70_74_moe                          NUMERIC,
    m_75_79                          NUMERIC,  m_75_79_moe                          NUMERIC,
    m_80_84                          NUMERIC,  m_80_84_moe                          NUMERIC,
    m_85plus                         NUMERIC,  m_85plus_moe                         NUMERIC,
    -- Female age brackets
    f_under5                         NUMERIC,  f_under5_moe                         NUMERIC,
    f_5_9                            NUMERIC,  f_5_9_moe                            NUMERIC,
    f_10_14                          NUMERIC,  f_10_14_moe                          NUMERIC,
    f_15_17                          NUMERIC,  f_15_17_moe                          NUMERIC,
    f_18_19                          NUMERIC,  f_18_19_moe                          NUMERIC,
    f_20                             NUMERIC,  f_20_moe                             NUMERIC,
    f_21                             NUMERIC,  f_21_moe                             NUMERIC,
    f_22_24                          NUMERIC,  f_22_24_moe                          NUMERIC,
    f_25_29                          NUMERIC,  f_25_29_moe                          NUMERIC,
    f_30_34                          NUMERIC,  f_30_34_moe                          NUMERIC,
    f_35_39                          NUMERIC,  f_35_39_moe                          NUMERIC,
    f_40_44                          NUMERIC,  f_40_44_moe                          NUMERIC,
    f_45_49                          NUMERIC,  f_45_49_moe                          NUMERIC,
    f_50_54                          NUMERIC,  f_50_54_moe                          NUMERIC,
    f_55_59                          NUMERIC,  f_55_59_moe                          NUMERIC,
    f_60_61                          NUMERIC,  f_60_61_moe                          NUMERIC,
    f_62_64                          NUMERIC,  f_62_64_moe                          NUMERIC,
    f_65_66                          NUMERIC,  f_65_66_moe                          NUMERIC,
    f_67_69                          NUMERIC,  f_67_69_moe                          NUMERIC,
    f_70_74                          NUMERIC,  f_70_74_moe                          NUMERIC,
    f_75_79                          NUMERIC,  f_75_79_moe                          NUMERIC,
    f_80_84                          NUMERIC,  f_80_84_moe                          NUMERIC,
    f_85plus                         NUMERIC,  f_85plus_moe                         NUMERIC,
    -- Households & Income (B11001, B19013, B19301, C17002, B19057)
    total_households                 NUMERIC,  total_households_moe                 NUMERIC,
    median_hhi                       NUMERIC,  median_hhi_moe                       NUMERIC,
    per_capita_income                NUMERIC,  per_capita_income_moe                NUMERIC,
    poverty_universe                 NUMERIC,  poverty_universe_moe                 NUMERIC,
    poverty_under_050                NUMERIC,  poverty_under_050_moe                NUMERIC,
    poverty_050_099                  NUMERIC,  poverty_050_099_moe                  NUMERIC,
    public_assistance_count          NUMERIC,  public_assistance_count_moe          NUMERIC,
    public_assistance_universe       NUMERIC,  public_assistance_universe_moe       NUMERIC,
    -- Housing Stock (B25001, B25077, B25064, B25002, B25035)
    total_housing_units              NUMERIC,  total_housing_units_moe              NUMERIC,
    median_home_value                NUMERIC,  median_home_value_moe                NUMERIC,
    median_gross_rent                NUMERIC,  median_gross_rent_moe                NUMERIC,
    vacant_units                     NUMERIC,  vacant_units_moe                     NUMERIC,
    total_housing_units_occ          NUMERIC,  total_housing_units_occ_moe          NUMERIC,
    median_year_built                NUMERIC,  median_year_built_moe                NUMERIC,
    -- Tenure (B25003)
    owner_occupied                   NUMERIC,  owner_occupied_moe                   NUMERIC,
    renter_occupied                  NUMERIC,  renter_occupied_moe                  NUMERIC,
    tenure_universe                  NUMERIC,  tenure_universe_moe                  NUMERIC,
    -- Education (B15003)
    edu_universe                     NUMERIC,  edu_universe_moe                     NUMERIC,
    hs_diploma                       NUMERIC,  hs_diploma_moe                       NUMERIC,
    ged                              NUMERIC,  ged_moe                              NUMERIC,
    some_college_lt1                 NUMERIC,  some_college_lt1_moe                 NUMERIC,
    some_college_ge1                 NUMERIC,  some_college_ge1_moe                 NUMERIC,
    associates                       NUMERIC,  associates_moe                       NUMERIC,
    bachelors                        NUMERIC,  bachelors_moe                        NUMERIC,
    masters                          NUMERIC,  masters_moe                          NUMERIC,
    professional                     NUMERIC,  professional_moe                     NUMERIC,
    doctorate                        NUMERIC,  doctorate_moe                        NUMERIC,
    -- Commute & Travel Time (B08303, B08301)
    travel_time_total                NUMERIC,  travel_time_total_moe                NUMERIC,
    travel_time_lt5                  NUMERIC,  travel_time_lt5_moe                  NUMERIC,
    travel_time_5_9                  NUMERIC,  travel_time_5_9_moe                  NUMERIC,
    travel_time_10_14                NUMERIC,  travel_time_10_14_moe                NUMERIC,
    travel_time_15_19                NUMERIC,  travel_time_15_19_moe                NUMERIC,
    travel_time_20_24                NUMERIC,  travel_time_20_24_moe                NUMERIC,
    travel_time_25_29                NUMERIC,  travel_time_25_29_moe                NUMERIC,
    travel_time_30_34                NUMERIC,  travel_time_30_34_moe                NUMERIC,
    travel_time_35_39                NUMERIC,  travel_time_35_39_moe                NUMERIC,
    travel_time_40_44                NUMERIC,  travel_time_40_44_moe                NUMERIC,
    travel_time_45_59                NUMERIC,  travel_time_45_59_moe                NUMERIC,
    travel_time_60_89                NUMERIC,  travel_time_60_89_moe                NUMERIC,
    travel_time_90plus               NUMERIC,  travel_time_90plus_moe               NUMERIC,
    drive_alone                      NUMERIC,  drive_alone_moe                      NUMERIC,
    commute_universe                 NUMERIC,  commute_universe_moe                 NUMERIC,
    work_from_home                   NUMERIC,  work_from_home_moe                   NUMERIC,
    -- Employment (B23025)
    unemployed                       NUMERIC,  unemployed_moe                       NUMERIC,
    labor_force                      NUMERIC,  labor_force_moe                      NUMERIC,
    in_labor_force                   NUMERIC,  in_labor_force_moe                   NUMERIC,
    labor_force_universe             NUMERIC,  labor_force_universe_moe             NUMERIC,
    -- Occupation (C24010)
    occ_total                        NUMERIC,  occ_total_moe                        NUMERIC,
    occ_m_mgmt                       NUMERIC,  occ_m_mgmt_moe                       NUMERIC,
    occ_m_service                    NUMERIC,  occ_m_service_moe                    NUMERIC,
    occ_m_sales                      NUMERIC,  occ_m_sales_moe                      NUMERIC,
    occ_m_natural                    NUMERIC,  occ_m_natural_moe                    NUMERIC,
    occ_m_production                 NUMERIC,  occ_m_production_moe                 NUMERIC,
    occ_f_mgmt                       NUMERIC,  occ_f_mgmt_moe                       NUMERIC,
    occ_f_service                    NUMERIC,  occ_f_service_moe                    NUMERIC,
    occ_f_sales                      NUMERIC,  occ_f_sales_moe                      NUMERIC,
    occ_f_natural                    NUMERIC,  occ_f_natural_moe                    NUMERIC,
    occ_f_production                 NUMERIC,  occ_f_production_moe                 NUMERIC,
    -- Industry (C24030)
    ind_total                        NUMERIC,  ind_total_moe                        NUMERIC,
    ind_m_ag_mining                  NUMERIC,  ind_m_ag_mining_moe                  NUMERIC,
    ind_m_construction               NUMERIC,  ind_m_construction_moe               NUMERIC,
    ind_m_manufacturing              NUMERIC,  ind_m_manufacturing_moe              NUMERIC,
    ind_m_wholesale                  NUMERIC,  ind_m_wholesale_moe                  NUMERIC,
    ind_m_retail                     NUMERIC,  ind_m_retail_moe                     NUMERIC,
    ind_m_transport_util             NUMERIC,  ind_m_transport_util_moe             NUMERIC,
    ind_m_information                NUMERIC,  ind_m_information_moe                NUMERIC,
    ind_m_finance_re                 NUMERIC,  ind_m_finance_re_moe                 NUMERIC,
    ind_m_professional               NUMERIC,  ind_m_professional_moe               NUMERIC,
    ind_m_edu_health                 NUMERIC,  ind_m_edu_health_moe                 NUMERIC,
    ind_m_arts_food                  NUMERIC,  ind_m_arts_food_moe                  NUMERIC,
    ind_m_other_svc                  NUMERIC,  ind_m_other_svc_moe                  NUMERIC,
    ind_m_public_admin               NUMERIC,  ind_m_public_admin_moe               NUMERIC,
    ind_f_ag_mining                  NUMERIC,  ind_f_ag_mining_moe                  NUMERIC,
    ind_f_construction               NUMERIC,  ind_f_construction_moe               NUMERIC,
    ind_f_manufacturing              NUMERIC,  ind_f_manufacturing_moe              NUMERIC,
    ind_f_wholesale                  NUMERIC,  ind_f_wholesale_moe                  NUMERIC,
    ind_f_retail                     NUMERIC,  ind_f_retail_moe                     NUMERIC,
    ind_f_transport_util             NUMERIC,  ind_f_transport_util_moe             NUMERIC,
    ind_f_information                NUMERIC,  ind_f_information_moe                NUMERIC,
    ind_f_finance_re                 NUMERIC,  ind_f_finance_re_moe                 NUMERIC,
    ind_f_professional               NUMERIC,  ind_f_professional_moe               NUMERIC,
    ind_f_edu_health                 NUMERIC,  ind_f_edu_health_moe                 NUMERIC,
    ind_f_arts_food                  NUMERIC,  ind_f_arts_food_moe                  NUMERIC,
    ind_f_other_svc                  NUMERIC,  ind_f_other_svc_moe                  NUMERIC,
    ind_f_public_admin               NUMERIC,  ind_f_public_admin_moe               NUMERIC,
    -- Race & Ethnicity (B03002)
    total_race                       NUMERIC,  total_race_moe                       NUMERIC,
    non_hispanic_white               NUMERIC,  non_hispanic_white_moe               NUMERIC,
    hispanic                         NUMERIC,  hispanic_moe                         NUMERIC,
    black                            NUMERIC,  black_moe                            NUMERIC,
    asian                            NUMERIC,  asian_moe                            NUMERIC,
    -- Language (C16002)
    language_universe                NUMERIC,  language_universe_moe                NUMERIC,
    limited_english_spanish          NUMERIC,  limited_english_spanish_moe          NUMERIC,
    limited_english_other_indo       NUMERIC,  limited_english_other_indo_moe       NUMERIC,
    limited_english_asian            NUMERIC,  limited_english_asian_moe            NUMERIC,
    limited_english_other            NUMERIC,  limited_english_other_moe            NUMERIC,
    PRIMARY KEY (geoid, acs_year)
);

CREATE INDEX IF NOT EXISTS acs_bg_data_geoid_idx
    ON acs_block_group_data (geoid);

-- ---------------------------------------------------------------------------
-- EPA AQS Monitoring Sites — one row per monitoring station.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS epa_aqs_sites (
    site_id          TEXT  PRIMARY KEY,  -- state_code || county_code || site_num (9 chars)
    state_code       TEXT,
    county_code      TEXT,
    site_num         TEXT,
    local_site_name  TEXT,
    address          TEXT,
    city             TEXT,
    county_name      TEXT,
    state_name       TEXT,
    latitude         NUMERIC,
    longitude        NUMERIC,
    geom             GEOMETRY(POINT, 4326)
);

CREATE INDEX IF NOT EXISTS epa_aqs_sites_geom_idx
    ON epa_aqs_sites USING GIST (geom);

-- ---------------------------------------------------------------------------
-- EPA AQS Annual Summary — one row per site × year × parameter × standard.
-- Stores all fields from the EPA pre-built annual summary CSV files.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS epa_aqs_annual_summary (
    id                       BIGSERIAL PRIMARY KEY,
    site_id                  TEXT     NOT NULL REFERENCES epa_aqs_sites (site_id),
    year                     SMALLINT NOT NULL,
    parameter_code           TEXT     NOT NULL,
    parameter_name           TEXT,
    pollutant_standard       TEXT,
    units                    TEXT,
    arithmetic_mean          NUMERIC,
    first_max_value          NUMERIC,
    first_max_hour           INTEGER,
    second_max_value         NUMERIC,
    third_max_value          NUMERIC,
    fourth_max_value         NUMERIC,
    ninety_eighth_pctile     NUMERIC,
    ninety_ninth_pctile      NUMERIC,
    aqi                      INTEGER,
    method_code              TEXT,
    method_name              TEXT,
    observation_count        INTEGER,
    observation_percent      NUMERIC,
    valid_day_count          INTEGER,
    required_day_count       INTEGER,
    exceptional_data_count   INTEGER,
    UNIQUE (site_id, year, parameter_code, pollutant_standard)
);

CREATE INDEX IF NOT EXISTS epa_aqs_summary_site_year_idx
    ON epa_aqs_annual_summary (site_id, year);
CREATE INDEX IF NOT EXISTS epa_aqs_summary_param_idx
    ON epa_aqs_annual_summary (parameter_code, year);

-- ---------------------------------------------------------------------------
-- FCC Broadband Availability — one row per location × provider × technology.
-- Loaded from FCC BDC state availability bulk ZIP files.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fcc_broadband_availability (
    id                        BIGSERIAL PRIMARY KEY,
    location_id               BIGINT   NOT NULL,
    frn                       TEXT,
    provider_id               TEXT,
    brand_name                TEXT,
    technology_code           SMALLINT,
    max_download_speed        INTEGER,   -- Mbps
    max_upload_speed          INTEGER,   -- Mbps
    low_latency               BOOLEAN,
    business_residential_code CHAR(1),
    state_usps                TEXT,
    county_geoid              TEXT,
    block_geoid               TEXT,
    h3_res8_id                TEXT,
    geom                      GEOMETRY(POINT, 4326)
);

CREATE INDEX IF NOT EXISTS fcc_broadband_geom_idx
    ON fcc_broadband_availability USING GIST (geom);
CREATE INDEX IF NOT EXISTS fcc_broadband_location_idx
    ON fcc_broadband_availability (location_id);
CREATE INDEX IF NOT EXISTS fcc_broadband_county_idx
    ON fcc_broadband_availability (county_geoid);
CREATE INDEX IF NOT EXISTS fcc_broadband_block_idx
    ON fcc_broadband_availability (block_geoid);

-- ---------------------------------------------------------------------------
-- NASA POWER Climatology — 20-year monthly climatology by 0.5° × 0.625° grid cell.
-- month 1–12 = monthly climatology; month 0 = annual average.
-- grid_lat / grid_lon identify the SW corner of the POWER grid cell.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS nasa_power_climatology (
    grid_lat              NUMERIC(5,2) NOT NULL,
    grid_lon              NUMERIC(6,2) NOT NULL,
    month                 SMALLINT     NOT NULL,  -- 0=annual, 1–12=monthly
    -- Meteorological (MERRA-2)
    t2m_mean_c            NUMERIC,   -- Air temperature at 2m mean (°C)
    t2m_max_c             NUMERIC,   -- Air temperature at 2m max (°C)
    t2m_min_c             NUMERIC,   -- Air temperature at 2m min (°C)
    t2mdew_c              NUMERIC,   -- Dew point at 2m (°C)
    t2mwet_c              NUMERIC,   -- Wet bulb temperature at 2m (°C)
    rh2m_pct              NUMERIC,   -- Relative humidity at 2m (%)
    prectotcorr_mm_day    NUMERIC,   -- Precipitation corrected (mm/day)
    ws10m_m_s             NUMERIC,   -- Wind speed at 10m (m/s)
    ws50m_m_s             NUMERIC,   -- Wind speed at 50m (m/s)
    -- Solar (CERES SYN1deg)
    allsky_sfc_sw_dwn     NUMERIC,   -- All-sky surface shortwave (kWh/m²/day)
    allsky_kt             NUMERIC,   -- All-sky insolation clearness index
    clrsky_sfc_sw_dwn     NUMERIC,   -- Clear-sky surface shortwave (kWh/m²/day)
    allsky_sfc_lw_dwn     NUMERIC,   -- All-sky surface longwave (kWh/m²/day)
    -- Derived
    hdd18_3               NUMERIC,   -- Heating degree days (base 18.3°C)
    cdd18_3               NUMERIC,   -- Cooling degree days (base 18.3°C)
    PRIMARY KEY (grid_lat, grid_lon, month)
);

-- ---------------------------------------------------------------------------
-- USGS Earthquake Events — M≥2.0 events within the coverage region.
-- Loaded from USGS FDSN ComCat bulk CSV export.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS usgs_earthquake_events (
    event_id       TEXT        PRIMARY KEY,  -- USGS event ID (e.g. "us7000aabc")
    occurred_at    TIMESTAMPTZ NOT NULL,
    magnitude      NUMERIC,
    magnitude_type TEXT,
    depth_km       NUMERIC,
    place          TEXT,
    status         TEXT,    -- "reviewed" | "automatic"
    gap            NUMERIC, -- azimuthal gap (degrees)
    rms            NUMERIC, -- root-mean-square travel-time residual
    nst            INTEGER, -- number of seismic stations used
    url            TEXT,
    geom           GEOMETRY(POINT, 4326)
);

CREATE INDEX IF NOT EXISTS usgs_eq_geom_idx
    ON usgs_earthquake_events USING GIST (geom);
CREATE INDEX IF NOT EXISTS usgs_eq_occurred_idx
    ON usgs_earthquake_events (occurred_at);
CREATE INDEX IF NOT EXISTS usgs_eq_mag_idx
    ON usgs_earthquake_events (magnitude);
