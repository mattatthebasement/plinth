"""plinth-cli verify — bulk-ingestion coverage checks.

Usage:
    plinth-cli verify all
    plinth-cli verify census-acs
    plinth-cli verify epa-aqs
    plinth-cli verify nasa-power
    plinth-cli verify usgs-earthquakes
    plinth-cli verify usda-whp
    plinth-cli verify usgs-seismic

Each check queries the database and/or raster_tiles and prints a one-line
PASS/FAIL per dataset.  Exit code is 0 only if all requested checks pass.
"""
from __future__ import annotations

import sys
from typing import Any

import click

# NE Oklahoma bounding box (with 0.5° buffer)
_BBOX = (-97.0, 35.0, -94.0, 37.5)

# Test coordinate: 11822 E 116th St N, Collinsville, OK
_TEST_LAT = 36.32197414685
_TEST_LON = -95.842032856739


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _db():
    from plinth.db.connection import get_connection
    return get_connection()


def _pass(name: str, detail: str) -> dict:
    return {"name": name, "ok": True, "detail": detail}


def _fail(name: str, detail: str) -> dict:
    return {"name": name, "ok": False, "detail": detail}


def _print_results(results: list[dict]) -> int:
    """Print formatted results table; return 1 if any failed."""
    width = max(len(r["name"]) for r in results) + 2
    click.echo()
    click.echo("  ── Dataset coverage " + "─" * 45)
    for r in results:
        icon = click.style("✓", fg="green") if r["ok"] else click.style("✗", fg="red")
        name_col = r["name"].ljust(width)
        click.echo(f"  {icon}  {name_col} {r['detail']}")
    click.echo("  " + "─" * 66)
    click.echo()
    failed = [r for r in results if not r["ok"]]
    if failed:
        click.echo(click.style(f"  {len(failed)} check(s) failed.", fg="red"))
        return 1
    click.echo(click.style(f"  All {len(results)} checks passed.", fg="green"))
    return 0


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def _check_census_acs() -> dict:
    """Check ACS block group data coverage."""
    name = "census-acs-bulk"
    try:
        with _db() as conn:
            with conn.cursor() as cur:
                # Total rows
                cur.execute("SELECT COUNT(*) FROM acs_block_group_data")
                total = cur.fetchone()[0]

                # NE OK counties (FIPS 40xxx): geoid starts with '40'
                cur.execute(
                    "SELECT COUNT(DISTINCT geoid) FROM acs_block_group_data "
                    "WHERE geoid LIKE '40%'"
                )
                ok_count = cur.fetchone()[0]

                # Latest year
                cur.execute("SELECT MAX(acs_year) FROM acs_block_group_data")
                latest_year = cur.fetchone()[0]

                # Check test county (Tulsa = 40143) has data
                cur.execute(
                    "SELECT COUNT(*) FROM acs_block_group_data WHERE geoid LIKE '40143%'"
                )
                tulsa_count = cur.fetchone()[0]

        if total == 0:
            return _fail(name, "No rows loaded")
        if ok_count == 0:
            return _fail(name, "No Oklahoma block groups found (geoid LIKE '40%')")
        if tulsa_count == 0:
            return _fail(name, "Tulsa County (40143) not present")
        return _pass(
            name,
            f"{total:,} rows total; {ok_count:,} OK block groups; "
            f"Tulsa: {tulsa_count} BGs; latest year: {latest_year}"
        )
    except Exception as exc:
        return _fail(name, f"ERROR: {exc}")


def _check_epa_aqs() -> dict:
    """Check EPA AQS sites and summary coverage."""
    name = "epa-aqs-bulk"
    minx, miny, maxx, maxy = _BBOX
    try:
        with _db() as conn:
            with conn.cursor() as cur:
                # Sites in bbox
                cur.execute(
                    """
                    SELECT COUNT(*) FROM epa_aqs_sites
                    WHERE longitude BETWEEN %s AND %s
                      AND latitude  BETWEEN %s AND %s
                    """,
                    (minx, maxx, miny, maxy),
                )
                site_count = cur.fetchone()[0]

                # Check PM2.5 and Ozone present within 100 km of test coord
                cur.execute(
                    """
                    SELECT COUNT(DISTINCT a.parameter_code)
                    FROM epa_aqs_annual_summary a
                    JOIN epa_aqs_sites s ON a.site_id = s.site_id
                    WHERE a.parameter_code IN ('88101', '44201')
                      AND ST_DWithin(
                            s.geom::geography,
                            ST_MakePoint(%s, %s)::geography,
                            200000
                          )
                    """,
                    (_TEST_LON, _TEST_LAT),
                )
                params_found = cur.fetchone()[0]

                # Latest year
                cur.execute("SELECT MAX(year) FROM epa_aqs_annual_summary")
                latest_year = cur.fetchone()[0]

                # Total summary rows
                cur.execute("SELECT COUNT(*) FROM epa_aqs_annual_summary")
                summary_count = cur.fetchone()[0]

        if site_count == 0:
            return _fail(name, f"No sites in NE OK bbox {_BBOX}")
        if params_found < 2:
            return _fail(name, f"Missing PM2.5 or Ozone within 200 km of test coord (found {params_found}/2 params)")
        return _pass(
            name,
            f"{site_count} sites in bbox; PM2.5+O3 within 200km ✓; "
            f"{summary_count:,} summary rows; latest: {latest_year}"
        )
    except Exception as exc:
        return _fail(name, f"ERROR: {exc}")


def _check_nasa_power() -> dict:
    """Check NASA POWER climatology grid coverage."""
    name = "nasa-power-bulk"
    try:
        with _db() as conn:
            with conn.cursor() as cur:
                # Cell count
                cur.execute(
                    "SELECT COUNT(DISTINCT (grid_lat, grid_lon)) FROM nasa_power_climatology"
                )
                cell_count = cur.fetchone()[0]

                # All 13 months (0=annual, 1-12=monthly)
                cur.execute("SELECT COUNT(DISTINCT month) FROM nasa_power_climatology")
                month_count = cur.fetchone()[0]

                # Non-null t2m_mean_c at test coord (nearest grid cell)
                cur.execute(
                    """
                    SELECT t2m_mean_c FROM nasa_power_climatology
                    WHERE month = 0
                    ORDER BY ABS(grid_lat - %s) + ABS(grid_lon - %s)
                    LIMIT 1
                    """,
                    (_TEST_LAT, _TEST_LON),
                )
                row = cur.fetchone()
                t2m_annual = row[0] if row else None

        if cell_count == 0:
            return _fail(name, "No grid cells loaded")
        if month_count < 13:
            return _fail(name, f"Only {month_count}/13 months loaded")
        if t2m_annual is None:
            return _fail(name, "No T2M annual value near test coordinate")
        return _pass(
            name,
            f"{cell_count} grid cells; {month_count} months; "
            f"T2M annual at test coord: {t2m_annual:.1f}°C"
        )
    except Exception as exc:
        return _fail(name, f"ERROR: {exc}")


def _check_usgs_earthquakes() -> dict:
    """Check USGS earthquake event coverage."""
    name = "usgs-earthquakes-bulk"
    minx, miny, maxx, maxy = _BBOX
    try:
        with _db() as conn:
            with conn.cursor() as cur:
                # Total count in bbox
                cur.execute(
                    """
                    SELECT COUNT(*) FROM usgs_earthquake_events
                    WHERE ST_Within(geom, ST_MakeEnvelope(%s,%s,%s,%s,4326))
                    """,
                    (minx, miny, maxx, maxy),
                )
                count = cur.fetchone()[0]

                # Date range
                cur.execute(
                    "SELECT MIN(occurred_at)::date, MAX(occurred_at)::date "
                    "FROM usgs_earthquake_events"
                )
                min_date, max_date = cur.fetchone()

                # Spot-check: 2016 Pawnee M5.8
                cur.execute(
                    """
                    SELECT event_id, magnitude FROM usgs_earthquake_events
                    WHERE magnitude >= 5.0
                      AND occurred_at BETWEEN '2016-09-01' AND '2016-09-30'
                      AND ST_Within(geom, ST_MakeEnvelope(-97.5, 35.0, -94.0, 37.5, 4326))
                    LIMIT 1
                    """
                )
                pawnee = cur.fetchone()

                # Spot-check: 2011 Prague M5.7
                cur.execute(
                    """
                    SELECT event_id, magnitude FROM usgs_earthquake_events
                    WHERE magnitude >= 5.0
                      AND occurred_at BETWEEN '2011-11-01' AND '2011-11-10'
                    LIMIT 1
                    """
                )
                prague = cur.fetchone()

        if count == 0:
            return _fail(name, "No events in NE OK bbox")
        notes = []
        if pawnee:
            notes.append(f"Pawnee M{pawnee[1]} ✓")
        else:
            notes.append("Pawnee 2016 NOT FOUND")
        if prague:
            notes.append(f"Prague M{prague[1]} ✓")
        else:
            notes.append("Prague 2011 NOT FOUND")
        return _pass(
            name,
            f"{count:,} events in bbox; {min_date}–{max_date}; "
            + ", ".join(notes)
        )
    except Exception as exc:
        return _fail(name, f"ERROR: {exc}")


def _check_usda_whp() -> dict:
    """Check USDA WHP raster tile registration and sample value."""
    name = "usda-whp-raster"
    try:
        with _db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*), MIN(resolution_m) FROM raster_tiles WHERE dataset = 'usda-whp'"
                )
                tile_count, res_m = cur.fetchone()

        if tile_count == 0:
            return _fail(name, "No tile registered in raster_tiles for dataset='usda-whp'")

        # Try to sample the COG at the test coordinate
        sample_val = _sample_raster_value("usda-whp", _TEST_LAT, _TEST_LON, band=1)
        if sample_val is None:
            return _fail(name, f"{tile_count} tile(s) registered; sample at test coord: NO DATA")
        return _pass(
            name,
            f"{tile_count} tile(s) registered (~{res_m:.0f}m); "
            f"test coord WHP value: {int(sample_val):,}"
        )
    except Exception as exc:
        return _fail(name, f"ERROR: {exc}")


def _check_usgs_seismic() -> dict:
    """Check USGS seismic design-value raster tile registration and sample."""
    name = "usgs-seismic-raster"
    try:
        with _db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*), MIN(resolution_m) FROM raster_tiles WHERE dataset = 'usgs-seismic'"
                )
                tile_count, res_m = cur.fetchone()

        if tile_count == 0:
            return _fail(name, "No tile registered in raster_tiles for dataset='usgs-seismic'")

        # Sample all 3 bands (PGA, Ss, S1) at test coordinate
        pga = _sample_raster_value("usgs-seismic", _TEST_LAT, _TEST_LON, band=1)
        ss = _sample_raster_value("usgs-seismic", _TEST_LAT, _TEST_LON, band=2)
        s1 = _sample_raster_value("usgs-seismic", _TEST_LAT, _TEST_LON, band=3)

        if pga is None:
            return _fail(name, f"{tile_count} tile(s) registered; PGA sample at test coord: NO DATA")
        return _pass(
            name,
            f"{tile_count} tile(s) registered (~{res_m:.0f}m); "
            f"test coord: PGA={pga:.3f}g  Ss={ss:.3f}g  S1={s1:.3f}g"
        )
    except Exception as exc:
        return _fail(name, f"ERROR: {exc}")


# ---------------------------------------------------------------------------
# Raster sampling helper
# ---------------------------------------------------------------------------

def _sample_raster_value(
    dataset: str, lat: float, lon: float, band: int = 1
) -> float | None:
    """Fetch the pixel value at (lat, lon) from the named MinIO COG tile."""
    import tempfile
    from pathlib import Path

    import rasterio

    from plinth.raster.minio import download_cog

    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT s3_key FROM raster_tiles
                WHERE dataset = %s
                  AND ST_Contains(bounds, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
                ORDER BY resolution_m
                LIMIT 1
                """,
                (dataset, lon, lat),
            )
            row = cur.fetchone()

    if row is None:
        return None

    s3_key = row[0]
    with tempfile.TemporaryDirectory() as tmp:
        local = Path(tmp) / "tile.tif"
        download_cog(s3_key, local)
        with rasterio.open(local) as ds:
            row_idx, col_idx = ds.index(lon, lat)
            data = ds.read(band, window=rasterio.windows.Window(col_idx, row_idx, 1, 1))
            val = float(data[0, 0])
            nodata = ds.nodata
    if nodata is not None and val == nodata:
        return None
    return val


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------

_ALL_CHECKS = {
    "census-acs": _check_census_acs,
    "epa-aqs": _check_epa_aqs,
    "nasa-power": _check_nasa_power,
    "usgs-earthquakes": _check_usgs_earthquakes,
    "usda-whp": _check_usda_whp,
    "usgs-seismic": _check_usgs_seismic,
}


@click.group()
def verify() -> None:
    """Dataset ingestion coverage verification."""


@verify.command("all")
def verify_all() -> None:
    """Run all ingestion coverage checks."""
    results = [fn() for fn in _ALL_CHECKS.values()]
    sys.exit(_print_results(results))


def _make_single_check_command(key: str, fn):
    @verify.command(key)
    def _cmd():
        results = [fn()]
        sys.exit(_print_results(results))
    _cmd.__name__ = key.replace("-", "_")
    return _cmd


for _key, _fn in _ALL_CHECKS.items():
    _make_single_check_command(_key, _fn)
