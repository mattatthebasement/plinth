"""Prefect deployment registration for all Plinth flows.

Run this module directly inside the worker container to register all flows
with the Prefect server and start serving them:

    uv run python -m plinth.flows.deploy

Or via CLI:

    plinth-cli flows deploy

Schedules (all UTC):
  - cache-expire:       daily    01:00
  - check-staleness:    weekly   Mon 08:00
  - refresh-fema-nfhl:  monthly  1st 02:00
  - refresh-annual:     annual   Jan 1 03:00
  - ingest-all-regional: on-demand only (no schedule)
"""

from prefect import serve
from prefect.schedules import Cron

from plinth.flows.cache_expire import cache_expire
from plinth.flows.check_staleness import check_staleness
from plinth.flows.refresh_fema import refresh_fema_nfhl
from plinth.flows.refresh_annual import refresh_annual
from plinth.flows.ingest_all import ingest_all_regional


def build_deployments():
    """Build deployment objects for all Plinth flows."""
    return [
        cache_expire.to_deployment(
            name="cache-expire",
            schedules=[Cron("0 1 * * *")],
        ),
        check_staleness.to_deployment(
            name="check-staleness",
            schedules=[Cron("0 8 * * 1")],   # Monday 08:00
        ),
        refresh_fema_nfhl.to_deployment(
            name="refresh-fema-nfhl",
            schedules=[Cron("0 2 1 * *")],   # 1st of month 02:00
        ),
        refresh_annual.to_deployment(
            name="refresh-annual",
            schedules=[Cron("0 3 1 1 *")],   # Jan 1 03:00
        ),
        ingest_all_regional.to_deployment(
            name="ingest-all-regional",
            # No schedule — triggered manually
        ),
    ]


def main() -> None:
    deployments = build_deployments()
    print(f"Serving {len(deployments)} Plinth flow(s)...")
    serve(*deployments)


if __name__ == "__main__":
    main()
