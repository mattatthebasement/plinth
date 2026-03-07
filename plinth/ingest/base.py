import datetime
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional


class BaseIngestor(ABC):
    """Abstract base class for all Plinth data source ingestors.

    Subclasses must define `source_name` and implement the four abstract
    methods.  Call `run()` to execute the full pipeline in order:
    download → validate → load → register.
    """

    source_name: str        # e.g. "fema-nfhl"
    update_frequency: str = "annual"  # 'monthly' | 'annual' | 'decadal'

    def __init__(self) -> None:
        from plinth.config import get_settings

        self.settings = get_settings()
        self.staging_dir = Path(self.settings.staging_dir) / self.source_name
        self.staging_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Pipeline entry point
    # ------------------------------------------------------------------

    def run(self, region: Optional[str] = None) -> None:
        """Execute the full ingest pipeline for the given region."""
        self._log("Downloading...")
        self.download(region)

        self._log("Validating...")
        self.validate()

        self._log("Loading...")
        self.load()

        self._log("Registering...")
        self.register()

        self._log("Done.")

    # ------------------------------------------------------------------
    # Abstract methods — implement in each subclass
    # ------------------------------------------------------------------

    @abstractmethod
    def download(self, region: Optional[str] = None) -> None:
        """Download source data to self.staging_dir.

        Must be idempotent: use ETag / content-hash checks so unchanged
        files are never re-downloaded.
        """

    @abstractmethod
    def validate(self) -> None:
        """Check file integrity and record-count sanity.

        Raise ValueError (or a subclass) if validation fails.
        """

    @abstractmethod
    def load(self) -> None:
        """Upsert data into PostGIS.

        Never TRUNCATE + INSERT.  Use INSERT … ON CONFLICT DO UPDATE.
        """

    @abstractmethod
    def register(self) -> None:
        """Upsert a row in data_source_registry via _upsert_registry()."""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _upsert_registry(
        self,
        version: str,
        coverage_region: str,
        notes: Optional[str] = None,
    ) -> None:
        """Write or update this source's row in data_source_registry."""
        from plinth.db.connection import get_connection

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO data_source_registry
                        (source_name, dataset_version, last_downloaded,
                         update_frequency, next_review_date,
                         coverage_region, notes)
                    VALUES (%s, %s, now(), %s, %s, %s, %s)
                    ON CONFLICT (source_name) DO UPDATE SET
                        dataset_version  = EXCLUDED.dataset_version,
                        last_downloaded  = EXCLUDED.last_downloaded,
                        update_frequency = EXCLUDED.update_frequency,
                        next_review_date = EXCLUDED.next_review_date,
                        coverage_region  = EXCLUDED.coverage_region,
                        notes            = EXCLUDED.notes
                    """,
                    (
                        self.source_name,
                        version,
                        self.update_frequency,
                        self._next_review_date(),
                        coverage_region,
                        notes,
                    ),
                )
            conn.commit()

    def _next_review_date(self) -> datetime.date:
        today = datetime.date.today()
        if self.update_frequency == "monthly":
            # First day of next month
            return (today.replace(day=1) + datetime.timedelta(days=32)).replace(day=1)
        elif self.update_frequency == "decadal":
            return today.replace(year=today.year + 10)
        else:  # annual (default)
            return today.replace(year=today.year + 1)

    def _log(self, msg: str) -> None:
        print(f"[{self.source_name}] {msg}", flush=True)
