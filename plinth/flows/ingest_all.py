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


# ── Migration 007: bulk / API-to-local ingestors ──────────────────────────────

@task(name="ingest-census-acs-bulk", retries=1)
def ingest_census_acs_bulk_task(year: int = 2023) -> str:
    from plinth.ingest.census_acs_bulk import CensusAcsBulkIngestor
    CensusAcsBulkIngestor(year=year).run()
    return "census-acs-bulk"


@task(name="ingest-epa-aqs-bulk", retries=1)
def ingest_epa_aqs_bulk_task(years: int = 5) -> str:
    from plinth.ingest.epa_aqs_bulk import EpaAqsBulkIngestor
    EpaAqsBulkIngestor(years=years).run()
    return "epa-aqs-bulk"


@task(name="ingest-nasa-power-bulk", retries=1)
def ingest_nasa_power_bulk_task() -> str:
    from plinth.ingest.nasa_power_bulk import NasaPowerBulkIngestor
    NasaPowerBulkIngestor().run()
    return "nasa-power-bulk"


@task(name="ingest-usgs-earthquakes-bulk", retries=1)
def ingest_usgs_earthquakes_bulk_task() -> str:
    from plinth.ingest.usgs_earthquakes_bulk import UsgsEarthquakesBulkIngestor
    UsgsEarthquakesBulkIngestor().run()
    return "usgs-earthquakes-bulk"


@task(name="ingest-usda-whp-raster", retries=1)
def ingest_usda_whp_raster_task(region: str) -> str:
    from plinth.ingest.usda_whp_raster import UsdaWhpRasterIngestor
    UsdaWhpRasterIngestor().run(region)
    return "usda-whp-raster"


@task(name="ingest-usgs-seismic-raster", retries=1)
def ingest_usgs_seismic_raster_task(region: str) -> str:
    from plinth.ingest.usgs_seismic_raster import UsgsSeismicRasterIngestor
    UsgsSeismicRasterIngestor().run(region)
    return "usgs-seismic-raster"


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

    # Re-index rasters after Phase 3 uploads
    raster_index()

    # Migration 007: bulk / API-to-local ingestors (no inter-dependencies with Phase 2/3)
    ingest_census_acs_bulk_task()
    ingest_epa_aqs_bulk_task()
    ingest_nasa_power_bulk_task()
    ingest_usgs_earthquakes_bulk_task()
    ingest_usda_whp_raster_task(region)
    ingest_usgs_seismic_raster_task(region)   # slow: ~60 min per region

    # Re-index rasters again after WHP + seismic uploads
    raster_index()

    logger.info(f"Full ingestion complete for region: {region}")
