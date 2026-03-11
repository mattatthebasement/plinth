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

    from plinth.ingest.fcc_broadband import FccBroadbandIngestor
    from plinth.ingest.noaa_normals import NoaaNormalsIngestor

    CensusTigerIngestor().run(region)
    FemaNfhlIngestor().run(region)
    IeccIngestor().run()
    FemaNriIngestor().run()
    NhdIngestor().run(region)
    SsurgoIngestor().run(region)
    NoaaNormalsIngestor().run()
    FccBroadbandIngestor().run(region)

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
    from plinth.ingest.usgs_3dep import Usgs3depIngestor

    Usgs3depIngestor().run(region)


@ingest.command("nlcd")
@click.option("--region", default="ne-oklahoma", show_default=True)
def ingest_nlcd(region: str) -> None:
    """Ingest NLCD national land cover raster."""
    from plinth.ingest.nlcd import NlcdIngestor

    NlcdIngestor().run(region)


@ingest.command("usgs-seismic")
@click.option("--region", default="ne-oklahoma", show_default=True)
def ingest_usgs_seismic(region: str) -> None:
    """Ingest USGS NEHRP 2020 seismic design values raster.

    Grid-samples the USGS Design Maps API at 0.05° intervals over the
    region bbox and builds a 3-band COG (PGA/Ss/S1 in g) in MinIO.
    """
    from plinth.ingest.usgs_seismic_raster import UsgsSeismicRasterIngestor

    UsgsSeismicRasterIngestor().run(region)


@ingest.command("usda-whp")
@click.option("--region", default="ne-oklahoma", show_default=True)
def ingest_usda_whp(region: str) -> None:
    """Ingest USDA Wildfire Hazard Potential 2023 raster.

    Clips the WHP 2023 continuous index from the USFS ImageServer
    (imagery.geoplatform.gov), converts to COG, and stores in MinIO.
    """
    from plinth.ingest.usda_whp_raster import UsdaWhpRasterIngestor

    UsdaWhpRasterIngestor().run(region)


@ingest.command("noaa-normals")
def ingest_noaa_normals() -> None:
    """Ingest NOAA 1991-2020 Climate Normals station data."""
    from plinth.ingest.noaa_normals import NoaaNormalsIngestor

    NoaaNormalsIngestor().run()


@ingest.command("fcc-broadband")
@click.option("--region", default="ne-oklahoma", show_default=True,
              help="Region slug (e.g. ne-oklahoma) or state FIPS mapping.")
def ingest_fcc_broadband(region: str) -> None:
    """Ingest FCC BDC State/Location Coverage CSVs (Fixed Broadband)."""
    from plinth.ingest.fcc_broadband import FccBroadbandIngestor

    FccBroadbandIngestor().run(region)


@ingest.command("census-acs-bulk")
@click.option("--year", default=2023, show_default=True,
              help="ACS 5-year vintage year (e.g. 2023).")
def ingest_census_acs_bulk(year: int) -> None:
    """Bulk-ingest Census ACS 5-year estimates for all US block groups.

    Downloads pre-built Summary File .dat tables from census.gov (no API key).
    Loads all ~240k block groups nationally into acs_block_group_data.
    """
    from plinth.ingest.census_acs_bulk import CensusAcsBulkIngestor

    CensusAcsBulkIngestor(year=year).run()


@ingest.command("epa-aqs-bulk")
@click.option("--years", default=5, show_default=True, help="Number of years to load (most recent first).")
def ingest_epa_aqs_bulk(years: int) -> None:
    """Bulk-ingest EPA AQS annual summary files (no API key required).

    Downloads annual_conc_by_monitor_YYYY.zip for the last YEARS years
    from aqs.epa.gov and loads all monitor/pollutant records into
    epa_aqs_sites and epa_aqs_annual_summary.
    """
    from plinth.ingest.epa_aqs_bulk import EpaAqsBulkIngestor

    EpaAqsBulkIngestor(years=years).run()


@ingest.command("nasa-power-bulk")
def ingest_nasa_power_bulk() -> None:
    """Bulk-ingest NASA POWER 20-year monthly climatology for NE Oklahoma.

    Makes 15 regional API calls (one per parameter) covering the NE Oklahoma
    bounding box. Responses are cached in staging so subsequent runs are free.
    """
    from plinth.ingest.nasa_power_bulk import NasaPowerBulkIngestor

    NasaPowerBulkIngestor().run()


@ingest.command("usgs-earthquakes-bulk")
@click.option("--min-mag", default=2.0, show_default=True, help="Minimum magnitude threshold.")
def ingest_usgs_earthquakes_bulk(min_mag: float) -> None:
    """Bulk-ingest USGS ComCat earthquake catalog for NE Oklahoma.

    Fetches all M≥MIN_MAG events in the NE Oklahoma bounding box +1° buffer
    via the USGS FDSN event API (single request, ~13k events total).
    Staging file is refreshed daily.
    """
    from plinth.ingest.usgs_earthquakes_bulk import UsgsEarthquakesBulkIngestor

    UsgsEarthquakesBulkIngestor(min_magnitude=min_mag).run()


def _require_ingestor(name: str) -> None:
    """Print a not-yet-implemented notice (placeholder until Phase 2/3)."""
    click.echo(f"  [{name}] ingestor not yet implemented (Phase 2/3).")
