"""USDA Wildfire Hazard Potential (WHP) 2023 raster ingestor.

Downloads the WHP 2023 continuous index raster for a region via the
USFS ImageServer (imagery.geoplatform.gov), converts to COG, uploads
to MinIO, and registers the tile in raster_tiles.

Source: USDA Forest Service / USFS EDW — WHP 2023, 270 m resolution
        https://imagery.geoplatform.gov/iipp/rest/services/
          Fire_Aviation/USFS_EDW_RMRS_WildfireHazardPotentialContinuous/ImageServer
CRS:    Source is EPSG:3857; reprojected to EPSG:4326 for COG
Refresh: Annual check
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import httpx

from plinth.ingest.base import BaseIngestor
from plinth.raster.cog import to_cog
from plinth.raster.minio import upload_cog

_IMAGESERVER = (
    "https://imagery.geoplatform.gov/iipp/rest/services"
    "/Fire_Aviation/USFS_EDW_RMRS_WildfireHazardPotentialContinuous"
    "/ImageServer/exportImage"
)
_DATASET = "usda-whp"
_VERSION = "2023"

# NE Oklahoma bounding box with 0.5° buffer (WGS84)
_REGIONS: dict[str, tuple[float, float, float, float]] = {
    "ne-oklahoma": (-97.0, 35.0, -94.0, 37.5),
}


class UsdaWhpRasterIngestor(BaseIngestor):
    """Download USDA WHP 2023 raster for a region and store as COG in MinIO."""

    source_name = "usda-whp"
    update_frequency = "annual"

    def download(self, region: Optional[str] = None) -> None:
        """Export the WHP raster for *region* via the USFS ImageServer."""
        region = region or "ne-oklahoma"
        if region not in _REGIONS:
            raise ValueError(f"Unknown region: {region}. Known: {list(_REGIONS)}")

        dest = self._raw_path(region)
        if dest.exists():
            self._log(f"Raw WHP raster already present: {dest.name} — skipping download.")
            return

        minx, miny, maxx, maxy = _REGIONS[region]
        self._log(f"Requesting WHP 2023 export for {region} from USFS ImageServer…")

        # Step 1: request the export and get the temporary image URL
        resp = httpx.get(
            _IMAGESERVER,
            params={
                "bbox": f"{minx},{miny},{maxx},{maxy}",
                "bboxSR": "4326",
                "size": "2000,2000",
                "format": "tiff",
                "pixelType": "S32",
                "noDataInterpretation": "esriNoDataMatchAny",
                "interpolation": "RSP_NearestNeighbor",
                "f": "json",
            },
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()

        if "error" in data:
            raise ValueError(f"ImageServer error: {data['error']}")

        href = data.get("href")
        if not href:
            raise ValueError(f"No href in ImageServer response: {data}")

        self._log(f"  Downloading GeoTIFF ({data.get('width')}×{data.get('height')} px)…")

        # Step 2: download the exported GeoTIFF
        with httpx.stream("GET", href, timeout=300, follow_redirects=True) as r:
            r.raise_for_status()
            dest.parent.mkdir(parents=True, exist_ok=True)
            with open(dest, "wb") as f:
                for chunk in r.iter_bytes(chunk_size=1 << 20):
                    f.write(chunk)

        size_mb = dest.stat().st_size / 1e6
        self._log(f"  Downloaded: {dest.name} ({size_mb:.1f} MB)")

    def validate(self) -> None:
        """Verify the raw WHP clip is present and non-empty."""
        region = self._region or "ne-oklahoma"
        dest = self._raw_path(region)
        if not dest.exists():
            raise ValueError(f"Raw WHP raster not found: {dest}")
        if dest.stat().st_size < 10_000:
            raise ValueError(f"WHP file suspiciously small: {dest}")
        self._log(f"Validation passed: {dest.name}")

    def load(self) -> None:
        """Reproject to EPSG:4326, convert to COG, upload to MinIO, register tile."""
        import rasterio
        from plinth.db.connection import get_connection

        region = self._region or "ne-oklahoma"
        raw = self._raw_path(region)
        cog_path = self.staging_dir / f"{region}_cog.tif"

        self._log("Converting to COG (reprojecting to EPSG:4326)…")
        to_cog(raw, cog_path, reproject_epsg=4326)
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
            notes="USDA Forest Service WHP 2023 continuous index (270m). Clipped via USFS ImageServer.",
        )

    def _raw_path(self, region: str) -> Path:
        return self.staging_dir / f"{region}_raw.tif"
