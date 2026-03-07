from contextlib import contextmanager
from typing import Generator

import psycopg

from plinth.config import get_settings


def get_dsn() -> str:
    s = get_settings()
    return (
        f"host={s.postgres_host} "
        f"port={s.postgres_port} "
        f"dbname={s.postgres_db} "
        f"user={s.postgres_user} "
        f"password={s.postgres_password}"
    )


@contextmanager
def get_connection() -> Generator[psycopg.Connection, None, None]:
    """Yield a psycopg connection. Commits on clean exit, rolls back on error."""
    with psycopg.connect(get_dsn()) as conn:
        yield conn


@contextmanager
def get_cursor(autocommit: bool = False) -> Generator[psycopg.Cursor, None, None]:
    """Yield a cursor inside a managed connection."""
    with get_connection() as conn:
        if autocommit:
            conn.autocommit = True
        with conn.cursor() as cur:
            yield cur
        if not autocommit:
            conn.commit()
