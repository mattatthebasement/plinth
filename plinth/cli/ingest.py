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
    """Run all Phase 2 ingestors in dependency order for a region."""
    click.echo(f"Ingesting all datasets for region: {region}")

    from plinth.ingest.census_tiger import CensusTigerIngestor
    from plinth.ingest.fema_nfhl import FemaNfhlIngestor
    from plinth.ingest.iecc import IeccIngestor
    from plinth.ingest.fema_nri import FemaNriIngestor
    from plinth.ingest.nhd import NhdIngestor
    from plinth.ingest.ssurgo import SsurgoIngestor

    CensusTigerIngestor().run(region)
    FemaNfhlIngestor().run(region)
    IeccIngestor().run()
    FemaNriIngestor().run()
    NhdIngestor().run(region)
    SsurgoIngestor().run(region)

    click.echo("All Phase 2 ingestors complete.")


@ingest.command("fema-nfhl")
@click.option("--region", default="ne-oklahoma", show_default=True)
def ingest_fema_nfhl(region: str) -> None:
    """Ingest FEMA National Flood Hazard Layer."""
    from plinth.ingest.fema_nfhl import FemaNfhlIngestor

    FemaNfhlIngestor().run(region)


@ingest.command("census-tiger")
@click.option("--region", default="ne-oklahoma", show_default=True)
def ingest_census_tiger(region: str) -> None:
    """Ingest Census TIGER/Line block groups and tracts."""
    from plinth.ingest.census_tiger import CensusTigerIngestor

    CensusTigerIngestor().run(region)


@ingest.command("iecc")
def ingest_iecc() -> None:
    """Ingest IECC climate zone boundaries."""
    from plinth.ingest.iecc import IeccIngestor

    IeccIngestor().run()


@ingest.command("fema-nri")
@click.option("--region", default="ne-oklahoma", show_default=True)
def ingest_fema_nri(region: str) -> None:
    """Ingest FEMA National Risk Index (tract-level, ArcGIS FeatureServer)."""
    from plinth.ingest.fema_nri import FemaNriIngestor

    FemaNriIngestor().run(region)


@ingest.command("nhd")
@click.option("--region", default="ne-oklahoma", show_default=True)
def ingest_nhd(region: str) -> None:
    """Ingest NHDPlus High Resolution hydrography."""
    from plinth.ingest.nhd import NhdIngestor

    NhdIngestor().run(region)


@ingest.command("ssurgo")
@click.option("--region", default="ne-oklahoma", show_default=True)
def ingest_ssurgo(region: str) -> None:
    """Ingest USDA SSURGO soils data."""
    from plinth.ingest.ssurgo import SsurgoIngestor

    SsurgoIngestor().run(region)


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
    from plinth.ingest.noaa_normals import NoaaNormalsIngestor

    NoaaNormalsIngestor().run()


def _require_ingestor(name: str) -> None:
    """Print a not-yet-implemented notice (placeholder until Phase 2/3)."""
    click.echo(f"  [{name}] ingestor not yet implemented (Phase 2/3).")
