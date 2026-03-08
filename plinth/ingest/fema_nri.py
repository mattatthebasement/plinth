"""FEMA National Risk Index (NRI) ingestor — tract-level CSV."""

import csv
import zipfile
from pathlib import Path
from typing import Optional

from plinth.ingest.base import BaseIngestor

NRI_URL = (
    "https://hazards.fema.gov/nri/Content/StaticDocuments/DataDownload/"
    "NRI_Table_CensusTracts/NRI_Table_CensusTracts.zip"
)

# Ordered list of hazard score column names in the NRI CSV
_HAZARD_COLS = [
    "AVLN_SCORE",
    "CFLD_SCORE",
    "CWAV_SCORE",
    "DRGT_SCORE",
    "ERQK_SCORE",
    "HAIL_SCORE",
    "HWAV_SCORE",
    "HRCN_SCORE",
    "ISTM_SCORE",
    "LNDS_SCORE",
    "LTNG_SCORE",
    "RFLD_SCORE",
    "SWND_SCORE",
    "TRND_SCORE",
    "TSUN_SCORE",
    "VLCN_SCORE",
    "WFIR_SCORE",
    "WNTW_SCORE",
]

_BATCH_SIZE = 500


def _safe_numeric(value: str) -> Optional[float]:
    """Convert a CSV string to float, returning None for blank/non-numeric."""
    v = value.strip()
    if not v:
        return None
    try:
        return float(v)
    except ValueError:
        return None


class FemaNriIngestor(BaseIngestor):
    """Download and load FEMA National Risk Index tract-level data.

    The NRI CSV is joined to ``census_tracts`` geometry at load time.

    IMPORTANT: All report output using this data MUST be labeled
    "Source: FEMA National Risk Index".
    """

    source_name = "fema-nri"
    update_frequency = "annual"

    def download(self, region: Optional[str] = None) -> None:
        """Download the NRI tract CSV zip if changed."""
        dest = self.staging_dir / "NRI_Table_CensusTracts.zip"
        unzip_dir = self.staging_dir / "nri"

        fresh = self._download_if_changed(NRI_URL, dest)

        if fresh or not unzip_dir.exists():
            self._log("Unzipping NRI data…")
            unzip_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(dest) as zf:
                zf.extractall(unzip_dir)

    def validate(self) -> None:
        """Verify the CSV exists, has > 50,000 rows, and has required columns."""
        csv_path = self._find_csv()
        if csv_path is None:
            raise ValueError(
                f"No CSV file found under {self.staging_dir / 'nri'}. "
                "Check that the zip downloaded correctly."
            )

        with csv_path.open(newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            headers = reader.fieldnames or []
            headers_upper = [h.upper() for h in headers]

            # Determine tract ID column
            tract_col = None
            for candidate in ("TRACTFIPS", "GEOID", "TRACT_FIPS"):
                if candidate in headers_upper:
                    tract_col = candidate
                    break
            if tract_col is None:
                raise ValueError(
                    f"Required tract ID column not found. Available: {headers[:20]}"
                )

            for required in ("RISK_SCORE", "RISK_RATNG"):
                if required not in headers_upper:
                    raise ValueError(
                        f"Required column {required!r} not found in NRI CSV."
                    )

            row_count = sum(1 for _ in reader)

        if row_count < 50_000:
            raise ValueError(
                f"NRI CSV has only {row_count} rows — expected > 50,000 for national dataset."
            )
        self._log(f"Validated: {row_count} rows, tract column: {tract_col!r}")

    def load(self) -> None:
        """Upsert NRI rows into fema_nri, joining geometry from census_tracts."""
        csv_path = self._find_csv()
        if csv_path is None:
            raise RuntimeError("CSV not found — run download() first.")

        from plinth.db.connection import get_connection

        self._log("Loading NRI CSV into fema_nri…")
        total = 0

        with csv_path.open(newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            # Normalize header names to upper-case for lookup
            headers_upper = {h.upper(): h for h in (reader.fieldnames or [])}

            tract_key = next(
                (k for k in ("TRACTFIPS", "GEOID", "TRACT_FIPS") if k in headers_upper),
                None,
            )
            if tract_key is None:
                raise RuntimeError("Tract ID column not found in CSV.")

            def _col(name: str) -> str:
                """Return the original header name for a normalised column name."""
                return headers_upper.get(name, name)

            batch: list[tuple] = []

            with get_connection() as conn:
                for row in reader:
                    tract_id = row.get(_col(tract_key), "").strip()
                    if not tract_id:
                        continue

                    params = (
                        tract_id,
                        tract_id[:5],  # county_fips
                        _safe_numeric(row.get(_col("RISK_SCORE"), "")),
                        row.get(_col("RISK_RATNG"), "").strip() or None,
                        *[
                            _safe_numeric(row.get(_col(h), ""))
                            for h in _HAZARD_COLS
                        ],
                        tract_id,  # for geometry subquery
                    )
                    batch.append(params)

                    if len(batch) >= _BATCH_SIZE:
                        self._execute_batch(conn, batch)
                        total += len(batch)
                        batch = []

                if batch:
                    self._execute_batch(conn, batch)
                    total += len(batch)

        self._log(f"NRI rows upserted: {total}")

    def _execute_batch(self, conn, batch: list[tuple]) -> None:
        upsert_sql = """
            INSERT INTO fema_nri (
                tract_id, county_fips, risk_score, risk_ratng,
                avln_score, cfld_score, cwav_score, drgt_score, erqk_score,
                hail_score, hwav_score, hrcn_score, istm_score, lnds_score,
                ltng_score, rfld_score, swnd_score, trnd_score, tsun_score,
                vlcn_score, wfir_score, wntw_score,
                geom
            )
            VALUES (
                %s, %s, %s::numeric, %s,
                %s::numeric, %s::numeric, %s::numeric, %s::numeric, %s::numeric,
                %s::numeric, %s::numeric, %s::numeric, %s::numeric, %s::numeric,
                %s::numeric, %s::numeric, %s::numeric, %s::numeric, %s::numeric,
                %s::numeric, %s::numeric, %s::numeric,
                (SELECT geom FROM census_tracts WHERE geoid = %s)
            )
            ON CONFLICT (tract_id) DO UPDATE SET
                county_fips = EXCLUDED.county_fips,
                risk_score  = EXCLUDED.risk_score,
                risk_ratng  = EXCLUDED.risk_ratng,
                avln_score  = EXCLUDED.avln_score,
                cfld_score  = EXCLUDED.cfld_score,
                cwav_score  = EXCLUDED.cwav_score,
                drgt_score  = EXCLUDED.drgt_score,
                erqk_score  = EXCLUDED.erqk_score,
                hail_score  = EXCLUDED.hail_score,
                hwav_score  = EXCLUDED.hwav_score,
                hrcn_score  = EXCLUDED.hrcn_score,
                istm_score  = EXCLUDED.istm_score,
                lnds_score  = EXCLUDED.lnds_score,
                ltng_score  = EXCLUDED.ltng_score,
                rfld_score  = EXCLUDED.rfld_score,
                swnd_score  = EXCLUDED.swnd_score,
                trnd_score  = EXCLUDED.trnd_score,
                tsun_score  = EXCLUDED.tsun_score,
                vlcn_score  = EXCLUDED.vlcn_score,
                wfir_score  = EXCLUDED.wfir_score,
                wntw_score  = EXCLUDED.wntw_score,
                geom        = EXCLUDED.geom
        """
        with conn.cursor() as cur:
            cur.executemany(upsert_sql, batch)
        conn.commit()

    def _find_csv(self) -> Optional[Path]:
        """Return the first .csv file inside the nri unzip directory."""
        nri_dir = self.staging_dir / "nri"
        if not nri_dir.exists():
            return None
        for p in nri_dir.rglob("*.csv"):
            return p
        return None

    def register(self) -> None:
        """Register this source in data_source_registry."""
        import datetime

        self._upsert_registry(
            version=datetime.date.today().isoformat(),
            coverage_region="national",
            notes=(
                "Source: FEMA National Risk Index. "
                "This label is REQUIRED on all report output. "
                "Tract-level composite risk scores joined to census_tracts geometry."
            ),
        )
