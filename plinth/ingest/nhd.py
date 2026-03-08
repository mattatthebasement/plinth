"""NHDPlus High Resolution (HR) hydrography ingestor.

Downloads HU4 units covering NE Oklahoma (VPU 11, Arkansas-White-Red) from
the USGS The National Map API and loads flowlines and waterbodies into PostGIS.
"""

import zipfile
from pathlib import Path
from typing import Optional

from plinth.ingest.base import BaseIngestor

TNM_API = "https://tnmaccess.nationalmap.gov/api/v1/products"
NHD_DATASET = "National Hydrography Dataset Plus High Resolution (NHDPlus HR)"

# HU4 units that cover NE Oklahoma (Rogers County at 36.05N, 95.81W)
# Verified via TNM bbox query at bbox=(-96.0,35.9,-95.5,36.3)
HU4_UNITS = ["1107", "1109", "1110", "1111"]

# NE-Oklahoma bounding box (matches REGIONS in cli/ingest.py)
_NE_OK_BBOX = (-96.5, 35.5, -94.5, 37.0)


class NhdIngestor(BaseIngestor):
    """Download NHDPlus HR GDBs for VPU-11 HU4 units and load into PostGIS.

    Only named features (``GNIS_NAME IS NOT NULL``) are loaded to reduce volume.
    """

    source_name = "nhd-hr"
    update_frequency = "annual"

    def download(self, region: Optional[str] = None) -> None:
        """Query TNM API once for all HU4 units, then fetch each GDB package."""
        import httpx

        self._log("Querying TNM API for NE Oklahoma NHD-HR units…")
        url_map = self._get_all_tnm_urls()

        for hu4 in HU4_UNITS:
            url = url_map.get(hu4)
            if url is None:
                self._log(f"  Warning: no download URL found for HU4 {hu4}, skipping.")
                continue

            dest = self.staging_dir / f"nhd_{hu4}.zip"
            fresh = self._download_if_changed(url, dest)
            unzip_dir = self.staging_dir / hu4
            if fresh or not unzip_dir.exists():
                self._log(f"  Unzipping nhd_{hu4}.zip…")
                unzip_dir.mkdir(parents=True, exist_ok=True)
                with zipfile.ZipFile(dest) as zf:
                    zf.extractall(unzip_dir)

    def _get_all_tnm_urls(self) -> dict[str, str]:
        """Make a single TNM API call for the bbox and return {hu4: download_url}."""
        import httpx

        bbox = _NE_OK_BBOX
        params = {
            "datasets": NHD_DATASET,
            "bbox": f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}",
            "outputFormat": "JSON",
            "max": 100,
        }
        try:
            resp = httpx.get(TNM_API, params=params, timeout=60, follow_redirects=True)
            resp.raise_for_status()
            items = resp.json().get("items", [])
        except Exception as exc:
            self._log(f"  TNM API error: {exc}")
            return {}

        url_map: dict[str, str] = {}
        for item in items:
            title = item.get("title", "")
            url = item.get("downloadURL", "")
            if not url.endswith(".zip") or "GDB" not in url.upper():
                continue
            for hu4 in HU4_UNITS:
                if hu4 not in url_map and (f"- {hu4} " in title or f"- {hu4}(" in title):
                    url_map[hu4] = url
        return url_map

    def validate(self) -> None:
        """Check that downloaded zips and GDB directories are present."""
        for hu4 in HU4_UNITS:
            dest = self.staging_dir / f"nhd_{hu4}.zip"
            if not dest.exists():
                self._log(f"  Warning: zip not found for HU4 {hu4}.")
                continue
            if dest.stat().st_size == 0:
                raise ValueError(f"Empty zip for HU4 {hu4}: {dest}")
            unzip_dir = self.staging_dir / hu4
            if not unzip_dir.exists():
                raise ValueError(
                    f"Unzip directory not found for HU4 {hu4}: {unzip_dir}"
                )

    def load(self) -> None:
        """Load flowlines and waterbodies for each HU4."""
        bbox = _NE_OK_BBOX  # (minx, miny, maxx, maxy)

        for hu4 in HU4_UNITS:
            dest = self.staging_dir / f"nhd_{hu4}.zip"
            if not dest.exists():
                self._log(f"Skipping HU4 {hu4} — zip not downloaded.")
                continue

            gdb_path = self._find_gdb(self.staging_dir / hu4)
            if gdb_path is None:
                self._log(f"Warning: no GDB found for HU4 {hu4}.")
                continue

            self._log(f"Loading flowlines for HU4 {hu4}…")
            self._load_flowlines(str(gdb_path), bbox)

            self._log(f"Loading waterbodies for HU4 {hu4}…")
            self._load_waterbodies(str(gdb_path), bbox)

    def _find_gdb(self, directory: Path) -> Optional[Path]:
        for item in directory.rglob("*.gdb"):
            if item.is_dir():
                return item
        return None

    def _load_flowlines(self, gdb_path: str, bbox: tuple) -> None:
        staging = "_staging_nhd_flow"
        spat_args = [
            "-dim", "2",  # strip Z coordinates — NHD GDBs use 3D geometries
            "-spat", str(bbox[0]), str(bbox[1]), str(bbox[2]), str(bbox[3]),
        ]
        try:
            self._ogr2ogr_to_staging_table(
                gdb_path, "NHDFlowline", staging, extra_args=spat_args
            )
        except RuntimeError as exc:
            self._log(f"  ogr2ogr error (flowlines): {exc}")
            return

        from plinth.db.connection import get_connection

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    INSERT INTO nhd_flowlines
                        (permanent_identifier, gnis_name, lengthkm, ftype, fcode, geom)
                    SELECT
                        permanent_identifier,
                        gnis_name,
                        lengthkm::numeric,
                        ftype::integer,
                        fcode::integer,
                        geom
                    FROM {staging}
                    WHERE gnis_name IS NOT NULL AND gnis_name != ''
                    ON CONFLICT (permanent_identifier) DO UPDATE SET
                        geom      = EXCLUDED.geom,
                        gnis_name = EXCLUDED.gnis_name,
                        lengthkm  = EXCLUDED.lengthkm
                    """
                )
                rows = cur.rowcount
                cur.execute(f"DROP TABLE IF EXISTS {staging}")
            conn.commit()
        self._log(f"  Flowline rows upserted: {rows}")

    def _load_waterbodies(self, gdb_path: str, bbox: tuple) -> None:
        staging = "_staging_nhd_wb"
        spat_args = [
            "-dim", "2",  # strip Z coordinates — NHD GDBs use 3D geometries
            "-spat", str(bbox[0]), str(bbox[1]), str(bbox[2]), str(bbox[3]),
        ]
        try:
            self._ogr2ogr_to_staging_table(
                gdb_path, "NHDWaterbody", staging, extra_args=spat_args
            )
        except RuntimeError as exc:
            self._log(f"  ogr2ogr error (waterbodies): {exc}")
            return

        from plinth.db.connection import get_connection

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    INSERT INTO nhd_waterbodies
                        (permanent_identifier, gnis_name, areasqkm, ftype, fcode, geom)
                    SELECT
                        permanent_identifier,
                        gnis_name,
                        areasqkm::numeric,
                        ftype::integer,
                        fcode::integer,
                        geom
                    FROM {staging}
                    WHERE gnis_name IS NOT NULL AND gnis_name != ''
                    ON CONFLICT (permanent_identifier) DO UPDATE SET
                        geom      = EXCLUDED.geom,
                        gnis_name = EXCLUDED.gnis_name,
                        areasqkm  = EXCLUDED.areasqkm
                    """
                )
                rows = cur.rowcount
                cur.execute(f"DROP TABLE IF EXISTS {staging}")
            conn.commit()
        self._log(f"  Waterbody rows upserted: {rows}")

    def register(self) -> None:
        """Register this source in data_source_registry."""
        import datetime

        self._upsert_registry(
            version=datetime.date.today().isoformat(),
            coverage_region="ne-oklahoma",
            notes=(
                "NHDPlus HR hydrography for VPU 11 (Arkansas-White-Red). "
                f"HU4 units: {', '.join(HU4_UNITS)}. Named features only."
            ),
        )
