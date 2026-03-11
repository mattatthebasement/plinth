import click

from plinth.cli.db import db
from plinth.cli.ingest import ingest
from plinth.cli.raster import raster
from plinth.cli.cache import cache
from plinth.cli.query import query
from plinth.cli.report import report
from plinth.cli.infra import infra
from plinth.cli.flows import flows
from plinth.cli.verify import verify


@click.group()
def cli() -> None:
    """Plinth site intelligence platform CLI."""


cli.add_command(db)
cli.add_command(ingest)
cli.add_command(raster)
cli.add_command(cache)
cli.add_command(query)
cli.add_command(report)
cli.add_command(infra)
cli.add_command(flows)
cli.add_command(verify)
