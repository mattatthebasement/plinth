"""IECC 2021 Climate Zone ingestor.

Downloads the DOE/PNNL IECC 2021 climate zone shapefile components from the
GitHub mirror maintained at dalton-cole/energy-calculator (sourced from the
official PNNL/DOE dataset).  Polygons for the same zone label are unioned so
each zone is stored as a single MultiPolygon.
"""

import json
from pathlib import Path
from typing import Optional

from plinth.ingest.base import BaseIngestor

# Shapefile components hosted on GitHub — stable for a decadal dataset.
# Source: https://github.com/dalton-cole/energy-calculator/tree/main/ClimateZoneDataFiles
_GITHUB_BASE = (
    "https://raw.githubusercontent.com/dalton-cole/energy-calculator/main"
    "/ClimateZoneDataFiles/ClimateZones"
)
_SHP_EXTENSIONS = [".shp", ".dbf", ".shx", ".prj", ".cpg"]


class IeccIngestor(BaseIngestor):
    """Download and load DOE/PNNL IECC 2021 climate zone boundaries.

    Same-label polygons are unioned into a single MultiPolygon in
    ``iecc_climate_zones``.

    Fields used:
        BA_Climate_ → zone_label       (e.g. "3A")
        Climate_Zon → zone_description (e.g. "Mixed-Humid")
    """

    source_name = "iecc-climate-zones"
    update_frequency = "decadal"

    def download(self, region: Optional[str] = None) -> None:
        """Download IECC shapefile components from GitHub."""
        shp_dir = self.staging_dir / "iecc_2021"
        meta = shp_dir / "meta.json"

        if meta.exists():
            saved = json.loads(meta.read_text()).get("fetched_date", "")
            from datetime import date, timedelta
            try:
                if date.today() - date.fromisoformat(saved) < timedelta(days=30):
                    self._log("iecc_2021 shapefile: up to date (< 30 days old)")
                    return
            except ValueError:
                pass

        self._log("Downloading IECC 2021 shapefile components from GitHub…")
        shp_dir.mkdir(parents=True, exist_ok=True)

        for ext in _SHP_EXTENSIONS:
            url = f"{_GITHUB_BASE}{ext}"
            dest = shp_dir / f"ClimateZones{ext}"
            self._download_if_changed(url, dest)

        import datetime
        meta.write_text(json.dumps({"fetched_date": datetime.date.today().isoformat()}))
        self._log("  Shapefile components downloaded.")

    def validate(self) -> None:
        """Verify required shapefile components exist."""
        shp_dir = self.staging_dir / "iecc_2021"
        for ext in [".shp", ".dbf", ".shx"]:
            p = shp_dir / f"ClimateZones{ext}"
            if not p.exists() or p.stat().st_size == 0:
                raise ValueError(f"Missing or empty shapefile component: {p}")

    def load(self) -> None:
        """Load IECC zones into PostGIS, unioning polygons by zone label."""
        shp_path = str(self.staging_dir / "iecc_2021" / "ClimateZones.shp")
        staging = "_staging_iecc"
        self._ogr2ogr_to_staging_table(shp_path, "ClimateZones", staging)

        from plinth.db.connection import get_connection

        with get_connection() as conn:
            with conn.cursor() as cur:
                # Detect actual column names (ogr2ogr truncates to 10 chars)
                cur.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = %s ORDER BY ordinal_position",
                    (staging,),
                )
                cols = [r[0].lower() for r in cur.fetchall()]
                self._log(f"  Staging columns: {cols}")

                # This shapefile is county-level with climate zone attributes.
                # iecc21 = IECC 2021 zone label (e.g. "3A")
                # ba21   = Building America zone description (e.g. "Mixed-Humid")
                zone_col = next(
                    (c for c in cols if c in ("iecc21", "ba_climate", "icc_zone")),
                    None,
                )
                desc_col = next(
                    (c for c in cols if c in ("ba21", "climate_zon", "moisture21")),
                    None,
                )
                if zone_col is None:
                    raise RuntimeError(
                        f"Could not find zone label column in {staging}. Columns: {cols}"
                    )
                desc_expr = desc_col if desc_col else "NULL"

                cur.execute(
                    f"""
                    INSERT INTO iecc_climate_zones (zone_label, zone_description, geom)
                    SELECT
                        {zone_col},
                        MAX({desc_expr}),
                        ST_Multi(ST_Union(geom))
                    FROM {staging}
                    WHERE {zone_col} IS NOT NULL
                    GROUP BY {zone_col}
                    ON CONFLICT (zone_label) DO UPDATE SET
                        geom = ST_Multi(ST_Union(EXCLUDED.geom, iecc_climate_zones.geom))
                    """
                )
                rows = cur.rowcount
                cur.execute(f"DROP TABLE IF EXISTS {staging}")
            conn.commit()
        self._log(f"IECC zone rows upserted: {rows}")

    def register(self) -> None:
        """Register this source in data_source_registry."""
        self._upsert_registry(
            version="IECC-2021",
            coverage_region="national",
            notes=(
                "DOE/PNNL IECC 2021 climate zone boundaries. "
                "Same-label polygons are unioned into a single MultiPolygon. "
                "Source: dalton-cole/energy-calculator GitHub mirror of PNNL dataset."
            ),
        )
