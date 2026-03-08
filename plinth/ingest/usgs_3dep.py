"""USGS 3DEP Digital Elevation Model ingestor.

Downloads a clipped DEM for the target region via the USGS 3DEP ArcGIS
ImageServer exportImage endpoint, converts to COG, uploads to MinIO, and
registers the tile in raster_tiles.

Source: USGS National Elevation Dataset 1/3 arc-second via
        https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer
Resolution: ~10m native; capped at 8,000×8,000 px per export → ~22 m over NE Oklahoma
Refresh: Annual check
"""

from pathlib import Path
from typing import Optional

import httpx

from plinth.ingest.base import BaseIngestor
from plinth.raster.cog import to_cog
from plinth.raster.minio import upload_cog

_IMAGESERVER = (
    "https://elevation.nationalmap.gov/arcgis/rest/services/"
    "3DEPElevation/ImageServer/exportImage"
)
_DATASET = "usgs-3dep"
_VERSION = "2025"

# NE Oklahoma region bounding box (EPSG:4326)
_REGIONS: dict[str, tuple[float, float, float, float]] = {
    "ne-oklahoma": (-96.5, 35.5, -94.5, 37.0),
}


class Usgs3depIngestor(BaseIngestor):
    """Download USGS 3DEP DEM for a region and store as COG in MinIO."""

    source_name = "usgs-3dep"
    update_frequency = "annual"

    def download(self, region: Optional[str] = None) -> None:
        """Export the DEM for *region* from the USGS ImageServer."""
        region = region or "ne-oklahoma"
        if region not in _REGIONS:
            raise ValueError(f"Unknown region: {region}. Known: {list(_REGIONS)}")

        dest = self._raw_path(region)
        if dest.exists():
            self._log(f"Raw DEM already present: {dest.name} — skipping download.")
            return

        minx, miny, maxx, maxy = _REGIONS[region]
        self._log(f"Exporting 3DEP DEM for {region} from USGS ImageServer…")

        # Step 1: request the export and get the temporary image URL
        resp = httpx.get(
            _IMAGESERVER,
            params={
                "bbox": f"{minx},{miny},{maxx},{maxy}",
                "bboxSR": "4326",
                "size": "8000,8000",
                "format": "tiff",
                "pixelType": "F32",
                "noDataInterpretation": "esriNoDataMatchAny",
                "interpolation": "RSP_BilinearInterpolation",
                "f": "json",
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        href = data.get("href")
        if not href:
            raise ValueError(f"No href in ImageServer response: {data}")

        self._log(f"  Downloading exported GeoTIFF ({data.get('width')}×{data.get('height')} px)…")

        # Step 2: download the exported GeoTIFF
        with httpx.stream("GET", href, timeout=120, follow_redirects=True) as r:
            r.raise_for_status()
            dest.parent.mkdir(parents=True, exist_ok=True)
            with open(dest, "wb") as f:
                for chunk in r.iter_bytes(chunk_size=1 << 20):
                    f.write(chunk)

        size_mb = dest.stat().st_size / 1e6
        self._log(f"  Downloaded: {dest.name} ({size_mb:.1f} MB)")

    def validate(self) -> None:
        """Verify each expected raw DEM is present and non-empty."""
        region = self._region or "ne-oklahoma"
        dest = self._raw_path(region)
        if not dest.exists():
            raise ValueError(f"Raw DEM not found: {dest}")
        if dest.stat().st_size < 100_000:
            raise ValueError(f"DEM file suspiciously small: {dest}")
        self._log(f"Validation passed: {dest.name}")

    def load(self) -> None:
        """Convert raw DEM to COG, upload to MinIO, register in raster_tiles."""
        from plinth.db.connection import get_connection
        import rasterio

        region = self._region or "ne-oklahoma"
        raw = self._raw_path(region)
        cog_path = self.staging_dir / f"{region}_cog.tif"

        self._log("Converting to COG…")
        to_cog(raw, cog_path, reproject_epsg=4326)
        size_mb = cog_path.stat().st_size / 1e6
        self._log(f"  COG: {cog_path.name} ({size_mb:.1f} MB)")

        s3_key = f"{_DATASET}/{_VERSION}/{region}.tif"
        self._log(f"Uploading to MinIO: {s3_key}")
        upload_cog(cog_path, s3_key)

        # Read bounds and resolution from the COG
        with rasterio.open(cog_path) as ds:
            bounds = ds.bounds
            res_m = (ds.res[0] + ds.res[1]) / 2 * 111_320  # rough deg→m

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
        """Upsert a row in data_source_registry."""
        self._upsert_registry(
            version=_VERSION,
            coverage_region=self._region or "ne-oklahoma",
            notes="USGS 3DEP 1/3 arc-second DEM via ArcGIS ImageServer export. ~22m effective resolution over NE Oklahoma.",
        )

    def _raw_path(self, region: str) -> Path:
        return self.staging_dir / f"{region}_raw.tif"
