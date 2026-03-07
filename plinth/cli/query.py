import click


@click.group()
def query() -> None:
    """Spatial query commands."""


@query.command("all")
@click.option("--lat", required=True, type=float, help="Latitude (decimal degrees, WGS84).")
@click.option("--lon", required=True, type=float, help="Longitude (decimal degrees, WGS84).")
def query_all(lat: float, lon: float) -> None:
    """Run all spatial query functions for a coordinate and print JSON summary."""
    click.echo(f"query all not yet implemented (Phase 6). lat={lat} lon={lon}")
