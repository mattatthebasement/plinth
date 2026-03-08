"""Prefect flow: refresh_fema_nfhl

Monthly flow. Checks whether the FEMA NFHL source has changed since the
last download using the Last-Modified header. Re-ingests only if changed.
Clears relevant query_cache entries on successful update.

Schedule: monthly (1st of month, 02:00 UTC)
"""

from prefect import flow, task, get_run_logger


@task(name="fema-check-staleness")
def check_fema_last_modified() -> tuple[bool, str]:
    """Compare FEMA NFHL Last-Modified header against data_source_registry.

    Returns (changed: bool, remote_date: str).
    """
    import subprocess
    from plinth.db.connection import get_connection

    # Use the same region-specific URL as the FEMA ingestor
    url = "https://hazards.fema.gov/nfhlv2/output/County/40131C_20241003.zip"
    result = subprocess.run(
        ["curl", "-s", "-I", "--max-time", "30", url],
        capture_output=True, text=True, timeout=35,
    )
    remote_date = ""
    for line in result.stdout.splitlines():
        if line.lower().startswith("last-modified:"):
            remote_date = line.split(":", 1)[1].strip()
            break

    if not remote_date:
        # Can't determine — assume stale to be safe
        return True, ""

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT notes FROM data_source_registry WHERE source_name = 'fema-nfhl'",
            )
            row = cur.fetchone()

    # The notes field contains the raw download metadata; compare dates
    local_notes = row[0] if row else ""
    changed = remote_date not in (local_notes or "")
    return changed, remote_date


@task(name="fema-reingest", retries=1)
def reingest_fema(region: str) -> None:
    from plinth.ingest.fema_nfhl import FemaNfhlIngestor
    FemaNfhlIngestor().run(region)


@task(name="fema-clear-cache")
def clear_fema_cache() -> int:
    from plinth.db.connection import get_connection
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM query_cache WHERE dataset = 'fema-nfhl'")
            count = cur.rowcount
        conn.commit()
    return count


@flow(name="refresh-fema-nfhl", log_prints=True)
def refresh_fema_nfhl(region: str = "ne-oklahoma", force: bool = False) -> None:
    """Check for FEMA NFHL updates and re-ingest if the source has changed.

    Set force=True to bypass the Last-Modified check and always re-ingest.
    """
    logger = get_run_logger()

    if force:
        logger.info("Force flag set — skipping Last-Modified check")
        changed = True
    else:
        changed, remote_date = check_fema_last_modified()
        if not changed:
            logger.info(f"FEMA NFHL unchanged (Last-Modified: {remote_date}) — skipping")
            return
        logger.info(f"FEMA NFHL has changed (Last-Modified: {remote_date}) — re-ingesting")

    reingest_fema(region)
    purged = clear_fema_cache()
    logger.info(f"Re-ingest complete. Purged {purged} query_cache rows for fema-nfhl.")
