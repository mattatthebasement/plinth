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

# Source CSV column → output array name (all available MLY- data columns)
_ARRAY_COLS = {
    # Temperature normals
    "MLY-TAVG-NORMAL":          "tavg",
    "MLY-TMAX-NORMAL":          "tmax",
    "MLY-TMIN-NORMAL":          "tmin",
    # Temperature standard deviations & diurnal range
    "MLY-TAVG-STDDEV":          "tavg_stddev",
    "MLY-TMAX-STDDEV":          "tmax_stddev",
    "MLY-TMIN-STDDEV":          "tmin_stddev",
    "MLY-DUTR-NORMAL":          "dutr",
    "MLY-DUTR-STDDEV":          "dutr_stddev",
    # Days tmax above thresholds
    "MLY-TMAX-AVGNDS-GRTH032":  "tmax_days_gt32",
    "MLY-TMAX-AVGNDS-GRTH040":  "tmax_days_gt40",
    "MLY-TMAX-AVGNDS-GRTH050":  "tmax_days_gt50",
    "MLY-TMAX-AVGNDS-GRTH060":  "tmax_days_gt60",
    "MLY-TMAX-AVGNDS-GRTH070":  "tmax_days_gt70",
    "MLY-TMAX-AVGNDS-GRTH080":  "tmax_days_gt80",
    "MLY-TMAX-AVGNDS-GRTH090":  "tmax_days_gt90",
    "MLY-TMAX-AVGNDS-GRTH100":  "tmax_days_gt100",
    "MLY-TMAX-AVGNDS-LSTH032":  "tmax_days_lt32",
    # Days tmin below thresholds
    "MLY-TMIN-AVGNDS-LSTH000":  "tmin_days_lt0",
    "MLY-TMIN-AVGNDS-LSTH010":  "tmin_days_lt10",
    "MLY-TMIN-AVGNDS-LSTH020":  "tmin_days_lt20",
    "MLY-TMIN-AVGNDS-LSTH032":  "tmin_days_lt32",
    "MLY-TMIN-AVGNDS-LSTH040":  "tmin_days_lt40",
    "MLY-TMIN-AVGNDS-LSTH050":  "tmin_days_lt50",
    "MLY-TMIN-AVGNDS-LSTH060":  "tmin_days_lt60",
    "MLY-TMIN-AVGNDS-LSTH070":  "tmin_days_lt70",
    # Frost probability (probability tmin falls below threshold in a given month)
    "MLY-TMIN-PRBOCC-LSTH016":  "tmin_prob_lt16",
    "MLY-TMIN-PRBOCC-LSTH020":  "tmin_prob_lt20",
    "MLY-TMIN-PRBOCC-LSTH024":  "tmin_prob_lt24",
    "MLY-TMIN-PRBOCC-LSTH028":  "tmin_prob_lt28",
    "MLY-TMIN-PRBOCC-LSTH032":  "tmin_prob_lt32",
    "MLY-TMIN-PRBOCC-LSTH036":  "tmin_prob_lt36",
    # Heating degree days (base 65°F is htdd; alternatives below)
    "MLY-HTDD-NORMAL":          "htdd",
    "MLY-HTDD-BASE40":          "htdd_base40",
    "MLY-HTDD-BASE45":          "htdd_base45",
    "MLY-HTDD-BASE50":          "htdd_base50",
    "MLY-HTDD-BASE55":          "htdd_base55",
    "MLY-HTDD-BASE57":          "htdd_base57",
    "MLY-HTDD-BASE60":          "htdd_base60",
    # Cooling degree days (base 65°F is cldd; alternatives below)
    "MLY-CLDD-NORMAL":          "cldd",
    "MLY-CLDD-BASE40":          "cldd_base40",
    "MLY-CLDD-BASE45":          "cldd_base45",
    "MLY-CLDD-BASE50":          "cldd_base50",
    "MLY-CLDD-BASE55":          "cldd_base55",
    "MLY-CLDD-BASE57":          "cldd_base57",
    "MLY-CLDD-BASE60":          "cldd_base60",
    "MLY-CLDD-BASE70":          "cldd_base70",
    "MLY-CLDD-BASE72":          "cldd_base72",
    # Growing degree days
    "MLY-GRDD-BASE40":          "grdd_base40",
    "MLY-GRDD-BASE45":          "grdd_base45",
    "MLY-GRDD-BASE50":          "grdd_base50",
    "MLY-GRDD-BASE55":          "grdd_base55",
    "MLY-GRDD-BASE57":          "grdd_base57",
    "MLY-GRDD-BASE60":          "grdd_base60",
    "MLY-GRDD-BASE65":          "grdd_base65",
    "MLY-GRDD-BASE70":          "grdd_base70",
    "MLY-GRDD-BASE72":          "grdd_base72",
    "MLY-GRDD-TB4886":          "grdd_tb4886",   # corn GDD (base 48°F, cap 86°F)
    "MLY-GRDD-TB5086":          "grdd_tb5086",   # soybean GDD (base 50°F, cap 86°F)
    # Precipitation percentiles
    "MLY-PRCP-NORMAL":          "prcp",
    "MLY-PRCP-20PCTL":          "prcp_20pctl",
    "MLY-PRCP-25PCTL":          "prcp_25pctl",
    "MLY-PRCP-33PCTL":          "prcp_33pctl",
    "MLY-PRCP-40PCTL":          "prcp_40pctl",
    "MLY-PRCP-50PCTL":          "prcp_50pctl",
    "MLY-PRCP-60PCTL":          "prcp_60pctl",
    "MLY-PRCP-67PCTL":          "prcp_67pctl",
    "MLY-PRCP-75PCTL":          "prcp_75pctl",
    "MLY-PRCP-80PCTL":          "prcp_80pctl",
    # Precipitation threshold days
    "MLY-PRCP-AVGNDS-GE001HI":  "prcp_days_ge001",
    "MLY-PRCP-AVGNDS-GE010HI":  "prcp_days_ge010",
    "MLY-PRCP-AVGNDS-GE025HI":  "prcp_days_ge025",
    "MLY-PRCP-AVGNDS-GE050HI":  "prcp_days_ge050",
    "MLY-PRCP-AVGNDS-GE100HI":  "prcp_days_ge100",
    "MLY-PRCP-AVGNDS-GE200HI":  "prcp_days_ge200",
    "MLY-PRCP-AVGNDS-GE400HI":  "prcp_days_ge400",
    "MLY-PRCP-AVGNDS-GE600HI":  "prcp_days_ge600",
    # Snowfall percentiles
    "MLY-SNOW-NORMAL":          "snow",
    "MLY-SNOW-20PCTL":          "snow_20pctl",
    "MLY-SNOW-25PCTL":          "snow_25pctl",
    "MLY-SNOW-33PCTL":          "snow_33pctl",
    "MLY-SNOW-40PCTL":          "snow_40pctl",
    "MLY-SNOW-50PCTL":          "snow_50pctl",
    "MLY-SNOW-60PCTL":          "snow_60pctl",
    "MLY-SNOW-67PCTL":          "snow_67pctl",
    "MLY-SNOW-75PCTL":          "snow_75pctl",
    "MLY-SNOW-80PCTL":          "snow_80pctl",
    # Snowfall threshold days
    "MLY-SNOW-AVGNDS-GE001TI":  "snow_days_ge001",
    "MLY-SNOW-AVGNDS-GE010TI":  "snow_days_ge010",
    "MLY-SNOW-AVGNDS-GE020TI":  "snow_days_ge020",
    "MLY-SNOW-AVGNDS-GE030TI":  "snow_days_ge030",
    "MLY-SNOW-AVGNDS-GE040TI":  "snow_days_ge040",
    "MLY-SNOW-AVGNDS-GE050TI":  "snow_days_ge050",
    "MLY-SNOW-AVGNDS-GE100TI":  "snow_days_ge100",
    "MLY-SNOW-AVGNDS-GE200TI":  "snow_days_ge200",
    # Snow depth threshold days
    "MLY-SNWD-AVGNDS-GE001WI":  "snwd_days_ge001",
    "MLY-SNWD-AVGNDS-GE002WI":  "snwd_days_ge002",
    "MLY-SNWD-AVGNDS-GE003WI":  "snwd_days_ge003",
    "MLY-SNWD-AVGNDS-GE004WI":  "snwd_days_ge004",
    "MLY-SNWD-AVGNDS-GE005WI":  "snwd_days_ge005",
    "MLY-SNWD-AVGNDS-GE010WI":  "snwd_days_ge010",
    "MLY-SNWD-AVGNDS-GE020WI":  "snwd_days_ge020",
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

        # Build SQL dynamically so all columns in _ARRAY_COLS are included
        arr_cols = list(_ARRAY_COLS.values())
        meta_cols = ["station_id", "name", "elevation_m", "geom"]
        all_cols = meta_cols + arr_cols

        col_list = ", ".join(all_cols)
        val_list = (
            "%(station_id)s, %(name)s, %(elevation_m)s, "
            "ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326), "
            + ", ".join(f"%({c})s" for c in arr_cols)
        )
        update_set = ", ".join(
            f"{c} = EXCLUDED.{c}"
            for c in ["name", "elevation_m", "geom"] + arr_cols
        )
        upsert_sql = (
            f"INSERT INTO noaa_climate_normals ({col_list}) "
            f"VALUES ({val_list}) "
            f"ON CONFLICT (station_id) DO UPDATE SET {update_set}"
        )

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.executemany(upsert_sql, stations)
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
