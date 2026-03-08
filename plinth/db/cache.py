"""query_cache read/write helpers with TTL enforcement."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from plinth.db.connection import get_connection


def get_cached(cache_key: str) -> dict[str, Any] | None:
    """Return cached result if present and not expired, else None."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT result_json FROM query_cache
                WHERE cache_key = %s
                  AND (expires_at IS NULL OR expires_at > now())
                """,
                (cache_key,),
            )
            row = cur.fetchone()
    if row is None:
        return None
    result = row[0]
    return result if isinstance(result, dict) else json.loads(result)


def set_cached(
    cache_key: str,
    dataset: str,
    result: dict[str, Any],
    ttl_days: int,
    lat: float | None = None,
    lon: float | None = None,
) -> None:
    """Upsert a cache entry with an expiry timestamp."""
    expires_at = datetime.now(tz=timezone.utc) + timedelta(days=ttl_days)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO query_cache
                    (cache_key, dataset, input_lat, input_lon, result_json, expires_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (cache_key) DO UPDATE SET
                    result_json = EXCLUDED.result_json,
                    cached_at   = now(),
                    expires_at  = EXCLUDED.expires_at
                """,
                (cache_key, dataset, lat, lon, json.dumps(result), expires_at),
            )
        conn.commit()


def clear_dataset(dataset: str) -> int:
    """Delete all cache entries for a dataset. Returns rows deleted."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM query_cache WHERE dataset = %s",
                (dataset,),
            )
            deleted = cur.rowcount
        conn.commit()
    return deleted


def purge_expired() -> int:
    """Delete all expired cache entries. Returns rows deleted."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM query_cache WHERE expires_at IS NOT NULL AND expires_at <= now()"
            )
            deleted = cur.rowcount
        conn.commit()
    return deleted
