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
    """Run all query functions for a coordinate and print JSON summary."""
    from plinth.ingest.api import nasa_power, epa_aqs, usgs_earthquakes, usgs_seismic, usda_whp
    from plinth.ingest.api import fcc_broadband as fcc_api
    from plinth.db.connection import get_connection

    results: dict = {}

    click.echo(f"Querying all sources for ({lat}, {lon})...", err=True)

    for label, fn, kwargs in [
        ("nasa_power",       nasa_power.fetch,        {"lat": lat, "lon": lon}),
        ("epa_aqs",          epa_aqs.fetch,           {"lat": lat, "lon": lon, "county_fips": county_fips}),
        ("usgs_earthquakes", usgs_earthquakes.fetch,  {"lat": lat, "lon": lon}),
        ("usgs_seismic",     usgs_seismic.fetch,      {"lat": lat, "lon": lon}),
        ("usda_whp",         usda_whp.fetch,          {"lat": lat, "lon": lon}),
    ]:
        click.echo(f"  {label}...", err=True)
        try:
            results[label] = fn(**kwargs)
        except Exception as exc:
            results[label] = {"available": False, "error": str(exc)}

    # FCC broadband: prefer PostGIS query if table is populated, else API client
    click.echo("  fcc_broadband...", err=True)
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM fcc_broadband_coverage LIMIT 1")
                count = cur.fetchone()[0]

        if count > 0:
            from plinth.query.fcc_broadband import query_fcc_broadband
            results["fcc_broadband"] = query_fcc_broadband(lat, lon)
        else:
            results["fcc_broadband"] = fcc_api.fetch(lat, lon)
    except Exception as exc:
        results["fcc_broadband"] = {"available": False, "error": str(exc)}

    click.echo(json.dumps(results, indent=2))


