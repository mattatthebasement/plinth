from __future__ import annotations

import string
import sys
import urllib.parse
from pathlib import Path

import click
import httpx

from plinth.report.render import render_report_pdf
from plinth.report.mock_data import MOCK_CONTEXT


def _title_case(s: str) -> str:
    """Title-case a string, preserving common abbreviations like 'OK', 'NE', 'NW'."""
    return string.capwords(s)


def _geocode_census(address: str) -> tuple[float, float, str, str, str] | None:
    """
    Geocode via US Census Bureau Geocoder (no API key required).

    Uses the /geographies endpoint to get county name in one call.
    Returns (lat, lon, street_address, city_state_zip, county) or None on failure.
    """
    encoded = urllib.parse.quote(address)
    url = (
        "https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress"
        f"?address={encoded}&benchmark=Public_AR_Current&vintage=Current_Current&format=json"
    )
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(url)
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        return None

    matches = data.get("result", {}).get("addressMatches", [])
    if not matches:
        return None

    match = matches[0]
    coords = match["coordinates"]
    lat, lon = float(coords["y"]), float(coords["x"])

    # matched address is ALL CAPS, e.g. "11822 E 116TH ST N, COLLINSVILLE, OK, 74021"
    matched = _title_case(match.get("matchedAddress", address))

    # Split: "11822 E 116th St N, Collinsville, Ok, 74021"
    # Census format: STREET, CITY, STATE, ZIP  (4 comma-separated parts)
    parts = [p.strip() for p in matched.split(",")]
    street = parts[0] if parts else matched

    if len(parts) >= 4:
        city = parts[1].strip()
        state = parts[2].strip().upper()  # restore state to uppercase abbreviation
        zip_code = parts[3].strip()
        city_state_zip = f"{city}, {state} {zip_code}"
    elif len(parts) == 3:
        city_state_zip = f"{parts[1].strip()}, {parts[2].strip().upper()}"
    else:
        city_state_zip = ""

    # County name from geographies response
    geos = match.get("geographies", {})
    counties = geos.get("Counties", [])
    county = _title_case(counties[0].get("NAME", "")) if counties else ""

    return lat, lon, street, city_state_zip, county


def _geocode_mapbox(address: str) -> tuple[float, float, str, str, str] | None:
    """
    Geocode via Mapbox Geocoding API (fallback). Requires MAPBOX_TOKEN.

    Returns (lat, lon, street_address, city_state_zip, county) or None on failure.
    """
    from plinth.config import get_settings
    token = get_settings().mapbox_token
    if not token:
        return None

    encoded = urllib.parse.quote(address)
    url = (
        f"https://api.mapbox.com/geocoding/v5/mapbox.places/{encoded}.json"
        f"?country=us&types=address&access_token={token}"
    )
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(url)
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        return None

    features = data.get("features", [])
    if not features:
        return None

    feature = features[0]
    lon, lat = feature["center"]

    # Parse context array for city/state/zip/county
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

    # Street address only (first part of place_name before the city)
    place_name = feature.get("place_name", "")
    street = place_name.split(",")[0].strip() if "," in place_name else place_name

    city = ctx_map.get("place", "")
    state = ctx_map.get("region", "")
    zip_code = ctx_map.get("postcode", "")
    county = ctx_map.get("district", "")
    city_state_zip = ", ".join(filter(None, [city, f"{state} {zip_code}".strip()]))

    return lat, lon, street, city_state_zip, county


def _geocode(address: str) -> tuple[float, float, str, str, str]:
    """
    Geocode an address. Tries US Census Geocoder first (no API key, accurate for US),
    then falls back to Mapbox.

    Returns (lat, lon, street_address, city_state_zip, county).
    Raises RuntimeError if all methods fail.
    """
    result = _geocode_census(address)
    if result:
        return result

    click.echo("  Census geocoder unavailable — trying Mapbox fallback…", err=True)
    result = _geocode_mapbox(address)
    if result:
        return result

    raise RuntimeError(
        f"Could not geocode address: {address!r}\n"
        "Census Geocoder and Mapbox both failed. Check your address and network."
    )


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
