"""NOAA 1991-2020 Climate Normals ingestor.

Downloads the NCEI monthly normals bulk archive (~28 MB) and loads station
point data into PostGIS. Monthly values are stored as NUMERIC[12] arrays
(index 1 = January … 12 = December).

Source: https://www.ncei.noaa.gov/data/normals-monthly/1991-2020/archive/
Refresh: Decadal (next update ~2032 for 2001-2030 normals)
"""

import io
import tarfile
from typing import Optional

from plinth.ingest.base import BaseIngestor

_ARCHIVE_URL = (
    "https://www.ncei.noaa.gov/data/normals-monthly/1991-2020/archive/"
    "us-climate-normals_1991-2020_v1.0.1_monthly_multivariate_by-station_c20230404.tar.gz"
)
_ARCHIVE_FILE = "noaa_normals_1991-2020.tar.gz"

# Source CSV column → output array name
_ARRAY_COLS = {
    "MLY-TAVG-NORMAL": "tavg",
    "MLY-TMAX-NORMAL": "tmax",
    "MLY-TMIN-NORMAL": "tmin",
    "MLY-PRCP-NORMAL": "prcp",
    "MLY-SNOW-NORMAL": "snow",
    "MLY-HTDD-NORMAL": "htdd",
    "MLY-CLDD-NORMAL": "cldd",
}

# NOAA sentinel values that mean "missing" or "trace" — store as NULL
_MISSING = {-9999.0, -9999, -7777.0, -7777, -8888.0, -8888}


def _parse_val(s: str) -> Optional[float]:
    """Return float or None for missing/trace NOAA sentinel values."""
    try:
        v = float(s.strip())
        return None if v in _MISSING else v
    except (ValueError, TypeError):
        return None


class NoaaNormalsIngestor(BaseIngestor):
    """Download NCEI 1991-2020 monthly normals archive and load into PostGIS.

    Loads all US stations from the bulk tar.gz. Each CSV has 12 rows (one per
    month); we pivot them into a single row with NUMERIC[12] arrays and upsert
    into ``noaa_climate_normals``.
    """

    source_name = "noaa-normals"
    update_frequency = "decadal"

    def download(self, region: Optional[str] = None) -> None:
        """Download the NCEI monthly normals bulk archive if not current.

        Uses ETag-based caching via _download_if_changed so re-runs do not
        re-download an unchanged archive.
        """
        dest = self.staging_dir / _ARCHIVE_FILE
        self._log("Checking NOAA 1991-2020 monthly normals archive…")
        fetched = self._download_if_changed(_ARCHIVE_URL, dest)
        if not fetched:
            self._log("Archive is up-to-date (ETag matched).")

    def validate(self) -> None:
        """Verify the archive is present and is a valid gzip tar."""
        dest = self.staging_dir / _ARCHIVE_FILE
        if not dest.exists():
            raise ValueError(f"Archive not found: {dest}")
        if dest.stat().st_size < 1_000_000:
            raise ValueError(f"Archive suspiciously small ({dest.stat().st_size} bytes): {dest}")
        try:
            with tarfile.open(dest, "r:gz") as tf:
                names = tf.getnames()
            if len(names) < 100:
                raise ValueError(f"Archive has only {len(names)} members, expected ~15k")
        except tarfile.TarError as exc:
            raise ValueError(f"Invalid tar archive: {exc}") from exc
        self._log(f"Validation passed ({len(names):,} station files in archive).")

    def load(self) -> None:
        """Parse all station CSVs and upsert into noaa_climate_normals."""
        import csv

        from plinth.db.connection import get_connection

        dest = self.staging_dir / _ARCHIVE_FILE
        self._log("Parsing station CSVs from archive…")

        stations: list[dict] = []
        with tarfile.open(dest, "r:gz") as tf:
            for member in tf.getmembers():
                if not member.name.endswith(".csv"):
                    continue
                f = tf.extractfile(member)
                if f is None:
                    continue
                row = self._parse_station_csv(io.TextIOWrapper(f, encoding="utf-8"))
                if row is not None:
                    stations.append(row)

        self._log(f"  Parsed {len(stations):,} stations.")
        self._log("Upserting into noaa_climate_normals…")

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.executemany(
                    """
                    INSERT INTO noaa_climate_normals
                        (station_id, name, elevation_m, geom,
                         tmax, tmin, tavg, prcp, snow, htdd, cldd)
                    VALUES
                        (%(station_id)s, %(name)s, %(elevation_m)s,
                         ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326),
                         %(tmax)s, %(tmin)s, %(tavg)s,
                         %(prcp)s, %(snow)s, %(htdd)s, %(cldd)s)
                    ON CONFLICT (station_id) DO UPDATE SET
                        name        = EXCLUDED.name,
                        elevation_m = EXCLUDED.elevation_m,
                        geom        = EXCLUDED.geom,
                        tmax        = EXCLUDED.tmax,
                        tmin        = EXCLUDED.tmin,
                        tavg        = EXCLUDED.tavg,
                        prcp        = EXCLUDED.prcp,
                        snow        = EXCLUDED.snow,
                        htdd        = EXCLUDED.htdd,
                        cldd        = EXCLUDED.cldd
                    """,
                    stations,
                )
                count = cur.rowcount
            conn.commit()
        self._log(f"  Upserted: {count:,} stations.")

    def _parse_station_csv(self, f) -> Optional[dict]:
        """Parse a 12-row per-station CSV into a single dict for upsert.

        Returns None if the station has no valid lat/lon or too few rows.
        """
        import csv
        reader = csv.DictReader(f)
        monthly: dict[str, list] = {col: [None] * 12 for col in _ARRAY_COLS.values()}
        meta: dict = {}

        for row in reader:
            try:
                month_idx = int(row.get("month", 0)) - 1
            except (ValueError, TypeError):
                continue
            if not (0 <= month_idx <= 11):
                continue

            if not meta:
                try:
                    lat = float(row["LATITUDE"].strip())
                    lon = float(row["LONGITUDE"].strip())
                    elev_raw = row.get("ELEVATION", "").strip()
                    elev = float(elev_raw) if elev_raw else None
                except (ValueError, KeyError):
                    return None
                meta = {
                    "station_id": row.get("STATION", "").strip(),
                    "name": row.get("NAME", "").strip(),
                    "lat": lat,
                    "lon": lon,
                    "elevation_m": elev,
                }

            for src_col, arr_name in _ARRAY_COLS.items():
                monthly[arr_name][month_idx] = _parse_val(row.get(src_col, ""))

        if not meta:
            return None

        return {
            **meta,
            **{k: v for k, v in monthly.items()},
        }

    def register(self) -> None:
        """Register this source in data_source_registry."""
        self._upsert_registry(
            version="1991-2020-v1.0.1",
            coverage_region="national",
            notes="NCEI 1991-2020 Monthly Climate Normals. Decadal dataset.",
        )
