import click


@click.group()
def report() -> None:
    """Report generation commands."""


@report.command()
@click.option("--address", required=True, help='US address string, e.g. "11822 E 116th St N, Collinsville, OK".')
def generate(address: str) -> None:
    """Geocode an address, run all queries, and generate a PDF report."""
    click.echo(f"report generate not yet implemented (Phase 7). address='{address}'")
