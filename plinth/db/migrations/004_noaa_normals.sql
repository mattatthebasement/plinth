-- NOAA 1991-2020 Climate Normals station data
-- Monthly values stored as NUMERIC[12] arrays (index 1=Jan … 12=Dec)
CREATE TABLE noaa_climate_normals (
    station_id   TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    elevation_m  NUMERIC,
    geom         GEOMETRY(POINT, 4326) NOT NULL,
    tmax         NUMERIC[12],   -- monthly avg daily max temp (°F)
    tmin         NUMERIC[12],   -- monthly avg daily min temp (°F)
    tavg         NUMERIC[12],   -- monthly avg temp (°F)
    prcp         NUMERIC[12],   -- monthly total precipitation (inches)
    snow         NUMERIC[12],   -- monthly total snowfall (inches)
    htdd         NUMERIC[12],   -- monthly heating degree days
    cldd         NUMERIC[12]    -- monthly cooling degree days
);

CREATE INDEX ON noaa_climate_normals USING GIST (geom);
