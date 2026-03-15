"""Spatial query functions — one per data source."""

from plinth.query.flood_zone import query_flood_zone
from plinth.query.fema_nri import query_fema_nri
from plinth.query.iecc_zone import query_iecc_zone
from plinth.query.census_demographics import query_census_block_groups
from plinth.query.soil import query_soil
from plinth.query.hydro import query_hydro
from plinth.query.noaa_normals import query_noaa_normals
from plinth.query.noaa_nclimgrid import query_noaa_nclimgrid
from plinth.query.elevation import query_elevation
from plinth.query.slope import query_slope
from plinth.query.land_cover import query_land_cover
from plinth.query.seismic_pga import query_seismic_pga
from plinth.query.wildfire_whp import query_wildfire_whp
from plinth.query.nasa_power import query_nasa_power
from plinth.query.epa_aqs import query_epa_aqs
from plinth.query.earthquakes import query_earthquakes
from plinth.query.fcc_broadband import query_fcc_broadband
from plinth.query.electric_infrastructure import query_electric_infrastructure
from plinth.query.water_infrastructure import query_water_infrastructure

__all__ = [
    "query_flood_zone",
    "query_fema_nri",
    "query_iecc_zone",
    "query_census_block_groups",
    "query_soil",
    "query_hydro",
    "query_noaa_normals",
    "query_noaa_nclimgrid",
    "query_elevation",
    "query_slope",
    "query_land_cover",
    "query_seismic_pga",
    "query_wildfire_whp",
    "query_nasa_power",
    "query_epa_aqs",
    "query_earthquakes",
    "query_fcc_broadband",
    "query_electric_infrastructure",
    "query_water_infrastructure",
]
