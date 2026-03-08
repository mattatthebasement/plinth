import subprocess
import sys

import click


@click.group()
def flows() -> None:
    """Prefect flow management commands."""


@flows.command("deploy")
def flows_deploy() -> None:
    """Register and serve all Plinth flows with the Prefect server.

    Starts a long-running serve process. Run in the background or as a
    supervised process inside the prefect-worker container.
    """
    from plinth.flows.deploy import main
    main()


@flows.command("run")
@click.argument("flow_name", metavar="FLOW")
@click.option("--region", default="ne-oklahoma", show_default=True,
              help="Region slug (for flows that accept a region argument).")
@click.option("--force", is_flag=True, default=False,
              help="Force re-run even if source is unchanged (refresh-fema-nfhl only).")
def flows_run(flow_name: str, region: str, force: bool) -> None:
    """Manually trigger a flow by name.

    \b
    Available flows:
      ingest-all-regional   Full ingestion pipeline for a region
      refresh-fema-nfhl     FEMA NFHL staleness check + conditional re-ingest
      refresh-annual        Annual re-ingest of all annually-refreshed sources
      check-staleness       Scan data_source_registry for overdue sources
      cache-expire          Purge expired query_cache rows
    """
    flow_map = {
        "ingest-all-regional": _run_ingest_all,
        "refresh-fema-nfhl":   _run_refresh_fema,
        "refresh-annual":      _run_refresh_annual,
        "check-staleness":     _run_check_staleness,
        "cache-expire":        _run_cache_expire,
    }

    if flow_name not in flow_map:
        click.echo(
            f"Unknown flow: '{flow_name}'. "
            f"Choose from: {', '.join(flow_map)}", err=True
        )
        sys.exit(1)

    click.echo(f"Running flow: {flow_name}", err=True)
    flow_map[flow_name](region=region, force=force)


# ── Private dispatch helpers ──────────────────────────────────────────────────

def _run_ingest_all(region: str, **_) -> None:
    from plinth.flows.ingest_all import ingest_all_regional
    ingest_all_regional(region=region)


def _run_refresh_fema(region: str, force: bool, **_) -> None:
    from plinth.flows.refresh_fema import refresh_fema_nfhl
    refresh_fema_nfhl(region=region, force=force)


def _run_refresh_annual(region: str, **_) -> None:
    from plinth.flows.refresh_annual import refresh_annual
    refresh_annual(region=region)


def _run_check_staleness(**_) -> None:
    from plinth.flows.check_staleness import check_staleness
    check_staleness()


def _run_cache_expire(**_) -> None:
    from plinth.flows.cache_expire import cache_expire
    cache_expire()
