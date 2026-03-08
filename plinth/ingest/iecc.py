"""IECC 2021 Climate Zone ingestor."""

import subprocess
import zipfile
from pathlib import Path
from typing import Optional

from plinth.ingest.base import BaseIngestor

IECC_URL = (
    "https://opendata.arcgis.com/api/v3/datasets/"
    "4bd3b8e311af4e13be0b13ffd0e53b8b_0/downloads/data"
    "?format=shp&spatialRefId=4326"
)
IECC_URL_FALLBACK = (
    "https://climate.ncsu.edu/images/climate_zones/"
    "2021_iecc_climate_zone_shapefile.zip"
)


class IeccIngestor(BaseIngestor):
    """Download and load DOE/PNNL IECC 2021 climate zone boundaries.

    Polygons for the same zone label are unioned into a single MultiPolygon
    in ``iecc_climate_zones``.
    """

    source_name = "iecc-climate-zones"
    update_frequency = "decadal"

    def download(self, region: Optional[str] = None) -> None:
        """Download the IECC 2021 shapefile zip."""
        dest = self.staging_dir / "iecc_2021.zip"
        unzip_dir = self.staging_dir / "iecc_2021"

        try:
            fresh = self._download_if_changed(IECC_URL, dest)
        except Exception as exc:
            self._log(
                f"Primary URL failed: {exc}. "
                f"Trying fallback: {IECC_URL_FALLBACK}"
            )
            fresh = self._download_if_changed(IECC_URL_FALLBACK, dest)

        if fresh or not unzip_dir.exists():
            self._log("Unzipping iecc_2021.zip…")
            unzip_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(dest) as zf:
                zf.extractall(unzip_dir)

    def validate(self) -> None:
        """Verify the zip and at least one .shp file exist."""
        dest = self.staging_dir / "iecc_2021.zip"
        if not dest.exists() or dest.stat().st_size == 0:
            raise ValueError(f"Missing or empty zip: {dest}")
        shp = self._find_shp()
        if shp is None:
            raise ValueError(
                f"No .shp file found under {self.staging_dir / 'iecc_2021'}"
            )

    def load(self) -> None:
        """Load IECC zones into PostGIS, unioning polygons by zone label."""
        shp = self._find_shp()
        if shp is None:
            raise RuntimeError("Shapefile not found — run validate() first.")

        layer_name = self._detect_layer_name(shp)
        self._log(f"Layer detected: {layer_name}")

        staging = "_staging_iecc"
        self._ogr2ogr_to_staging_table(str(shp), layer_name, staging)

        zone_col, desc_col = self._detect_columns(staging)
        self._log(f"Zone column: {zone_col!r}, description column: {desc_col!r}")

        from plinth.db.connection import get_connection

        with get_connection() as conn:
            with conn.cursor() as cur:
                desc_expr = f"{desc_col}" if desc_col else "NULL"
                cur.execute(
                    f"""
                    INSERT INTO iecc_climate_zones (zone_label, zone_description, geom)
                    SELECT
                        {zone_col},
                        {desc_expr},
                        ST_Multi(ST_Union(geom))
                    FROM {staging}
                    WHERE {zone_col} IS NOT NULL
                    GROUP BY {zone_col}, {desc_expr}
                    ON CONFLICT (zone_label) DO UPDATE SET
                        geom = ST_Multi(ST_Union(EXCLUDED.geom, iecc_climate_zones.geom))
                    """
                )
                rows = cur.rowcount
                cur.execute(f"DROP TABLE IF EXISTS {staging}")
            conn.commit()
        self._log(f"IECC zone rows upserted: {rows}")

    def _find_shp(self) -> Optional[Path]:
        """Return the first .shp file inside the unzipped directory."""
        unzip_dir = self.staging_dir / "iecc_2021"
        for p in unzip_dir.rglob("*.shp"):
            return p
        return None

    def _detect_layer_name(self, shp: Path) -> str:
        """Use ogrinfo to discover the layer name inside the shapefile."""
        result = subprocess.run(
            ["ogrinfo", "-ro", "-al", "-so", str(shp)],
            capture_output=True,
            text=True,
        )
        for line in result.stdout.splitlines():
            if line.startswith("Layer name:"):
                return line.split(":", 1)[1].strip()
        # Fall back to stem name
        return shp.stem

    def _detect_columns(self, staging_table: str) -> tuple[str, Optional[str]]:
        """Inspect the staging table to find the zone-label and description columns."""
        from plinth.db.connection import get_connection

        zone_candidates = [
            "ba_climate_",
            "iecc_climat",
            "zone",
            "climate_zon",
            "climzone",
            "icc_zone",
        ]
        desc_candidates = [
            "zone_descri",
            "description",
            "zone_desc",
            "moisture",
        ]

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = %s
                    ORDER BY ordinal_position
                    """,
                    (staging_table,),
                )
                cols = [row[0].lower() for row in cur.fetchall()]

        zone_col: Optional[str] = None
        for candidate in zone_candidates:
            matches = [c for c in cols if c.startswith(candidate)]
            if matches:
                zone_col = matches[0]
                break
        if zone_col is None:
            # Last resort: pick first text-like column that isn't geom/gid/ogc_fid
            for c in cols:
                if c not in ("geom", "gid", "ogc_fid", "wkb_geometry"):
                    zone_col = c
                    break
        if zone_col is None:
            raise RuntimeError(
                f"Could not detect zone-label column in {staging_table}. "
                f"Available columns: {cols}"
            )

        desc_col: Optional[str] = None
        for candidate in desc_candidates:
            matches = [c for c in cols if c.startswith(candidate)]
            if matches:
                desc_col = matches[0]
                break

        return zone_col, desc_col

    def register(self) -> None:
        """Register this source in data_source_registry."""
        self._upsert_registry(
            version="IECC-2021",
            coverage_region="national",
            notes=(
                "DOE/PNNL IECC 2021 climate zone boundaries. "
                "Polygons for the same zone label are unioned into a single MultiPolygon."
            ),
        )
