"""HydroFrame Water Table Depth (WTD) ingestor.

Registers the HydroFrame Ma et al. (2025) modeled water table depth dataset
in the data_source_registry.  Point queries are performed lazily at report
time via the hf_hydrodata Python package and cached permanently to disk
(the dataset is static; it never changes).

Reference
---------
Ma, Y. et al. (2025). A data-driven 30 m resolution water table depth map
for the conterminous United States. Communications Earth & Environment.
DOI: 10.1038/s43247-025-03094-3

Dataset : hf_hydrodata  'ma_2025', variable 'water_table_depth'
Grid    : conus2_wtd.30 (~24 m, Lambert Conformal Conic, CONUS)
License : CC-BY 4.0
Coverage: Full CONUS

Note on storage
---------------
The full CONUS raster is ~140 GB uncompressed (246 K × 144 K × float32).
Bulk download to MinIO is impractical for this dataset.  Instead, point
values are fetched once per unique ~0.05° grid cell via hf_hydrodata and
cached permanently at $STAGING_DIR/hydroframe_cache/<lat>_<lon>.json.
After a location has been queried once, no further API calls are needed.
"""
from __future__ import annotations

from typing import Optional

from plinth.ingest.base import BaseIngestor


class HydroframeWtdIngestor(BaseIngestor):
    """Register HydroFrame WTD in data_source_registry.

    This ingestor performs no bulk download.  See the docstring above for
    the storage rationale.  The actual data access logic lives in
    plinth/query/water_infrastructure.py (_query_hydroframe_wtd).
    """

    source_name = "hydroframe-wtd"
    update_frequency = "decadal"

    def download(self, region: Optional[str] = None) -> None:
        """No bulk download — data is accessed lazily at query time."""
        self._log(
            "HydroFrame WTD: no bulk download. "
            "Point values are fetched on first query and cached permanently to disk."
        )

    def validate(self) -> None:
        """Verify hf_hydrodata is importable and credentials are configured."""
        try:
            import hf_hydrodata  # noqa: F401
        except ImportError as exc:
            raise ValueError(
                "hf_hydrodata package not installed. "
                "Add 'hf_hydrodata>=1.0' to pyproject.toml and run 'uv sync'."
            ) from exc

        from plinth.config import get_settings
        cfg = get_settings()
        if not cfg.hydroframe_username or not cfg.hydroframe_password:
            raise ValueError(
                "HYDROFRAME_USERNAME and HYDROFRAME_PASSWORD must be set in .env. "
                "Register free at: https://hydrogen.princeton.edu/hf_hydrodata/"
            )
        self._log("HydroFrame WTD: hf_hydrodata importable, credentials configured.")

    def load(self) -> None:
        """No load step — data is not bulk-loaded."""
        pass

    def register(self) -> None:
        """Upsert a row in data_source_registry."""
        self._upsert_registry(
            dataset_version="ma_2025",
            coverage_region="national",
            notes=(
                "Ma et al. (2025) 30 m CONUS water table depth model. "
                "CC-BY 4.0. DOI: 10.1038/s43247-025-03094-3. "
                "RMSE ≈ 15 m (49 ft); use for planning context only. "
                "Accessed lazily via hf_hydrodata; cached permanently to disk."
            ),
        )
