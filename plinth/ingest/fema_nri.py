"""FEMA National Risk Index (NRI) ingestor — tract-level ArcGIS FeatureServer."""

import json
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode
from urllib.request import urlopen

from plinth.ingest.base import BaseIngestor

_BASE_URL = (
    "https://services.arcgis.com/XG15cJAlne2vxtgt/arcgis/rest/services"
    "/National_Risk_Index_Census_Tracts/FeatureServer/0"
)

# Hazard risk score fields in NRI v1.20 (per-hazard {HAZARD}_RISKS).
# RFLD (riverine flooding) was removed in v1.20; we store NULL for rfld_score.
_HAZARD_API_FIELDS: list[tuple[str, str]] = [
    ("AVLN_RISKS", "avln_score"),
    ("CFLD_RISKS", "cfld_score"),
    ("CWAV_RISKS", "cwav_score"),
    ("DRGT_RISKS", "drgt_score"),
    ("ERQK_RISKS", "erqk_score"),
    ("HAIL_RISKS", "hail_score"),
    ("HWAV_RISKS", "hwav_score"),
    ("HRCN_RISKS", "hrcn_score"),
    ("ISTM_RISKS", "istm_score"),
    ("LNDS_RISKS", "lnds_score"),
    ("LTNG_RISKS", "ltng_score"),
    ("SWND_RISKS", "swnd_score"),
    ("TRND_RISKS", "trnd_score"),
    ("TSUN_RISKS", "tsun_score"),
    ("VLCN_RISKS", "vlcn_score"),
    ("WFIR_RISKS", "wfir_score"),
    ("WNTW_RISKS", "wntw_score"),
]

_OUT_FIELDS = ",".join(
    ["TRACTFIPS", "STCOFIPS", "RISK_SCORE", "RISK_RATNG"]
    + [api for api, _ in _HAZARD_API_FIELDS]
)

_PAGE_SIZE = 2000
_BATCH_SIZE = 500

# Maps region name prefix → state FIPS string
_REGION_STATE_FIPS: dict[str, str] = {
    "ne-oklahoma": "40",
    "oklahoma": "40",
}


class FemaNriIngestor(BaseIngestor):
    """Download and load FEMA National Risk Index tract-level data.

    Fetches from the official FEMA ArcGIS FeatureServer, filtered by state.

    IMPORTANT: All report output using this data MUST be labeled
    "Source: FEMA National Risk Index".
    """

    source_name = "fema-nri"
    update_frequency = "annual"

    def download(self, region: Optional[str] = None) -> None:
        """Fetch NRI features from FEMA FeatureServer for the target state."""
        state_fips = self._state_fips(region)
        cache_path = self.staging_dir / f"nri_{state_fips}.json"

        if self._is_fresh(cache_path, ttl_days=30):
            self._log(f"NRI data for state {state_fips} is up-to-date.")
            return

        self._log(f"Fetching NRI tracts for state FIPS {state_fips}…")
        features = self._paginate_features(state_fips)
        self._log(f"  Fetched {len(features)} NRI tracts.")

        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(features))

    def validate(self) -> None:
        """Verify cached features exist and contain required fields."""
        state_fips = self._state_fips(self._region)
        cache_path = self.staging_dir / f"nri_{state_fips}.json"

        if not cache_path.exists():
            raise ValueError(
                f"NRI cache file not found: {cache_path}. Run download() first."
            )

        features = json.loads(cache_path.read_text())
        if not features:
            raise ValueError("NRI cache is empty — check FEMA API response.")

        sample = features[0]
        for required in ("TRACTFIPS", "RISK_SCORE", "RISK_RATNG"):
            if required not in sample:
                raise ValueError(f"Required field {required!r} missing from NRI data.")

        self._log(f"Validated: {len(features)} NRI tracts.")

    def load(self) -> None:
        """Upsert NRI rows into fema_nri, joining geometry from census_tracts."""
        state_fips = self._state_fips(self._region)
        cache_path = self.staging_dir / f"nri_{state_fips}.json"
        features = json.loads(cache_path.read_text())

        from plinth.db.connection import get_connection

        self._log(f"Loading {len(features)} NRI tracts into fema_nri…")
        total = 0
        batch: list[tuple] = []

        with get_connection() as conn:
            for attrs in features:
                tract_id = (attrs.get("TRACTFIPS") or "").strip()
                if not tract_id:
                    continue

                params = (
                    tract_id,
                    tract_id[:5],
                    attrs.get("RISK_SCORE"),
                    attrs.get("RISK_RATNG") or None,
                    *[attrs.get(api) for api, _ in _HAZARD_API_FIELDS],
                    None,  # rfld_score — removed in NRI v1.20
                    tract_id,
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

    def _paginate_features(self, state_fips: str) -> list[dict]:
        """Page through the FeatureServer and return a flat list of attribute dicts."""
        features: list[dict] = []
        offset = 0

        while True:
            params = urlencode({
                "where": f"STATEFIPS='{state_fips}'",
                "outFields": _OUT_FIELDS,
                "returnGeometry": "false",
                "resultOffset": offset,
                "resultRecordCount": _PAGE_SIZE,
                "f": "json",
            })
            url = f"{_BASE_URL}/query?{params}"
            with urlopen(url, timeout=60) as resp:
                data = json.loads(resp.read())

            page = [f["attributes"] for f in data.get("features", [])]
            features.extend(page)

            if not data.get("exceededTransferLimit"):
                break
            offset += len(page)

        return features

    def _execute_batch(self, conn, batch: list[tuple]) -> None:
        upsert_sql = """
            INSERT INTO fema_nri (
                tract_id, county_fips, risk_score, risk_ratng,
                avln_score, cfld_score, cwav_score, drgt_score, erqk_score,
                hail_score, hwav_score, hrcn_score, istm_score, lnds_score,
                ltng_score, swnd_score, trnd_score, tsun_score,
                vlcn_score, wfir_score, wntw_score,
                rfld_score,
                geom
            )
            VALUES (
                %s, %s, %s::numeric, %s,
                %s::numeric, %s::numeric, %s::numeric, %s::numeric, %s::numeric,
                %s::numeric, %s::numeric, %s::numeric, %s::numeric, %s::numeric,
                %s::numeric, %s::numeric, %s::numeric, %s::numeric,
                %s::numeric, %s::numeric, %s::numeric,
                %s::numeric,
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
                swnd_score  = EXCLUDED.swnd_score,
                trnd_score  = EXCLUDED.trnd_score,
                tsun_score  = EXCLUDED.tsun_score,
                vlcn_score  = EXCLUDED.vlcn_score,
                wfir_score  = EXCLUDED.wfir_score,
                wntw_score  = EXCLUDED.wntw_score,
                rfld_score  = EXCLUDED.rfld_score,
                geom        = EXCLUDED.geom
        """
        with conn.cursor() as cur:
            cur.executemany(upsert_sql, batch)
        conn.commit()

    def _state_fips(self, region: Optional[str]) -> str:
        """Resolve region name to a state FIPS string."""
        if region:
            for key, fips in _REGION_STATE_FIPS.items():
                if region.lower().startswith(key):
                    return fips
        return "40"  # default to Oklahoma

    def _is_fresh(self, path: Path, ttl_days: int = 30) -> bool:
        """Return True if path exists and was modified within ttl_days."""
        if not path.exists():
            return False
        import datetime
        age = datetime.datetime.now() - datetime.datetime.fromtimestamp(path.stat().st_mtime)
        return age.days < ttl_days

    def register(self) -> None:
        """Register this source in data_source_registry."""
        import datetime

        self._upsert_registry(
            version=datetime.date.today().isoformat(),
            coverage_region="oklahoma",
            notes=(
                "Source: FEMA National Risk Index. "
                "This label is REQUIRED on all report output. "
                "Tract-level composite risk scores joined to census_tracts geometry."
            ),
        )
