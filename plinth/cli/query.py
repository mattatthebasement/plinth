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
def query_all(lat: float, lon: float, county_fips: str) -> None:
    """Run all Phase 4 API query functions for a coordinate and print JSON summary."""
    from plinth.ingest.api import nasa_power, epa_aqs, usgs_earthquakes, usgs_seismic, usda_whp, fcc_broadband

    results: dict = {}

    click.echo(f"Querying all API sources for ({lat}, {lon})...", err=True)

    for label, fn, kwargs in [
        ("nasa_power",      nasa_power.fetch,       {"lat": lat, "lon": lon}),
        ("epa_aqs",         epa_aqs.fetch,          {"lat": lat, "lon": lon, "county_fips": county_fips}),
        ("usgs_earthquakes",usgs_earthquakes.fetch,  {"lat": lat, "lon": lon}),
        ("usgs_seismic",    usgs_seismic.fetch,     {"lat": lat, "lon": lon}),
        ("usda_whp",        usda_whp.fetch,         {"lat": lat, "lon": lon}),
        ("fcc_broadband",   fcc_broadband.fetch,    {"lat": lat, "lon": lon}),
    ]:
        click.echo(f"  {label}...", err=True)
        try:
            results[label] = fn(**kwargs)
        except Exception as exc:
            results[label] = {"available": False, "error": str(exc)}

    click.echo(json.dumps(results, indent=2))

