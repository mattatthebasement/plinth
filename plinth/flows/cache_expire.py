"""Prefect flow: cache_expire

Daily flow that purges expired rows from the query_cache table.
Rows are expired when expires_at < now().

Schedule: daily at 01:00 UTC
"""

from prefect import flow, task, get_run_logger


@task(name="purge-expired-cache")
def purge_expired() -> int:
    """Delete expired query_cache rows. Returns count of deleted rows."""
    from plinth.db.connection import get_connection

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM query_cache WHERE expires_at < now()")
            count = cur.rowcount
        conn.commit()

    return count


@task(name="cache-size-report")
def report_cache_size() -> dict[str, int]:
    """Return current row counts per dataset in query_cache."""
    from plinth.db.connection import get_connection

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT dataset, COUNT(*) AS row_count
                FROM query_cache
                GROUP BY dataset
                ORDER BY dataset
                """
            )
            rows = cur.fetchall()

    return {r[0]: r[1] for r in rows}


@flow(name="cache-expire", log_prints=True)
def cache_expire() -> None:
    """Purge expired query_cache rows and log remaining counts per dataset."""
    logger = get_run_logger()

    purged = purge_expired()
    logger.info(f"Purged {purged} expired query_cache row(s).")

    remaining = report_cache_size()
    if remaining:
        logger.info("Remaining query_cache rows by dataset:")
        for dataset, count in remaining.items():
            logger.info(f"  {dataset}: {count}")
    else:
        logger.info("query_cache is empty.")
