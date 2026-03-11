"""USGS ComCat earthquake catalog bulk ingestor.

Fetches all M≥2.0 earthquake events within the NE Oklahoma coverage
bounding box + 1° buffer from the USGS FDSN event API. Stores in
usgs_earthquake_events. Total regional catalog is ~13k events (well
under the 20k FDSN single-response limit), so a single request suffices.

Source: https://earthquake.usgs.gov/fdsnws/event/1/
Coverage: All available dates back to 1918
"""

from __future__ import annotations

import csv
import io
from datetime import date, timedelta
from pathlib import Path

from plinth.ingest.base import BaseIngestor

_FDSN_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query"
_DATASET = "usgs-earthquakes-bulk"

# NE Oklahoma bbox + 1° buffer
_DEFAULT_BBOX = {
    "lat_min": 34.0,
    "lat_max": 38.5,
    "lon_min": -98.5,
    "lon_max": -93.0,
}

_MIN_MAGNITUDE = 2.0
_CACHE_DAYS = 1  # Re-download if staging file is older than this many days
_BATCH_SIZE = 2000


def _floatnull(val: str | None) -> float | None:
    if not val or not val.strip():
        return None
    try:
        return float(val.strip())
    except ValueError:
        return None


def _intnull(val: str | None) -> int | None:
    if not val or not val.strip():
        return None
    try:
        return int(float(val.strip()))
    except ValueError:
        return None


class UsgsEarthquakesBulkIngestor(BaseIngestor):
    """Ingestor for USGS ComCat earthquake events via FDSN event API.

    Fetches all M≥2.0 events within the coverage bbox in a single request.
    Staging file is refreshed daily. Uses ON CONFLICT to handle re-runs
    and incremental updates idempotently.
    """

    source_name = _DATASET
    update_frequency = "annual"

    def __init__(
        self,
        bbox: dict | None = None,
        min_magnitude: float = _MIN_MAGNITUDE,
    ) -> None:
        super().__init__()
        self.bbox = bbox or _DEFAULT_BBOX
        self.min_magnitude = min_magnitude
        self._staging_file = self.staging_dir / "usgs_earthquakes.csv"

    # ------------------------------------------------------------------
    # Pipeline steps
    # ------------------------------------------------------------------

    def download(self, region=None) -> None:
        import httpx

        # Re-download if file is missing or older than CACHE_DAYS
        if self._staging_file.exists():
            age_days = (date.today() - date.fromtimestamp(self._staging_file.stat().st_mtime)).days
            if age_days < _CACHE_DAYS:
                size = self._staging_file.stat().st_size
                self._log(f"Skipped download (cached {age_days}d old, {size:,} bytes)")
                return

        self._log("Fetching all events from USGS FDSN...")
        params = {
            "format": "csv",
            "minlatitude": self.bbox["lat_min"],
            "maxlatitude": self.bbox["lat_max"],
            "minlongitude": self.bbox["lon_min"],
            "maxlongitude": self.bbox["lon_max"],
            "minmagnitude": self.min_magnitude,
            "starttime": "1900-01-01",
            "endtime": date.today().isoformat(),
            "orderby": "time-asc",
            "limit": 20000,
        }
        resp = httpx.get(_FDSN_URL, params=params, timeout=120, follow_redirects=True)
        resp.raise_for_status()
        self._staging_file.write_text(resp.text, encoding="utf-8")
        rows = resp.text.count("\n") - 1
        size = self._staging_file.stat().st_size
        self._log(f"Downloaded {rows:,} events ({size:,} bytes)")

    def validate(self) -> None:
        if not self._staging_file.exists():
            raise FileNotFoundError(f"Missing staging file: {self._staging_file}")
        text = self._staging_file.read_text(encoding="utf-8")
        first_line = text.split("\n", 1)[0]
        if "time" not in first_line or "mag" not in first_line:
            raise ValueError(f"Unexpected CSV header: {first_line[:100]}")
        rows = text.count("\n") - 1
        self._log(f"Validated {rows:,} event rows")

    def load(self) -> None:
        from plinth.db.connection import get_connection

        text = self._staging_file.read_text(encoding="utf-8")
        reader = csv.DictReader(io.StringIO(text))

        with get_connection() as conn:
            batch: list[dict] = []
            total = 0

            for row in reader:
                event_id = row.get("id", "").strip()
                if not event_id:
                    continue
                lat = _floatnull(row.get("latitude"))
                lon = _floatnull(row.get("longitude"))
                batch.append({
                    "event_id": event_id,
                    "occurred_at": row.get("time", "").strip() or None,
                    "magnitude": _floatnull(row.get("mag")),
                    "magnitude_type": row.get("magType", "").strip() or None,
                    "depth_km": _floatnull(row.get("depth")),
                    "place": row.get("place", "").strip() or None,
                    "status": row.get("status", "").strip() or None,
                    "gap": _floatnull(row.get("gap")),
                    "rms": _floatnull(row.get("rms")),
                    "nst": _intnull(row.get("nst")),
                    "url": f"https://earthquake.usgs.gov/earthquakes/eventpage/{event_id}",
                    "lat": lat,
                    "lon": lon,
                })

                if len(batch) >= _BATCH_SIZE:
                    _flush_batch(conn, batch)
                    total += len(batch)
                    batch = []

            if batch:
                _flush_batch(conn, batch)
                total += len(batch)

        self._log(f"Upserted {total:,} earthquake events")

    def register(self) -> None:
        bbox = self.bbox
        region = (
            f"lat {bbox['lat_min']}–{bbox['lat_max']}°N, "
            f"lon {bbox['lon_min']}–{bbox['lon_max']}°W, "
            f"M≥{self.min_magnitude}"
        )
        self._upsert_registry(
            version=f"USGS ComCat through {date.today().isoformat()}",
            coverage_region=region,
            notes=(
                "USGS FDSN event API — all M≥2.0 events in NE Oklahoma +1° buffer. "
                "Full catalog from 1900. Refreshed on ingest run."
            ),
        )


def _flush_batch(conn, batch: list[dict]) -> None:
    """Upsert a batch of earthquake events."""
    cols = [
        "event_id", "occurred_at", "magnitude", "magnitude_type",
        "depth_km", "place", "status", "gap", "rms", "nst", "url", "geom",
    ]
    ncols = len(cols)
    safe_batch = max(1, 65535 // ncols)
    update_set = ", ".join(
        f"{c} = EXCLUDED.{c}"
        for c in cols if c != "event_id"
    )

    for i in range(0, len(batch), safe_batch):
        chunk = batch[i : i + safe_batch]
        row_ph = (
            "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
            "CASE WHEN %s IS NOT NULL AND %s IS NOT NULL "
            "THEN ST_SetSRID(ST_MakePoint(%s, %s), 4326) ELSE NULL END)"
        )
        placeholders = ", ".join(row_ph for _ in chunk)
        flat: list = []
        for r in chunk:
            flat += [
                r["event_id"], r["occurred_at"], r["magnitude"],
                r["magnitude_type"], r["depth_km"], r["place"],
                r["status"], r["gap"], r["rms"], r["nst"], r["url"],
                # geom CASE (lon, lat × 2)
                r["lon"], r["lat"], r["lon"], r["lat"],
            ]
        sql = (
            f"INSERT INTO usgs_earthquake_events ({', '.join(cols)}) "
            f"VALUES {placeholders} "
            f"ON CONFLICT (event_id) DO UPDATE SET {update_set}"
        )
        with conn.cursor() as cur:
            cur.execute(sql, flat)
    conn.commit()
