import click


@click.group()
def raster() -> None:
    """Raster tile management commands."""


@raster.command()
def index() -> None:
    """Rebuild the raster_tiles PostGIS index from MinIO bucket listing."""
    click.echo("raster index not yet implemented (Phase 3).")
