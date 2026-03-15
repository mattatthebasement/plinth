"""Water & utility infrastructure query module.

Queries four data sources for any lat/lon in CONUS:
  1. EPA SDWIS service areas (water_system_boundaries → sdwis_water_systems)
  2. USGS Principal Aquifers (usgs_principal_aquifers)
  3. USGS NWIS Groundwater Wells + recent discrete readings
  4. Ma et al. (2025) modeled water table depth COG from MinIO
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from plinth.db.connection import get_connection

log = logging.getLogger(__name__)

_MAX_WELL_MI = 10.0
_MAX_SYSTEM_MI = 20.0
_MI_TO_M = 1609.344
_READINGS_STALE_DAYS = 30  # re-fetch well readings if last update is older than this


def _refresh_nearby_readings(site_nos: list[str], conn) -> None:
    """Fetch any readings newer than what we have from the USGS OGC API and write
    them directly to the database.

    Called at report time for nearby wells only.  Silent on all API errors — the
    report uses whatever is in the DB already.  Skips wells whose most recent
    reading is less than _READINGS_STALE_DAYS old.
    """
    import datetime
    import time

    import httpx

    from plinth.config import get_settings

    _FIELD_MEAS_URL = "https://api.waterdata.usgs.gov/ogcapi/v0/collections/field-measurements/items"
    _STALE_CUTOFF = datetime.date.today() - datetime.timedelta(days=_READINGS_STALE_DAYS)

    try:
        settings = get_settings()
        api_key = settings.usgs_api_key
        headers = {"X-Api-Key": api_key} if api_key else {}
    except Exception:
        return

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT site_no, MAX(lev_dt) AS last_dt
                FROM usgs_groundwater_well_readings
                WHERE site_no = ANY(%s)
                GROUP BY site_no
                """,
                (site_nos,),
            )
            freshness: dict[str, datetime.date | None] = {r[0]: r[1] for r in cur.fetchall()}
    except Exception as exc:
        log.debug("_refresh_nearby_readings: could not query DB: %s", exc)
        return

    new_rows: list[tuple] = []
    for site_no in site_nos:
        last_dt = freshness.get(site_no)
        if last_dt is not None and last_dt >= _STALE_CUTOFF:
            continue  # recent enough

        # Start one day after last known reading, or 90 days back for wells with no readings
        if last_dt is not None:
            since = (last_dt + datetime.timedelta(days=1)).isoformat() + "T00:00:00Z"
        else:
            since = (
                datetime.date.today() - datetime.timedelta(days=90)
            ).isoformat() + "T00:00:00Z"
        until = datetime.date.today().isoformat() + "T23:59:59Z"

        try:
            resp = httpx.get(
                _FIELD_MEAS_URL,
                params={
                    "f": "json",
                    "parameter_code": ",".join(["72019", "62610", "62611", "72150"]),
                    "monitoring_location_id": f"USGS-{site_no}",
                    "datetime": f"{since}/{until}",
                    "limit": 100,
                },
                headers=headers,
                timeout=30,
            )
            if resp.status_code != 200:
                continue
            data = resp.json()
        except Exception:
            continue

        for feature in data.get("features", []):
            props = feature.get("properties", {})
            raw_site = props.get("monitoring_location_id", "")
            sno = raw_site.replace("USGS-", "")
            raw_dt = props.get("time", "")[:10] if props.get("time") else None
            try:
                lev_dt = datetime.date.fromisoformat(raw_dt) if raw_dt else None
            except ValueError:
                lev_dt = None

            raw_val = props.get("value")
            try:
                lev_va = float(raw_val) if raw_val is not None else None
            except (TypeError, ValueError):
                lev_va = None

            meth = props.get("parameter_code")
            qual_list = props.get("qualifier", [])
            qualifier = ", ".join(qual_list) if isinstance(qual_list, list) else str(qual_list) if qual_list else None

            if sno and lev_dt:
                new_rows.append((sno, lev_dt, lev_va, meth, qualifier))

        time.sleep(0.5)

    if not new_rows:
        return

    try:
        with conn.cursor() as cur:
            for row in new_rows:
                cur.execute(
                    """
                    INSERT INTO usgs_groundwater_well_readings
                        (site_no, lev_dt, lev_va, parameter_code, qualifier)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (site_no, lev_dt, COALESCE(qualifier, ''))
                    DO UPDATE SET
                        lev_va         = EXCLUDED.lev_va,
                        parameter_code = EXCLUDED.parameter_code
                    """,
                    row,
                )
        conn.commit()
        log.debug("_refresh_nearby_readings: inserted/updated %d readings", len(new_rows))
    except Exception as exc:
        log.warning("_refresh_nearby_readings: DB write failed: %s", exc)
        try:
            conn.rollback()
        except Exception:
            pass


def query_water_infrastructure(lat: float, lon: float) -> dict[str, Any]:
    """Return water and utility infrastructure data for the given coordinates.

    Returns
    -------
    dict with keys:
        available           bool
        service_systems     list[dict]  — CWS/NTNC systems whose boundary contains the site
        site_in_service_area bool
        nearby_systems      list[dict]  — nearest systems when site is outside all boundaries
        aquifer             dict | None — principal aquifer (containing or nearest)
        wells               list[dict]  — up to 8 USGS monitoring wells within 10 mi
        wtd                 dict        — HydroFrame modeled water table depth
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            # ── Service area lookup (site inside boundary) ───────────────────
            cur.execute(
                """
                SELECT w.pwsid, w.pws_name, w.boundary_source,
                       ST_AsGeoJSON(ST_Simplify(w.geom, 0.002)) AS geom_json,
                       s.pws_type_code, s.primary_source, s.owner_type_code,
                       s.population_served, s.service_connections,
                       s.activity_code, s.violation_count_5yr, s.state_code
                FROM water_system_boundaries w
                LEFT JOIN sdwis_water_systems s ON s.pwsid = w.pwsid
                WHERE ST_Contains(w.geom, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
                ORDER BY s.population_served DESC NULLS LAST
                LIMIT 4
                """,
                (lon, lat),
            )
            service_col = [d[0] for d in cur.description]
            service_rows = cur.fetchall()

            # ── Nearest service areas (fallback when site is outside all) ────
            if not service_rows:
                cur.execute(
                    """
                    SELECT w.pwsid, w.pws_name, w.boundary_source,
                           ST_AsGeoJSON(ST_Simplify(w.geom, 0.002)) AS geom_json,
                           s.pws_type_code, s.primary_source, s.owner_type_code,
                           s.population_served, s.service_connections,
                           s.activity_code, s.violation_count_5yr, s.state_code,
                           ST_Distance(
                               w.geom::geography,
                               ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
                           ) / 1609.344 AS dist_mi
                    FROM water_system_boundaries w
                    LEFT JOIN sdwis_water_systems s ON s.pwsid = w.pwsid
                    WHERE ST_DWithin(
                        w.geom::geography,
                        ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                        %s
                    )
                    ORDER BY dist_mi
                    LIMIT 3
                    """,
                    (lon, lat, lon, lat, _MAX_SYSTEM_MI * _MI_TO_M),
                )
                nearby_service_col = [d[0] for d in cur.description]
                nearby_service_rows = cur.fetchall()
            else:
                nearby_service_rows = []
                nearby_service_col = service_col + ["dist_mi"]

            # ── Principal aquifer (containing) ───────────────────────────────
            cur.execute(
                """
                SELECT aq_name, aq_code, rock_type, aquifer_type,
                       ST_AsGeoJSON(ST_Simplify(geom, 0.01)) AS geom_json
                FROM usgs_principal_aquifers
                WHERE ST_Contains(geom, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
                  AND aq_code != 999
                LIMIT 1
                """,
                (lon, lat),
            )
            aquifer_col = [d[0] for d in cur.description]
            aquifer_row = cur.fetchone()

            # ── Hydrogeologic region (province + region + description) ────────
            cur.execute(
                """
                SELECT
                    p.prov_name,
                    r.reg_name,
                    r.reg_code,
                    r.reg_type,
                    r.lithology,
                    d.description   AS reg_description,
                    d.confidence    AS reg_confidence
                FROM usgs_hydrogeologic_regions r
                JOIN usgs_hydrogeologic_provinces p
                    ON ST_Contains(p.geom, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
                LEFT JOIN usgs_hydrogeologic_region_descriptions d
                    ON d.reg_code = r.reg_code
                WHERE ST_Contains(r.geom, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
                LIMIT 1
                """,
                (lon, lat, lon, lat),
            )
            hydro_region_col = [d[0] for d in cur.description]
            hydro_region_row = cur.fetchone()

            # ── Nearby groundwater monitoring wells ──────────────────────────
            cur.execute(
                """
                SELECT site_no, station_nm, state_cd, aquifer_cd, nat_aqfr_cd,
                       well_depth_ft,
                       dtw_median_ft, dtw_min_ft, dtw_max_ft, dtw_obs_count,
                       dtw_period_start, dtw_period_end,
                       ST_Distance(
                           geom::geography,
                           ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
                       ) / 1609.344 AS dist_mi,
                       ST_Y(geom) AS well_lat,
                       ST_X(geom) AS well_lon
                FROM usgs_groundwater_wells
                WHERE ST_DWithin(
                    geom::geography,
                    ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                    %s
                )
                ORDER BY dist_mi
                LIMIT 8
                """,
                (lon, lat, lon, lat, _MAX_WELL_MI * _MI_TO_M),
            )
            well_col = [d[0] for d in cur.description]
            well_rows = cur.fetchall()

            # ── Recent discrete readings for nearby wells ─────────────────────
            well_site_nos = [r[0] for r in well_rows]  # site_no is first column
            if well_site_nos:
                _refresh_nearby_readings(well_site_nos, conn)

            readings_by_site: dict[str, list[dict]] = {}
            if well_site_nos:
                cur.execute(
                    """
                    SELECT site_no, lev_dt, lev_va, parameter_code, qualifier
                    FROM usgs_groundwater_well_readings
                    WHERE site_no = ANY(%s)
                    ORDER BY site_no, lev_dt DESC
                    """,
                    (well_site_nos,),
                )
                for row in cur.fetchall():
                    sno, lev_dt, lev_va, parameter_code, qualifier = row
                    if sno not in readings_by_site:
                        readings_by_site[sno] = []
                    readings_by_site[sno].append({
                        "lev_dt":         lev_dt.isoformat() if lev_dt else None,
                        "lev_va":         float(lev_va) if lev_va is not None else None,
                        "parameter_code": parameter_code,
                        "qualifier":      qualifier,
                    })

    def row_to_dict(row: tuple, cols: list[str]) -> dict:
        return dict(zip(cols, row))

    # Assemble service systems
    site_in_service_area = len(service_rows) > 0
    service_systems = [row_to_dict(r, service_col) for r in service_rows]
    nearby_systems = [row_to_dict(r, nearby_service_col) for r in nearby_service_rows]

    # Assemble aquifer
    if aquifer_row:
        aquifer: dict | None = row_to_dict(aquifer_row, aquifer_col)
        aquifer["is_containing"] = True
        aquifer["dist_mi"] = None
    else:
        aquifer = None

    wells = [row_to_dict(r, well_col) for r in well_rows]
    # Attach readings to each well
    for w in wells:
        w["readings"] = readings_by_site.get(w["site_no"], [])

    hydro_region = (
        dict(zip(hydro_region_col, hydro_region_row)) if hydro_region_row else None
    )

    # Ma et al. (2025) modeled WTD — COG point sample from MinIO
    wtd = _query_ma_wtd(lat, lon)

    return {
        "available": True,
        "service_systems": service_systems,
        "site_in_service_area": site_in_service_area,
        "nearby_systems": nearby_systems,
        "aquifer": aquifer,
        "hydro_region": hydro_region,
        "wells": wells,
        "wtd": wtd,
    }


def _query_ma_wtd(lat: float, lon: float) -> dict[str, Any]:
    """Sample the Ma et al. (2025) water table depth COG at a point.

    The COG is stored in MinIO at ``ma-wtd/2025/wtd_mean_conus.tif``.
    A single pixel is read via a window read — no full-file download.
    Raises no exceptions; returns ``{"available": False}`` on any error.

    Returns a dict with:
        available      bool
        wtd_m          float — modeled WTD in meters (positive = below surface)
        wtd_ft         float — same, converted to feet
        source         str
        note           str
    """
    import tempfile
    from plinth.db.connection import get_connection
    from plinth.raster.minio import download_cog

    _DATASET = "ma-wtd"
    s3_key: str | None = None
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT s3_key FROM raster_tiles
                WHERE dataset = %s
                  AND ST_Contains(bounds, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
                LIMIT 1
                """,
                (_DATASET, lon, lat),
            )
            row = cur.fetchone()
    if row:
        s3_key = row[0]

    if s3_key is None:
        return {"available": False, "flag": "Ma WTD raster not yet ingested."}

    try:
        import rasterio

        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp) / "wtd_tile.tif"
            download_cog(s3_key, local)
            with rasterio.open(local) as ds:
                row_idx, col_idx = ds.index(lon, lat)
                window = rasterio.windows.Window(col_idx, row_idx, 1, 1)
                data = ds.read(1, window=window)
                nodata = ds.nodata
        val = float(data[0, 0])
        if nodata is not None and val == nodata:
            return {"available": False, "flag": "No data at this location in Ma WTD raster."}
        return {
            "available": True,
            "wtd_m":  round(val, 2),
            "wtd_ft": round(val * 3.28084, 1),
            "source": "Ma et al. (2026)",
            "note": (
                "Modeled mean depth to water table — r=0.79, RMSE≈49 ft. "
                "Use for planning context only; not a substitute for site investigation. "
                "Source: Ma, Y. et al. (2026). Commun Earth Environ 7, 45. "
                "DOI: 10.1038/s43247-025-03094-3"
            ),
        }
    except Exception as exc:
        log.warning("Ma WTD COG query failed at (%.4f, %.4f): %s", lat, lon, exc)
        return {"available": False, "flag": f"Ma WTD data unavailable: {exc}"}
