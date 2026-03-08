import click


@click.group()
def raster() -> None:
    """Raster tile management commands."""


@raster.command()
def index() -> None:
    """Rebuild the raster_tiles PostGIS index from MinIO bucket listing.

    Walks every .tif object in the MinIO rasters bucket, downloads each COG
    to a temp file to read bounds/resolution via rasterio, then upserts a
    row in raster_tiles.  Stale rows for missing objects are removed.
    """
    from plinth.raster.index import build_raster_index

    click.echo("Listing objects in MinIO rasters bucket…")
    count = build_raster_index()
    click.echo(f"raster_tiles updated: {count} tile(s) indexed.")

