"""Prefect flow: check_staleness

Weekly flow that scans data_source_registry for any source whose
next_review_date has passed. Logs a warning for each stale source.

Schedule: weekly, Mondays at 08:00 UTC
"""

from prefect import flow, task, get_run_logger


@task(name="scan-staleness")
def scan_stale_sources() -> list[dict]:
    """Return all sources where next_review_date < today."""
    from plinth.db.connection import get_connection

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    source_name,
                    dataset_version,
                    last_downloaded,
                    next_review_date,
                    coverage_region
                FROM data_source_registry
                WHERE next_review_date < CURRENT_DATE
                ORDER BY next_review_date ASC
                """
            )
            rows = cur.fetchall()

    return [
        {
            "source_name":    r[0],
            "dataset_version": r[1],
            "last_downloaded": str(r[2]) if r[2] else None,
            "next_review_date": str(r[3]) if r[3] else None,
            "coverage_region": r[4],
        }
        for r in rows
    ]


@flow(name="check-staleness", log_prints=True)
def check_staleness() -> None:
    """Log a warning for every data source that has passed its review date."""
    logger = get_run_logger()

    stale = scan_stale_sources()

    if not stale:
        logger.info("All data sources are current — no stale sources found.")
        return

    logger.warning(f"{len(stale)} stale data source(s) found:")
    for s in stale:
        logger.warning(
            f"  STALE: {s['source_name']} "
            f"(version={s['dataset_version']}, "
            f"last_downloaded={s['last_downloaded']}, "
            f"next_review_date={s['next_review_date']}, "
            f"region={s['coverage_region']})"
        )
