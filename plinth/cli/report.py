from __future__ import annotations

import sys
from pathlib import Path

import click

from plinth.report.render import render_report_pdf
from plinth.report.mock_data import MOCK_CONTEXT


@click.group()
def report() -> None:
    """Report generation commands."""


@report.command()
@click.option("--address", required=True, help='US address string, e.g. "11822 E 116th St N, Collinsville, OK".')
@click.option("--output", "-o", default=None, help="Output PDF file path. Default: plinth_report_<id>.pdf")
@click.option("--mock", is_flag=True, default=False, help="Use hardcoded mock data (Phase 7.1 skeleton). Ignores --address.")
def generate(address: str, output: str | None, mock: bool) -> None:
    """Geocode an address, run all queries, and generate a PDF report.

    Pass --mock to generate a skeleton PDF with hardcoded demo data
    (useful for layout validation before live data wiring).
    """
    if mock:
        click.echo("Rendering mock PDF skeleton (demo data — not live)…")
        context = MOCK_CONTEXT
    else:
        click.echo(f"Live report generation not yet implemented (Phase 7.2+). address='{address}'", err=True)
        click.echo("Use --mock to generate a demo PDF with hardcoded data.", err=True)
        sys.exit(1)

    report_id = context.get("report_id", "PLN-DEMO")
    out_path = Path(output) if output else Path(f"plinth_report_{report_id}.pdf")

    try:
        pdf_bytes = render_report_pdf(context)
    except Exception as exc:
        click.echo(f"PDF rendering failed: {exc}", err=True)
        raise SystemExit(1) from exc

    out_path.write_bytes(pdf_bytes)
    click.echo(f"PDF written → {out_path}  ({len(pdf_bytes):,} bytes)")
