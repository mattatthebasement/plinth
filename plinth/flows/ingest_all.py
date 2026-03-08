"""Prefect flow: ingest_all_regional

On-demand flow that runs the full ingestion pipeline for a region.
Intended for initial setup and full rebuilds. Mirrors the behaviour of
``plinth-cli ingest all --region <region>``.

Trigger: manual (Prefect UI or CLI)
"""

from prefect import flow, task, get_run_logger


@task(name="ingest-fema-nfhl", retries=1)
def ingest_fema_nfhl(region: str) -> str:
    from plinth.ingest.fema_nfhl import FemaNfhlIngestor
    FemaNfhlIngestor().run(region)
    return "fema-nfhl"


@task(name="ingest-census-tiger", retries=1)
def ingest_census_tiger(region: str) -> str:
    from plinth.ingest.census_tiger import CensusTigerIngestor
    CensusTigerIngestor().run(region)
    return "census-tiger"


@task(name="ingest-iecc", retries=1)
def ingest_iecc(region: str) -> str:
    from plinth.ingest.iecc import IeccIngestor
    IeccIngestor().run(region)
    return "iecc"


@task(name="ingest-fema-nri", retries=1)
def ingest_fema_nri(region: str) -> str:
    from plinth.ingest.fema_nri import FemaNriIngestor
    FemaNriIngestor().run(region)
    return "fema-nri"


@task(name="ingest-nhd-hr", retries=1)
def ingest_nhd_hr(region: str) -> str:
    from plinth.ingest.nhd import NhdIngestor
    NhdIngestor().run(region)
    return "nhd-hr"


@task(name="ingest-usda-ssurgo", retries=1)
def ingest_usda_ssurgo(region: str) -> str:
    from plinth.ingest.ssurgo import SsurgoIngestor
    SsurgoIngestor().run(region)
    return "usda-ssurgo"


@task(name="ingest-noaa-normals", retries=1)
def ingest_noaa_normals(region: str) -> str:
    from plinth.ingest.noaa_normals import NoaaNormalsIngestor
    NoaaNormalsIngestor().run(region)
    return "noaa-normals"


@task(name="ingest-fcc-broadband", retries=1)
def ingest_fcc_broadband(region: str) -> str:
    from plinth.ingest.fcc_broadband import FccBroadbandIngestor
    FccBroadbandIngestor().run(region)
    return "fcc-broadband"


@task(name="ingest-usgs-3dep", retries=1)
def ingest_usgs_3dep(region: str) -> str:
    from plinth.ingest.usgs_3dep import Usgs3depIngestor
    Usgs3depIngestor().run(region)
    return "usgs-3dep"


@task(name="ingest-nlcd", retries=1)
def ingest_nlcd(region: str) -> str:
    from plinth.ingest.nlcd import NlcdIngestor
    NlcdIngestor().run(region)
    return "nlcd"


@task(name="raster-index", retries=1)
def raster_index() -> str:
    from plinth.raster.index import build_raster_index
    build_raster_index()
    return "raster-index"


@flow(name="ingest-all-regional", log_prints=True)
def ingest_all_regional(region: str = "ne-oklahoma") -> None:
    """Run the full ingestion pipeline for a region.

    Tasks run sequentially to respect inter-ingestor dependencies
    (e.g. census-tiger must complete before fema-nri).
    """
    logger = get_run_logger()
    logger.info(f"Starting full ingestion for region: {region}")

    # Phase 2 vector sources (in dependency order)
    ingest_fema_nfhl(region)
    ingest_census_tiger(region)     # block groups needed by fema-nri and fcc-broadband
    ingest_iecc(region)
    ingest_fema_nri(region)         # depends on census_tracts
    ingest_nhd_hr(region)
    ingest_usda_ssurgo(region)
    ingest_noaa_normals(region)
    ingest_fcc_broadband(region)    # depends on census_block_groups

    # Phase 3 raster sources
    ingest_usgs_3dep(region)
    ingest_nlcd(region)

    # Re-index rasters after upload
    raster_index()

    logger.info(f"Full ingestion complete for region: {region}")
