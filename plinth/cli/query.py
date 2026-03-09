import json
import click


@click.group()
def query() -> None:
    """Spatial query commands."""


@query.command("all")
@click.option("--lat", required=True, type=float, help="Latitude (decimal degrees, WGS84).")
@click.option("--lon", required=True, type=float, help="Longitude (decimal degrees, WGS84).")
@click.option("--county-fips", default="40131", show_default=True,
              help="5-digit county FIPS for EPA AQS lookup.")
@click.option("--radius-mi", default=5.0, show_default=True, type=float,
              help="Hydrography search radius in miles.")
@click.option("--slope-radius-m", default=100.0, show_default=True, type=float,
              help="Slope computation radius in metres.")
@click.option("--lc-radius-m", default=500.0, show_default=True, type=float,
              help="Land cover clip radius in metres.")
def query_all(
    lat: float,
    lon: float,
    county_fips: str,
    radius_mi: float,
    slope_radius_m: float,
    lc_radius_m: float,
) -> None:
    """Run all query functions for a coordinate and print JSON summary."""
    from plinth.query import (
        query_flood_zone,
        query_fema_nri,
        query_iecc_zone,
        query_census_block_groups,
        query_soil,
        query_hydro,
        query_noaa_normals,
        query_elevation,
        query_slope,
        query_land_cover,
        query_seismic_pga,
        query_wildfire_whp,
        query_nasa_power,
        query_epa_aqs,
        query_earthquakes,
        query_fcc_broadband,
    )

    results: dict = {}

    sources = [
        # (label, callable, kwargs)
        ("flood_zone",          query_flood_zone,         {"lat": lat, "lon": lon}),
        ("fema_nri",            query_fema_nri,           {"lat": lat, "lon": lon}),
        ("iecc_zone",           query_iecc_zone,          {"lat": lat, "lon": lon}),
        ("census_block_groups", query_census_block_groups, {"lat": lat, "lon": lon}),
        ("soil",                query_soil,               {"lat": lat, "lon": lon}),
        ("hydro",               query_hydro,              {"lat": lat, "lon": lon, "radius_mi": radius_mi}),
        ("noaa_normals",        query_noaa_normals,       {"lat": lat, "lon": lon}),
        ("elevation",           query_elevation,          {"lat": lat, "lon": lon}),
        ("slope",               query_slope,              {"lat": lat, "lon": lon, "radius_m": slope_radius_m}),
        ("land_cover",          query_land_cover,         {"lat": lat, "lon": lon, "radius_m": lc_radius_m}),
        ("seismic_pga",         query_seismic_pga,        {"lat": lat, "lon": lon}),
        ("wildfire_whp",        query_wildfire_whp,       {"lat": lat, "lon": lon}),
        ("nasa_power",          query_nasa_power,         {"lat": lat, "lon": lon}),
        ("epa_aqs",             query_epa_aqs,            {"lat": lat, "lon": lon, "county_fips": county_fips}),
        ("earthquakes",         query_earthquakes,        {"lat": lat, "lon": lon}),
        ("fcc_broadband",       query_fcc_broadband,      {"lat": lat, "lon": lon}),
    ]

    click.echo(f"Querying all sources for ({lat}, {lon})...", err=True)

    for label, fn, kwargs in sources:
        click.echo(f"  {label}...", err=True)
        try:
            results[label] = fn(**kwargs)
        except Exception as exc:
            results[label] = {"available": False, "error": str(exc)}

    click.echo(json.dumps(results, indent=2))
