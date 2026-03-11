"""Prefect flow: refresh_annual

Annual flow (Jan 1) that re-runs all annually-refreshed data sources.
Sources backed by local bulk tables are re-ingested directly.
Sources still API-backed (NASA POWER cached 30d, FCC blocked) are noted.

Sources refreshed:
  - Census TIGER (block groups, tracts)
  - Census ACS bulk (national, ~242k block groups)
  - EPA AQS bulk (national, last 5 years)
  - USGS earthquake catalog bulk (regional)
  - USDA SSURGO
  - NLCD
  - USGS 3DEP
  - NOAA Normals (decadal, but cheap to re-check)
  - FCC Broadband (semi-annual; this flow covers the Jan refresh — currently blocked)

Schedule: annual, Jan 1 at 03:00 UTC
"""

from prefect import flow, task, get_run_logger


@task(name="annual-census-tiger", retries=1)
def run_census_tiger(region: str) -> None:
    from plinth.ingest.census_tiger import CensusTigerIngestor
    CensusTigerIngestor().run(region)


@task(name="annual-census-acs-bulk", retries=1)
def run_census_acs_bulk(year: int = 2023) -> None:
    """Refresh national Census ACS 5-year estimates (no API key required)."""
    from plinth.ingest.census_acs_bulk import CensusAcsBulkIngestor
    CensusAcsBulkIngestor(year=year).run()


@task(name="annual-epa-aqs-bulk", retries=1)
def run_epa_aqs_bulk(years: int = 5) -> None:
    """Refresh EPA AQS annual summary files (last N years)."""
    from plinth.ingest.epa_aqs_bulk import EpaAqsBulkIngestor
    EpaAqsBulkIngestor(years=years).run()


@task(name="annual-usgs-earthquakes-bulk", retries=1)
def run_usgs_earthquakes_bulk() -> None:
    """Refresh USGS earthquake catalog (idempotent — new events upserted)."""
    from plinth.ingest.usgs_earthquakes_bulk import UsgsEarthquakesBulkIngestor
    UsgsEarthquakesBulkIngestor().run()


@task(name="annual-ssurgo", retries=1)
def run_ssurgo(region: str) -> None:
    from plinth.ingest.ssurgo import SsurgoIngestor
    SsurgoIngestor().run(region)


@task(name="annual-nlcd", retries=1)
def run_nlcd(region: str) -> None:
    from plinth.ingest.nlcd import NlcdIngestor
    NlcdIngestor().run(region)


@task(name="annual-usgs-3dep", retries=1)
def run_usgs_3dep(region: str) -> None:
    from plinth.ingest.usgs_3dep import Usgs3depIngestor
    Usgs3depIngestor().run(region)


@task(name="annual-noaa-normals", retries=1)
def run_noaa_normals(region: str) -> None:
    from plinth.ingest.noaa_normals import NoaaNormalsIngestor
    NoaaNormalsIngestor().run(region)


@task(name="annual-fcc-broadband", retries=1)
def run_fcc_broadband(region: str) -> None:
    from plinth.ingest.fcc_broadband import FccBroadbandIngestor
    FccBroadbandIngestor().run(region)


@task(name="annual-raster-index", retries=1)
def run_raster_index() -> None:
    from plinth.raster.index import build_raster_index
    build_raster_index()


@flow(name="refresh-annual", log_prints=True)
def refresh_annual(region: str = "ne-oklahoma", acs_year: int = 2023) -> None:
    """Re-run all annually-refreshed ingestors.

    Census ACS and EPA AQS are now bulk-loaded from local files — no API cache
    clearing needed for those. NASA POWER climatology is a 20-year baseline and
    is not refreshed annually (re-run ingest-nasa-power-bulk manually on new vintage).
    """
    logger = get_run_logger()
    logger.info(f"Starting annual refresh for region: {region}")

    # Vector sources
    run_census_tiger(region)
    run_ssurgo(region)
    run_nlcd(region)
    run_usgs_3dep(region)
    run_noaa_normals(region)
    run_fcc_broadband(region)
    run_raster_index()

    # Bulk / API-to-local sources (new in migration 007)
    run_census_acs_bulk(acs_year)
    run_epa_aqs_bulk()
    run_usgs_earthquakes_bulk()

    logger.info(f"Annual refresh complete for region: {region}")
