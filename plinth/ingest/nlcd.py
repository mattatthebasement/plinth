"""NLCD 2021 National Land Cover Database ingestor.

Clips NLCD 2021 for the target region via the MRLC WCS (Web Coverage
Service) endpoint, converts to COG, uploads to MinIO, and registers the
tile in raster_tiles.

Source: MRLC GeoServer WCS
        https://www.mrlc.gov/geoserver/mrlc_display/NLCD_2021_Land_Cover_L48/wcs
CRS: Source is EPSG:3857 (Web Mercator); reprojected to EPSG:4326 for COG
Refresh: Annual check
"""

from pathlib import Path
from typing import Optional

import httpx

from plinth.ingest.base import BaseIngestor
from plinth.raster.cog import to_cog
from plinth.raster.minio import upload_cog

_WCS_URL = (
    "https://www.mrlc.gov/geoserver/mrlc_display/"
    "NLCD_2021_Land_Cover_L48/wcs"
)
_DATASET = "nlcd"
_VERSION = "2021"

# NE Oklahoma bbox in WGS84
_REGIONS: dict[str, tuple[float, float, float, float]] = {
    "ne-oklahoma": (-96.5, 35.5, -94.5, 37.0),
}


class NlcdIngestor(BaseIngestor):
    """Download NLCD 2021 land cover for a region and store as COG in MinIO."""

    source_name = "nlcd"
    update_frequency = "annual"

    def download(self, region: Optional[str] = None) -> None:
        """Clip NLCD via WCS GetCoverage for *region*."""
        region = region or "ne-oklahoma"
        if region not in _REGIONS:
            raise ValueError(f"Unknown region: {region}. Known: {list(_REGIONS)}")

        dest = self._raw_path(region)
        if dest.exists():
            self._log(f"Raw NLCD already present: {dest.name} — skipping download.")
            return

        minx_wgs, miny_wgs, maxx_wgs, maxy_wgs = _REGIONS[region]

        self._log(f"Fetching NLCD 2021 for {region} via WCS GetCoverage…")

        # Use subsettingCrs=EPSG:4326 so we can pass WGS84 Long/Lat bounds
        # directly without converting to Web Mercator (which GeoServer rejects).
        params = {
            "service": "WCS",
            "version": "2.0.1",
            "request": "GetCoverage",
            "coverageId": "mrlc_display__NLCD_2021_Land_Cover_L48",
            "format": "image/geotiff",
            "subsettingCrs": "http://www.opengis.net/def/crs/EPSG/0/4326",
            "outputCrs": "http://www.opengis.net/def/crs/EPSG/0/4326",
            "subset": [
                f"Long({minx_wgs},{maxx_wgs})",
                f"Lat({miny_wgs},{maxy_wgs})",
            ],
        }

        with httpx.stream("GET", _WCS_URL, params=params, timeout=300, follow_redirects=True) as r:
            r.raise_for_status()
            content_type = r.headers.get("content-type", "")
            if "xml" in content_type.lower():
                body = r.read()
                raise ValueError(f"WCS returned XML error: {body[:500]}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            with open(dest, "wb") as f:
                for chunk in r.iter_bytes(chunk_size=1 << 20):
                    f.write(chunk)

        size_mb = dest.stat().st_size / 1e6
        self._log(f"  Downloaded: {dest.name} ({size_mb:.1f} MB)")

    def validate(self) -> None:
        """Verify the raw NLCD clip is present and non-empty."""
        region = self._region or "ne-oklahoma"
        dest = self._raw_path(region)
        if not dest.exists():
            raise ValueError(f"Raw NLCD not found: {dest}")
        if dest.stat().st_size < 10_000:
            raise ValueError(f"NLCD file suspiciously small: {dest}")
        self._log(f"Validation passed: {dest.name}")

    def load(self) -> None:
        """Reproject to EPSG:4326, convert to COG, upload to MinIO, register tile."""
        import rasterio
        from plinth.db.connection import get_connection

        region = self._region or "ne-oklahoma"
        raw = self._raw_path(region)
        cog_path = self.staging_dir / f"{region}_cog.tif"

        self._log("Converting to COG…")
        to_cog(raw, cog_path)  # already in EPSG:4326, no reprojection needed
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
        self._log(f"  Tile registered (res ~{res_m:.0f} m).")

    def register(self) -> None:
        self._upsert_registry(
            version=_VERSION,
            coverage_region=self._region or "ne-oklahoma",
            notes="NLCD 2021 Land Cover (CONUS) clipped via MRLC WCS (subsettingCrs=EPSG:4326). ~30m resolution.",
        )

    def _raw_path(self, region: str) -> Path:
        return self.staging_dir / f"{region}_raw.tif"
