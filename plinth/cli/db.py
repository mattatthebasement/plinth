import sys

import click

from plinth.db import get_migration_status, run_migrations


@click.group()
def db() -> None:
    """Database management commands."""


@db.command()
def migrate() -> None:
    """Apply all pending SQL migrations."""
    click.echo("Running migrations...")
    try:
        applied = run_migrations()
    except Exception as exc:
        click.echo(f"Migration failed: {exc}", err=True)
        sys.exit(1)

    if applied:
        for version in applied:
            click.echo(f"  ✓ {version}")
        click.echo(f"Applied {len(applied)} migration(s).")
    else:
        click.echo("No pending migrations.")


@db.command()
def status() -> None:
    """Show applied migrations and data_source_registry contents."""
    try:
        migrations = get_migration_status()
    except Exception as exc:
        click.echo(f"Could not connect to database: {exc}", err=True)
        sys.exit(1)

    click.echo("\n── Schema Migrations ──────────────────────────")
    if not migrations:
        click.echo("  (none applied)")
    for row in migrations:
        click.echo(f"  {row['version']}  applied {row['applied_at']}")

    # data_source_registry may not exist yet (before Phase 1 migration)
    try:
        from plinth.db.connection import get_connection

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT source_name, dataset_version, last_downloaded,
                           update_frequency, coverage_region
                    FROM data_source_registry
                    ORDER BY source_name
                    """
                )
                sources = cur.fetchall()

        click.echo("\n── Data Source Registry ───────────────────────")
        if not sources:
            click.echo("  (empty)")
        for row in sources:
            click.echo(
                f"  {row[0]:<30} v={row[1] or 'N/A':<12} "
                f"downloaded={str(row[2])[:10] if row[2] else 'never':<12} "
                f"freq={row[3] or 'N/A':<10} region={row[4] or 'N/A'}"
            )
    except Exception:
        click.echo("\n  (data_source_registry not yet created — run db migrate first)")
