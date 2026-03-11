"""USGS Seismic Hazard Design Values raster ingestor.

Grid-samples the USGS Design Maps API (NEHRP 2020) at 0.1° intervals over
the NE Oklahoma region, assembles a 3-band GeoTIFF (band 1 = PGA, band 2 = Ss,
band 3 = S1 in units of g), converts to COG, uploads to MinIO, and registers
the tile in raster_tiles.

This produces a locally-queryable raster that replaces the per-point Design
Maps API call at report time.  The grid is dense enough for the 0.1° effective
resolution of the NEHRP 2020 model.

Source: USGS Design Maps Web Service (NEHRP 2020)
        https://earthquake.usgs.gov/ws/designmaps/nehrp-2020.json
Grid:   0.05° (~5.5 km) over bbox 35.0–37.5°N, 97.5–94.0°W
Refresh: When NSHM model updates (every ~5 years)
"""
from __future__ import annotations

import csv
import time
from pathlib import Path
from typing import Optional

import httpx
import numpy as np

from plinth.ingest.base import BaseIngestor
from plinth.raster.cog import to_cog
from plinth.raster.minio import upload_cog

_DESIGN_MAPS_URL = "https://earthquake.usgs.gov/ws/designmaps/nehrp-2020.json"
_DATASET = "usgs-seismic"
_VERSION = "2023"
_RISK_CATEGORY = "II"
_SITE_CLASS = "C"

# Grid bounds and resolution (with 0.5° buffer beyond NE Oklahoma)
_LAT_MIN, _LAT_MAX = 35.0, 37.5
_LON_MIN, _LON_MAX = -97.5, -94.0
_GRID_STEP = 0.05   # degrees; ~5.5 km at these latitudes

# Rate limit: stay well under USGS limits
_REQUEST_DELAY_S = 0.25

# Band index mapping in the output GeoTIFF
_BANDS = {"pgam": 1, "ss": 2, "s1": 3}
_BAND_NAMES = {1: "PGA_MCER_g", 2: "Ss_MCER_g", 3: "S1_MCER_g"}

_REGIONS: dict[str, tuple[float, float, float, float]] = {
    "ne-oklahoma": (_LAT_MIN, _LAT_MAX, _LON_MIN, _LON_MAX),
}


def _build_grid(
    lat_min: float, lat_max: float, lon_min: float, lon_max: float, step: float
) -> list[tuple[float, float]]:
    """Return (lat, lon) grid point list covering the bbox."""
    lats = np.arange(lat_min, lat_max + step * 0.5, step)
    lons = np.arange(lon_min, lon_max + step * 0.5, step)
    return [(round(float(la), 4), round(float(lo), 4)) for la in lats for lo in lons]


class UsgsSeismicRasterIngestor(BaseIngestor):
    """Build NEHRP 2020 design-value raster for a region and store in MinIO."""

    source_name = "usgs-seismic"
    update_frequency = "annual"

    def download(self, region: Optional[str] = None) -> None:
        """Grid-sample the Design Maps API and cache results to a CSV."""
        region = region or self._region or "ne-oklahoma"
        if region not in _REGIONS:
            raise ValueError(f"Unknown region: {region}. Known: {list(_REGIONS)}")

        cache_csv = self._cache_csv_path(region)
        if cache_csv.exists():
            # Check freshness: stale after 30 days
            age_days = (time.time() - cache_csv.stat().st_mtime) / 86400
            if age_days < 30:
                cached_count = sum(1 for _ in cache_csv.read_text().splitlines()) - 1
                self._log(f"Grid CSV already cached ({cached_count} points, {age_days:.0f}d old) — skipping download.")
                return

        lat_min, lat_max, lon_min, lon_max = _REGIONS[region]
        grid = _build_grid(lat_min, lat_max, lon_min, lon_max, _GRID_STEP)
        total = len(grid)
        self._log(f"Grid-sampling USGS Design Maps API: {total} points at {_GRID_STEP}° over {region}…")

        # Resume from existing partial cache if possible
        existing: dict[tuple[float, float], dict] = {}
        if cache_csv.exists():
            with open(cache_csv, newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    key = (float(row["lat"]), float(row["lon"]))
                    existing[key] = row

        cache_csv.parent.mkdir(parents=True, exist_ok=True)
        fetched = 0
        skipped = 0
        failed = 0

        with open(cache_csv, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["lat", "lon", "pgam", "ss", "s1"])

            for idx, (lat, lon) in enumerate(grid):
                key = (lat, lon)
                if key in existing:
                    row = existing[key]
                    writer.writerow([lat, lon, row["pgam"], row["ss"], row["s1"]])
                    skipped += 1
                    continue

                try:
                    resp = httpx.get(
                        _DESIGN_MAPS_URL,
                        params={
                            "latitude": lat,
                            "longitude": lon,
                            "riskCategory": _RISK_CATEGORY,
                            "siteClass": _SITE_CLASS,
                            "title": "Plinth Seismic Grid",
                        },
                        timeout=30,
                    )
                    resp.raise_for_status()
                    data = resp.json().get("response", {}).get("data", {})
                    pgam = data.get("pgam")
                    ss = data.get("ss")
                    s1 = data.get("s1")
                    writer.writerow([lat, lon,
                                     pgam if pgam is not None else "",
                                     ss if ss is not None else "",
                                     s1 if s1 is not None else ""])
                    fetched += 1
                except Exception as exc:
                    self._log(f"  WARNING: API error at ({lat}, {lon}): {exc}")
                    writer.writerow([lat, lon, "", "", ""])
                    failed += 1

                if (idx + 1) % 50 == 0:
                    self._log(f"  {idx + 1}/{total} points (fetched={fetched}, skipped={skipped}, failed={failed})")
                time.sleep(_REQUEST_DELAY_S)

        self._log(f"Grid sampling complete: {fetched} fetched, {skipped} from cache, {failed} failed → {cache_csv.name}")

    def validate(self) -> None:
        """Verify the cached CSV has enough valid data points."""
        region = self._region or "ne-oklahoma"
        cache_csv = self._cache_csv_path(region)
        if not cache_csv.exists():
            raise ValueError(f"Seismic grid CSV not found: {cache_csv}")

        valid = 0
        with open(cache_csv, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("pgam"):
                    valid += 1

        min_expected = len(_build_grid(*_REGIONS[region], _GRID_STEP)) // 2
        if valid < min_expected:
            raise ValueError(
                f"Too few valid seismic grid points: {valid} < {min_expected} expected"
            )
        self._log(f"Validation passed: {valid} valid grid points in {cache_csv.name}")

    def load(self) -> None:
        """Build multi-band GeoTIFF, convert to COG, upload to MinIO, register tile."""
        import rasterio
        from rasterio.transform import from_bounds
        from plinth.db.connection import get_connection

        region = self._region or "ne-oklahoma"
        cache_csv = self._cache_csv_path(region)
        lat_min, lat_max, lon_min, lon_max = _REGIONS[region]

        self._log("Assembling 3-band GeoTIFF from grid CSV…")
        grid = _build_grid(lat_min, lat_max, lon_min, lon_max, _GRID_STEP)
        lats = sorted(set(p[0] for p in grid))
        lons = sorted(set(p[1] for p in grid))
        nrows, ncols = len(lats), len(lons)
        lat_idx = {la: i for i, la in enumerate(lats)}
        lon_idx = {lo: j for j, lo in enumerate(lons)}

        # 3 bands, float32, NaN for missing
        bands = np.full((3, nrows, ncols), np.nan, dtype=np.float32)

        with open(cache_csv, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                la = round(float(row["lat"]), 4)
                lo = round(float(row["lon"]), 4)
                ri = lat_idx.get(la)
                ci = lon_idx.get(lo)
                if ri is None or ci is None:
                    continue
                # Flip row: rasterio convention has row 0 at top (max lat)
                flip_ri = nrows - 1 - ri
                try:
                    pgam = float(row["pgam"]) if row["pgam"] else np.nan
                    ss = float(row["ss"]) if row["ss"] else np.nan
                    s1 = float(row["s1"]) if row["s1"] else np.nan
                except (ValueError, KeyError):
                    pgam = ss = s1 = np.nan
                bands[0, flip_ri, ci] = pgam
                bands[1, flip_ri, ci] = ss
                bands[2, flip_ri, ci] = s1

        half = _GRID_STEP / 2
        transform = from_bounds(
            lon_min - half, lat_min - half,
            lon_max + half, lat_max + half,
            ncols, nrows,
        )

        raw_path = self._raw_path(region)
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        _NODATA = -9999.0

        with rasterio.open(
            raw_path, "w",
            driver="GTiff",
            height=nrows, width=ncols,
            count=3, dtype="float32",
            crs="EPSG:4326",
            transform=transform,
            nodata=_NODATA,
        ) as dst:
            nan_mask = np.isnan(bands)
            bands[nan_mask] = _NODATA
            dst.write(bands)
            for band_num, name in _BAND_NAMES.items():
                dst.update_tags(band_num, name=name)

        size_mb = raw_path.stat().st_size / 1e6
        self._log(f"  Raw GeoTIFF: {raw_path.name} ({size_mb:.1f} MB, {nrows}×{ncols} px, 3 bands)")

        cog_path = self.staging_dir / f"{region}_cog.tif"
        self._log("Converting to COG…")
        to_cog(raw_path, cog_path)
        size_mb = cog_path.stat().st_size / 1e6
        self._log(f"  COG: {cog_path.name} ({size_mb:.1f} MB)")

        s3_key = f"{_DATASET}/{_VERSION}/{region}.tif"
        self._log(f"Uploading to MinIO: {s3_key}")
        upload_cog(cog_path, s3_key)

        with rasterio.open(cog_path) as ds:
            bounds = ds.bounds
            res_m = (ds.res[0] + ds.res[1]) / 2 * 111_320

        self._log("Registering tile in raster_tiles…")
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO raster_tiles (dataset, s3_key, bounds, resolution_m, tile_id, dataset_version)
                    VALUES (%(dataset)s, %(s3_key)s,
                            ST_MakeEnvelope(%(minx)s,%(miny)s,%(maxx)s,%(maxy)s, 4326),
                            %(res_m)s, %(tile_id)s, %(version)s)
                    ON CONFLICT (s3_key) DO UPDATE SET
                        bounds = EXCLUDED.bounds,
                        resolution_m = EXCLUDED.resolution_m,
                        dataset_version = EXCLUDED.dataset_version
                    """,
                    {
                        "dataset": _DATASET,
                        "s3_key": s3_key,
                        "minx": bounds.left, "miny": bounds.bottom,
                        "maxx": bounds.right, "maxy": bounds.top,
                        "res_m": round(res_m, 1),
                        "tile_id": region,
                        "version": _VERSION,
                    },
                )
            conn.commit()
        self._log(f"  Tile registered (res ~{res_m:.0f} m, bands: PGA/Ss/S1).")

    def register(self) -> None:
        self._upsert_registry(
            version=_VERSION,
            coverage_region=self._region or "ne-oklahoma",
            notes=(
                "USGS NEHRP 2020 seismic design values (PGA, Ss, S1 in g). "
                f"Grid-sampled at {_GRID_STEP}° from Design Maps API. "
                "3-band GeoTIFF: band 1=PGA, band 2=Ss, band 3=S1. "
                f"Risk category {_RISK_CATEGORY}, site class {_SITE_CLASS}."
            ),
        )

    def _raw_path(self, region: str) -> Path:
        return self.staging_dir / f"{region}_raw.tif"

    def _cache_csv_path(self, region: str) -> Path:
        return self.staging_dir / f"{region}_grid.csv"
