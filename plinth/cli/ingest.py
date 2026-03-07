import click


REGIONS = {
    "ne-oklahoma": {
        "minx": -96.5,
        "miny": 35.5,
        "maxx": -94.5,
        "maxy": 37.0,
    },
}


@click.group()
def ingest() -> None:
    """Data ingestion commands."""


@ingest.command("all")
@click.option("--region", default="ne-oklahoma", show_default=True,
              help="Named region or 'minx,miny,maxx,maxy' bounding box.")
def ingest_all(region: str) -> None:
    """Run all ingestors in dependency order for a region."""
    click.echo(f"Ingesting all datasets for region: {region}")
    _require_ingestor("ingest all")


@ingest.command("fema-nfhl")
@click.option("--region", default="ne-oklahoma", show_default=True)
def ingest_fema_nfhl(region: str) -> None:
    """Ingest FEMA National Flood Hazard Layer."""
    _require_ingestor("fema-nfhl")


@ingest.command("census-tiger")
@click.option("--region", default="ne-oklahoma", show_default=True)
def ingest_census_tiger(region: str) -> None:
    """Ingest Census TIGER/Line block groups and tracts."""
    _require_ingestor("census-tiger")


@ingest.command("iecc")
def ingest_iecc() -> None:
    """Ingest IECC climate zone boundaries."""
    _require_ingestor("iecc")


@ingest.command("fema-nri")
def ingest_fema_nri() -> None:
    """Ingest FEMA National Risk Index (tract-level CSV)."""
    _require_ingestor("fema-nri")


@ingest.command("nhd")
@click.option("--region", default="ne-oklahoma", show_default=True)
def ingest_nhd(region: str) -> None:
    """Ingest NHDPlus High Resolution hydrography."""
    _require_ingestor("nhd")


@ingest.command("ssurgo")
@click.option("--region", default="ne-oklahoma", show_default=True)
def ingest_ssurgo(region: str) -> None:
    """Ingest USDA SSURGO soils data."""
    _require_ingestor("ssurgo")


@ingest.command("usgs-3dep")
@click.option("--region", default="ne-oklahoma", show_default=True)
def ingest_usgs_3dep(region: str) -> None:
    """Ingest USGS 3DEP digital elevation model tiles."""
    _require_ingestor("usgs-3dep")


@ingest.command("nlcd")
@click.option("--region", default="ne-oklahoma", show_default=True)
def ingest_nlcd(region: str) -> None:
    """Ingest NLCD national land cover raster."""
    _require_ingestor("nlcd")


@ingest.command("usgs-seismic")
def ingest_usgs_seismic() -> None:
    """Ingest USGS National Seismic Hazard Maps (PGA raster)."""
    _require_ingestor("usgs-seismic")


@ingest.command("usda-whp")
def ingest_usda_whp() -> None:
    """Ingest USDA Wildfire Hazard Potential raster."""
    _require_ingestor("usda-whp")


@ingest.command("noaa-normals")
def ingest_noaa_normals() -> None:
    """Ingest NOAA 1991-2020 Climate Normals station data."""
    _require_ingestor("noaa-normals")


def _require_ingestor(name: str) -> None:
    """Print a not-yet-implemented notice (placeholder until Phase 2/3)."""
    click.echo(f"  [{name}] ingestor not yet implemented (Phase 2/3).")
