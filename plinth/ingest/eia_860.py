"""EIA Form 860 Annual Electric Generator Report ingestor.

Downloads the most recent EIA-860 annual ZIP from eia.gov, parses the Plant
and Generator Excel worksheets, aggregates generator data to the plant level,
and upserts into eia_power_plants.

Each row in eia_power_plants represents one physical generating plant with
capacity aggregated across all of its generators. The primary_fuel column
identifies the fuel type of the highest-capacity generator(s). The
capacity_mw_by_fuel JSONB column provides a per-fuel breakdown.

Source:  https://www.eia.gov/electricity/data/eia860/
Refresh: Annual (new data released mid-year for prior calendar year)
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Optional

from plinth.ingest.base import BaseIngestor

# EIA-860 annual ZIP URL pattern
# Current year uses xls/, archived years use archive/xls/
_BASE_URL_CURRENT = "https://www.eia.gov/electricity/data/eia860/xls/eia860{year}.zip"
_BASE_URL_ARCHIVE = "https://www.eia.gov/electricity/data/eia860/archive/xls/eia860{year}.zip"

# Default to most recent data year; can be overridden via constructor
_DEFAULT_YEAR = 2024

# EIA fuel code descriptions (for reference — stored as-is in DB)
# NG=Natural Gas, SUN=Solar, WND=Wind, WAT=Hydro, NUC=Nuclear,
# COL=Coal, OIL=Oil/Petroleum, OTH=Other, DFO=Distillate Fuel Oil, etc.


class Eia860Ingestor(BaseIngestor):
    """Download EIA-860 and load power plant data into eia_power_plants.

    Args:
        year: EIA-860 data year (default 2023). The ZIP contains plant and
              generator data as-reported for that calendar year.
    """

    source_name = "eia-860"
    update_frequency = "annual"

    def __init__(self, year: int = _DEFAULT_YEAR) -> None:
        super().__init__()
        self.year = year

    @property
    def _zip_path(self) -> Path:
        return self.staging_dir / f"eia860{self.year}.zip"

    def download(self, region: Optional[str] = None) -> None:
        """Download EIA-860 annual ZIP with ETag-based idempotency."""
        import datetime
        current_year = datetime.date.today().year
        # Delete stale HTML non-ZIP if present
        if self._zip_path.exists():
            try:
                import zipfile as _zf
                _zf.ZipFile(self._zip_path).close()
            except Exception:
                self._log("Removing stale/invalid cached file.")
                self._zip_path.unlink()

        # EIA-860 URL layout:
        #   Current (2 most recent years): xls/eia860{year}.zip
        #   Older archive:                 archive/xls/eia860{year}.zip
        if self.year >= current_year - 2:
            url = _BASE_URL_CURRENT.format(year=self.year)
        else:
            url = _BASE_URL_ARCHIVE.format(year=self.year)
        self._log(f"Checking EIA-860 {self.year} ZIP…")
        fetched = self._download_if_changed(url, self._zip_path)
        if not fetched:
            self._log("ZIP is up-to-date (ETag matched).")

    def validate(self) -> None:
        """Verify the ZIP exists and contains expected worksheets."""
        if not self._zip_path.exists():
            raise ValueError(f"EIA-860 ZIP not found: {self._zip_path}")
        if self._zip_path.stat().st_size < 500_000:
            raise ValueError(f"ZIP suspiciously small: {self._zip_path.stat().st_size} bytes")

        with zipfile.ZipFile(self._zip_path) as zf:
            names = [n.lower() for n in zf.namelist()]

        # Expect plant sheet (2___Plant_YYYY.xlsx) and generator sheet
        plant_found = any("2___plant" in n and n.endswith(".xlsx") for n in names)
        gen_found = any("3_1_generator" in n and n.endswith(".xlsx") for n in names)
        if not plant_found:
            raise ValueError(f"Plant worksheet not found in EIA-860 ZIP (year={self.year})")
        if not gen_found:
            raise ValueError(f"Generator worksheet not found in EIA-860 ZIP (year={self.year})")
        self._log(f"Validation passed — EIA-860 {self.year} ZIP looks good.")

    def load(self) -> None:
        """Parse Plant + Generator sheets and upsert eia_power_plants."""
        import openpyxl

        from plinth.db.connection import get_connection

        with zipfile.ZipFile(self._zip_path) as zf:
            plant_file = self._find_member(zf, "2___plant")
            gen_file = self._find_member(zf, "3_1_generator")

            self._log(f"  Reading plant sheet: {plant_file}")
            plants = self._parse_plant_sheet(
                openpyxl.load_workbook(io.BytesIO(zf.read(plant_file)), read_only=True, data_only=True)
            )
            self._log(f"  Read {len(plants):,} plants.")

            self._log(f"  Reading generator sheet: {gen_file}")
            gen_rows = self._parse_generator_sheet(
                openpyxl.load_workbook(io.BytesIO(zf.read(gen_file)), read_only=True, data_only=True)
            )
            self._log(f"  Read {len(gen_rows):,} generator rows.")

        # Aggregate generators to plant level
        plant_capacity = self._aggregate_generators(plants, gen_rows)
        self._log(f"  Aggregated to {len(plant_capacity):,} plants with capacity data.")

        rows = list(plant_capacity.values())
        self._log(f"Upserting {len(rows):,} rows into eia_power_plants…")

        with get_connection() as conn:
            with conn.cursor() as cur:
                import json
                for row in rows:
                    cur.execute(
                        """
                        INSERT INTO eia_power_plants
                            (plant_id, plant_name, utility_id, utility_name,
                             operator_name, state, county, geom, data_year,
                             capacity_mw_total, capacity_mw_by_fuel,
                             primary_fuel, technology_types, operating_status)
                        VALUES (
                            %(plant_id)s, %(plant_name)s, %(utility_id)s, %(utility_name)s,
                            %(operator_name)s, %(state)s, %(county)s,
                            CASE WHEN %(lat)s::double precision IS NOT NULL
                                      AND %(lon)s::double precision IS NOT NULL
                                 THEN ST_SetSRID(ST_MakePoint(
                                          %(lon)s::double precision,
                                          %(lat)s::double precision), 4326)
                                 ELSE NULL END,
                            %(data_year)s,
                            %(capacity_mw_total)s, %(capacity_mw_by_fuel)s,
                            %(primary_fuel)s, %(technology_types)s, %(operating_status)s
                        )
                        ON CONFLICT (plant_id) DO UPDATE SET
                            plant_name         = EXCLUDED.plant_name,
                            utility_id         = EXCLUDED.utility_id,
                            utility_name       = EXCLUDED.utility_name,
                            operator_name      = EXCLUDED.operator_name,
                            state              = EXCLUDED.state,
                            county             = EXCLUDED.county,
                            geom               = EXCLUDED.geom,
                            data_year          = EXCLUDED.data_year,
                            capacity_mw_total  = EXCLUDED.capacity_mw_total,
                            capacity_mw_by_fuel = EXCLUDED.capacity_mw_by_fuel,
                            primary_fuel       = EXCLUDED.primary_fuel,
                            technology_types   = EXCLUDED.technology_types,
                            operating_status   = EXCLUDED.operating_status,
                            updated_at         = now()
                        """,
                        {
                            **row,
                            "capacity_mw_by_fuel": json.dumps(row["capacity_mw_by_fuel"]),
                        },
                    )
            conn.commit()
        self._log(f"  Upserted {len(rows):,} plants.")

    def register(self) -> None:
        self._upsert_registry(
            version=str(self.year),
            coverage_region="national",
            notes=f"EIA Form 860 Annual Electric Generator Report, {self.year} data year.",
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _find_member(self, zf: zipfile.ZipFile, prefix: str) -> str:
        """Return first ZIP member whose lowercase name contains prefix + .xlsx."""
        for name in zf.namelist():
            if prefix in name.lower() and name.lower().endswith(".xlsx"):
                return name
        raise ValueError(f"No member matching '{prefix}*.xlsx' in ZIP")

    def _parse_plant_sheet(self, wb) -> dict[int, dict]:
        """Return dict keyed by plant_id with location + metadata."""
        ws = wb.active
        rows = iter(ws.rows)

        # Skip rows until we find the header row (contains "Plant Code")
        header = None
        for row in rows:
            vals = [str(c.value or "").strip() for c in row]
            if "Plant Code" in vals:
                header = vals
                break
        if header is None:
            raise ValueError("Cannot find header row in plant sheet")

        header_set = set(header)

        def idx(name: str) -> Optional[int]:
            try:
                return header.index(name)
            except ValueError:
                return None

        plants: dict[int, dict] = {}
        for row in rows:
            vals = [c.value for c in row]
            try:
                plant_id = int(vals[idx("Plant Code")])
            except (TypeError, ValueError, TypeError):
                continue

            def _f(col: str) -> Optional[float]:
                i = idx(col)
                if i is None or i >= len(vals):
                    return None
                try:
                    return float(vals[i])
                except (TypeError, ValueError):
                    return None

            def _s(col: str) -> Optional[str]:
                i = idx(col)
                if i is None or i >= len(vals):
                    return None
                v = vals[i]
                return str(v).strip() if v is not None else None

            def _i(col: str) -> Optional[int]:
                i = idx(col)
                if i is None or i >= len(vals):
                    return None
                try:
                    return int(vals[i])
                except (TypeError, ValueError):
                    return None

            plants[plant_id] = {
                "plant_id": plant_id,
                "plant_name": _s("Plant Name") or f"Plant {plant_id}",
                "utility_id": _i("Utility ID"),
                "utility_name": _s("Utility Name"),
                "operator_name": _s("Operator Name"),  # not present in all years; OK if None
                "state": _s("State"),
                "county": _s("County"),
                "lat": _f("Latitude"),
                "lon": _f("Longitude"),
                "data_year": self.year,
                "capacity_mw_total": None,
                "capacity_mw_by_fuel": {},
                "primary_fuel": None,
                "technology_types": [],
                "operating_status": None,
            }
        return plants

    def _parse_generator_sheet(self, wb) -> list[dict]:
        """Return list of generator rows with plant_id, fuel, technology, MW, status."""
        ws = wb.active
        rows = iter(ws.rows)

        header = None
        for row in rows:
            vals = [str(c.value or "").strip() for c in row]
            if "Plant Code" in vals:
                header = vals
                break
        if header is None:
            raise ValueError("Cannot find header row in generator sheet")

        def idx(name: str) -> Optional[int]:
            try:
                return header.index(name)
            except ValueError:
                return None

        gen_rows = []
        for row in rows:
            vals = [c.value for c in row]
            try:
                plant_id = int(vals[idx("Plant Code")])
            except (TypeError, ValueError):
                continue

            def _f(col: str) -> Optional[float]:
                i = idx(col)
                if i is None:
                    return None
                try:
                    return float(vals[i])
                except (TypeError, ValueError):
                    return None

            def _s(col: str) -> Optional[str]:
                i = idx(col)
                if i is None:
                    return None
                v = vals[i]
                return str(v).strip() if v is not None else None

            gen_rows.append({
                "plant_id": plant_id,
                "energy_source_1": _s("Energy Source 1") or "",
                "technology": _s("Technology") or "",
                "nameplate_mw": _f("Nameplate Capacity (MW)") or 0.0,
                "status": _s("Status") or "",
            })
        return gen_rows

    def _aggregate_generators(
        self, plants: dict[int, dict], gen_rows: list[dict]
    ) -> dict[int, dict]:
        """Merge generator data into plants dict in-place and return it."""
        from collections import defaultdict

        for g in gen_rows:
            pid = g["plant_id"]
            if pid not in plants:
                continue
            p = plants[pid]
            fuel = g["energy_source_1"] or "OTH"
            mw = g["nameplate_mw"] or 0.0
            tech = g["technology"]
            status = g["status"]

            # Accumulate capacity by fuel
            p["capacity_mw_by_fuel"][fuel] = (
                p["capacity_mw_by_fuel"].get(fuel, 0.0) + mw
            )
            # Collect technology types
            if tech and tech not in p["technology_types"]:
                p["technology_types"].append(tech)
            # Use the first status seen (plant-level status)
            if p["operating_status"] is None:
                p["operating_status"] = status

        for p in plants.values():
            if p["capacity_mw_by_fuel"]:
                p["capacity_mw_total"] = sum(p["capacity_mw_by_fuel"].values())
                p["primary_fuel"] = max(
                    p["capacity_mw_by_fuel"], key=p["capacity_mw_by_fuel"].get
                )

        return plants
