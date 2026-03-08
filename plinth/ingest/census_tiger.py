"""Census TIGER/Line ingestor — block groups and tracts for Oklahoma."""

import zipfile
from pathlib import Path
from typing import Optional

from plinth.ingest.base import BaseIngestor

TIGER_YEAR = "2023"
STATE_FIPS = "40"  # Oklahoma

_BG_URL = (
    f"https://www2.census.gov/geo/tiger/TIGER{TIGER_YEAR}/BG/"
    f"tl_{TIGER_YEAR}_{STATE_FIPS}_bg.zip"
)
_TRACT_URL = (
    f"https://www2.census.gov/geo/tiger/TIGER{TIGER_YEAR}/TRACT/"
    f"tl_{TIGER_YEAR}_{STATE_FIPS}_tract.zip"
)


class CensusTigerIngestor(BaseIngestor):
    """Download and load Census TIGER/Line block groups and tracts.

    Geometry only — ACS demographic values are fetched at query time via the
    Census API and cached in ``query_cache``.
    """

    source_name = "census-tiger"
    update_frequency = "annual"

    def download(self, region: Optional[str] = None) -> None:
        """Download Oklahoma block-group and tract shapefiles if changed."""
        for url, filename in [
            (_BG_URL, f"tl_{TIGER_YEAR}_{STATE_FIPS}_bg.zip"),
            (_TRACT_URL, f"tl_{TIGER_YEAR}_{STATE_FIPS}_tract.zip"),
        ]:
            dest = self.staging_dir / filename
            fresh = self._download_if_changed(url, dest)
            subdir = dest.with_suffix("")  # strip .zip
            if fresh or not subdir.exists():
                self._log(f"Unzipping {filename}…")
                subdir.mkdir(parents=True, exist_ok=True)
                with zipfile.ZipFile(dest) as zf:
                    zf.extractall(subdir)

    def validate(self) -> None:
        """Verify zip files and unzipped shapefiles are present."""
        for stem in [
            f"tl_{TIGER_YEAR}_{STATE_FIPS}_bg",
            f"tl_{TIGER_YEAR}_{STATE_FIPS}_tract",
        ]:
            zip_path = self.staging_dir / f"{stem}.zip"
            if not zip_path.exists() or zip_path.stat().st_size == 0:
                raise ValueError(f"Missing or empty zip: {zip_path}")
            shp_path = self.staging_dir / stem / f"{stem}.shp"
            if not shp_path.exists():
                raise ValueError(f"Shapefile not found after unzip: {shp_path}")

    def load(self) -> None:
        """Upsert block groups and tracts into PostGIS."""
        self._load_block_groups()
        self._load_tracts()

    def _load_block_groups(self) -> None:
        stem = f"tl_{TIGER_YEAR}_{STATE_FIPS}_bg"
        shp = str(self.staging_dir / stem / f"{stem}.shp")
        staging = "_staging_census_bg"

        self._log("Loading block groups via ogr2ogr…")
        self._ogr2ogr_to_staging_table(shp, stem, staging)

        from plinth.db.connection import get_connection

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    INSERT INTO census_block_groups
                        (geoid, statefp, countyfp, tractce, blkgrpce, aland, awater, geom)
                    SELECT geoid, statefp, countyfp, tractce, blkgrpce,
                           aland::bigint, awater::bigint, geom
                    FROM {staging}
                    ON CONFLICT (geoid) DO UPDATE SET
                        geom    = EXCLUDED.geom,
                        aland   = EXCLUDED.aland,
                        awater  = EXCLUDED.awater
                    """
                )
                rows = cur.rowcount
                cur.execute(f"DROP TABLE IF EXISTS {staging}")
            conn.commit()
        self._log(f"Block groups upserted: {rows}")

    def _load_tracts(self) -> None:
        stem = f"tl_{TIGER_YEAR}_{STATE_FIPS}_tract"
        shp = str(self.staging_dir / stem / f"{stem}.shp")
        staging = "_staging_census_tract"

        self._log("Loading tracts via ogr2ogr…")
        self._ogr2ogr_to_staging_table(shp, stem, staging)

        from plinth.db.connection import get_connection

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    INSERT INTO census_tracts
                        (geoid, statefp, countyfp, tractce, aland, awater, geom)
                    SELECT geoid, statefp, countyfp, tractce,
                           aland::bigint, awater::bigint, geom
                    FROM {staging}
                    ON CONFLICT (geoid) DO UPDATE SET
                        geom   = EXCLUDED.geom,
                        aland  = EXCLUDED.aland,
                        awater = EXCLUDED.awater
                    """
                )
                rows = cur.rowcount
                cur.execute(f"DROP TABLE IF EXISTS {staging}")
            conn.commit()
        self._log(f"Tracts upserted: {rows}")

    def register(self) -> None:
        """Register this source in data_source_registry."""
        self._upsert_registry(
            version=TIGER_YEAR,
            coverage_region="oklahoma",
            notes=(
                f"Block groups and census tracts for Oklahoma (state FIPS {STATE_FIPS}). "
                "ACS demographics fetched at query time via Census API — not bulk loaded."
            ),
        )
