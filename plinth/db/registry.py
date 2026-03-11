"""Lightweight helper to register API data sources in data_source_registry."""

from __future__ import annotations

import logging
from typing import Any

from plinth.db.connection import get_connection

logger = logging.getLogger(__name__)

_UPSERT_SQL = """
INSERT INTO data_source_registry
    (source_name, dataset_version, last_downloaded,
     update_frequency, coverage_region, notes)
VALUES (%s, %s, now(), %s, %s, %s)
ON CONFLICT (source_name) DO UPDATE SET
    dataset_version  = EXCLUDED.dataset_version,
    last_downloaded  = EXCLUDED.last_downloaded,
    update_frequency = EXCLUDED.update_frequency,
    coverage_region  = EXCLUDED.coverage_region,
    notes            = EXCLUDED.notes
"""


def register_api_source(
    source_name: str,
    *,
    version: str,
    update_frequency: str = "on-demand",
    coverage_region: str = "national",
    notes: str | None = None,
) -> None:
    """Upsert an API data source into data_source_registry."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    _UPSERT_SQL,
                    (source_name, version, update_frequency,
                     coverage_region, notes),
                )
            conn.commit()
    except Exception:
        logger.debug("Could not register API source %s", source_name, exc_info=True)


def get_all_sources() -> list[dict[str, Any]]:
    """Return every row from data_source_registry, ordered by source_name."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT source_name, dataset_version, last_downloaded,
                       update_frequency, coverage_region, notes
                FROM data_source_registry
                ORDER BY source_name
                """
            )
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
