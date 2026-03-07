import click


VALID_DATASETS = [
    "nasa-power",
    "epa-aqs",
    "usgs-eq",
    "fcc-broadband",
    "census-acs",
    "fema-nfhl",
]


@click.group()
def cache() -> None:
    """Query cache management commands."""


@cache.command()
@click.option(
    "--dataset",
    required=True,
    type=click.Choice(VALID_DATASETS, case_sensitive=False),
    help="Dataset whose cache entries should be cleared.",
)
def clear(dataset: str) -> None:
    """Clear all cache entries for a specific dataset."""
    click.echo(f"Clearing cache for dataset: {dataset}")
    try:
        from plinth.db.connection import get_connection

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM query_cache WHERE dataset = %s",
                    (dataset,),
                )
                deleted = cur.rowcount
            conn.commit()
        click.echo(f"Deleted {deleted} cache entry/entries for '{dataset}'.")
    except Exception as exc:
        click.echo(f"Cache clear failed: {exc}", err=True)
        raise SystemExit(1)
