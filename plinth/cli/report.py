from __future__ import annotations

import sys
from pathlib import Path

import click

from plinth.report.render import render_report_pdf
from plinth.report.mock_data import MOCK_CONTEXT


def _geocode(address: str) -> tuple[float, float, str, str, str]:
    """
    Geocode an address using Mapbox Geocoding API.

    Returns (lat, lon, formatted_address, city_state_zip, county).
    Raises RuntimeError if geocoding fails.
    """
    import httpx
    from plinth.config import get_settings

    token = get_settings().mapbox_token
    if not token:
        raise RuntimeError(
            "MAPBOX_TOKEN is not configured. Set it in .env to use live geocoding."
        )

    import urllib.parse
    encoded = urllib.parse.quote(address)
    url = (
        f"https://api.mapbox.com/geocoding/v5/mapbox.places/{encoded}.json"
        f"?country=us&types=address&access_token={token}"
    )

    with httpx.Client(timeout=15.0) as client:
        resp = client.get(url)
        resp.raise_for_status()
        data = resp.json()

    features = data.get("features", [])
    if not features:
        raise RuntimeError(f"No geocoding results found for: {address!r}")

    feature = features[0]
    lon, lat = feature["center"]
    place_name = feature.get("place_name", address)

    # Parse context array for city/state/zip and county
    ctx_map: dict[str, str] = {}
    for ctx in feature.get("context", []):
        ctx_id = ctx.get("id", "")
        if ctx_id.startswith("postcode"):
            ctx_map["postcode"] = ctx.get("text", "")
        elif ctx_id.startswith("place"):
            ctx_map["place"] = ctx.get("text", "")
        elif ctx_id.startswith("region"):
            ctx_map["region"] = ctx.get("short_code", ctx.get("text", "")).replace("US-", "")
        elif ctx_id.startswith("district"):
            ctx_map["district"] = ctx.get("text", "")

    city = ctx_map.get("place", "")
    state = ctx_map.get("region", "")
    zip_code = ctx_map.get("postcode", "")
    county = ctx_map.get("district", "")

    city_state_zip = ", ".join(filter(None, [city, f"{state} {zip_code}".strip()]))
    return lat, lon, place_name, city_state_zip, county


@click.group()
def report() -> None:
    """Report generation commands."""


@report.command()
@click.option("--address", required=True, help='US address string, e.g. "11822 E 116th St N, Collinsville, OK".')
@click.option("--output", "-o", default=None, help="Output PDF file path. Default: plinth_report_<id>.pdf")
@click.option("--prepared-for", default="", help="Client name printed on the cover page.")
@click.option("--mock", is_flag=True, default=False, help="Use hardcoded mock data (demo layout). Ignores --address.")
def generate(address: str, output: str | None, prepared_for: str, mock: bool) -> None:
    """Geocode an address, run all queries, and generate a PDF report.

    Pass --mock to generate a skeleton PDF with hardcoded demo data
    (useful for layout validation).
    """
    if mock:
        click.echo("Rendering mock PDF skeleton (demo data — not live)…")
        context = MOCK_CONTEXT
    else:
        # Step 7.11: geocode → build_context → render
        click.echo(f"Geocoding: {address!r}…")
        try:
            lat, lon, formatted_address, city_state_zip, county = _geocode(address)
        except Exception as exc:
            click.echo(f"Geocoding failed: {exc}", err=True)
            sys.exit(1)

        click.echo(f"  → {lat:.5f}°N, {lon:.5f}°W  ({formatted_address})")
        click.echo("Running site queries…")

        from plinth.report.context import build_context
        try:
            context = build_context(
                lat=lat,
                lon=lon,
                address=formatted_address,
                city_state_zip=city_state_zip,
                county=county,
                prepared_for=prepared_for,
            )
        except Exception as exc:
            click.echo(f"Context build failed: {exc}", err=True)
            sys.exit(1)

        click.echo("Rendering PDF…")

    report_id = context.get("report_id", "PLN-DEMO")
    out_path = Path(output) if output else Path(f"plinth_report_{report_id}.pdf")

    try:
        pdf_bytes = render_report_pdf(context)
    except Exception as exc:
        click.echo(f"PDF rendering failed: {exc}", err=True)
        raise SystemExit(1) from exc

    out_path.write_bytes(pdf_bytes)
    click.echo(f"PDF written → {out_path}  ({len(pdf_bytes):,} bytes)")
