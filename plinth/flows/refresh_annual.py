"""Prefect flow: refresh_annual

Annual flow (Jan 1) that re-runs all annually-refreshed data sources and
clears stale query_cache entries for API-backed sources.

Sources refreshed:
  - Census TIGER (block groups, tracts)
  - USDA SSURGO
  - NLCD
  - USGS 3DEP
  - NOAA Normals (decadal, but cheap to re-check)
  - FCC Broadband (semi-annual; this flow covers the Jan refresh)

Schedule: annual, Jan 1 at 03:00 UTC
"""

from prefect import flow, task, get_run_logger


@task(name="annual-census-tiger", retries=1)
def run_census_tiger(region: str) -> None:
    from plinth.ingest.census_tiger import CensusTigerIngestor
    CensusTigerIngestor().run(region)


@task(name="annual-ssurgo", retries=1)
def run_ssurgo(region: str) -> None:
    from plinth.ingest.usda_ssurgo import UsdaSsurgoIngestor
    UsdaSsurgoIngestor().run(region)


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


@task(name="annual-clear-api-cache")
def clear_api_caches() -> dict[str, int]:
    """Purge query_cache for annual-refresh API sources."""
    from plinth.db.connection import get_connection

    annual_datasets = ["census-acs", "epa-aqs"]
    counts: dict[str, int] = {}

    with get_connection() as conn:
        with conn.cursor() as cur:
            for ds in annual_datasets:
                cur.execute("DELETE FROM query_cache WHERE dataset = %s", (ds,))
                counts[ds] = cur.rowcount
        conn.commit()

    return counts


@flow(name="refresh-annual", log_prints=True)
def refresh_annual(region: str = "ne-oklahoma") -> None:
    """Re-run all annually-refreshed ingestors and clear stale API caches."""
    logger = get_run_logger()
    logger.info(f"Starting annual refresh for region: {region}")

    run_census_tiger(region)
    run_ssurgo(region)
    run_nlcd(region)
    run_usgs_3dep(region)
    run_noaa_normals(region)
    run_fcc_broadband(region)
    run_raster_index()

    purged = clear_api_caches()
    logger.info(f"Annual refresh complete. Cache rows purged: {purged}")
