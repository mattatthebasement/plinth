import re
from pathlib import Path

from plinth.db.connection import get_connection

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def run_migrations() -> list[str]:
    """Apply all pending numbered SQL migrations. Returns list of applied versions."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version    TEXT PRIMARY KEY,
                    applied_at TIMESTAMPTZ DEFAULT now()
                )
            """)
        conn.commit()

        migration_files = sorted(
            f for f in MIGRATIONS_DIR.glob("*.sql")
            if re.match(r"^\d+_", f.name)
        )

        applied: list[str] = []
        for mf in migration_files:
            version = mf.stem
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM schema_migrations WHERE version = %s",
                    (version,),
                )
                if cur.fetchone():
                    continue

                cur.execute(mf.read_text())
                cur.execute(
                    "INSERT INTO schema_migrations (version) VALUES (%s)",
                    (version,),
                )
            conn.commit()
            applied.append(version)

    return applied


def get_migration_status() -> list[dict]:
    """Return applied migrations with timestamps."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT version, applied_at FROM schema_migrations ORDER BY version"
            )
            rows = cur.fetchall()
    return [{"version": r[0], "applied_at": r[1]} for r in rows]
