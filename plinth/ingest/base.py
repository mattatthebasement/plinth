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

    def _download_if_changed(self, url: str, dest: Path) -> bool:
        """Stream-download *url* to *dest*, skipping if the ETag matches.

        Returns ``True`` if a fresh download occurred, ``False`` if already
        current.  The ETag from the server is persisted in a sidecar file at
        ``dest.with_suffix(dest.suffix + '.etag')`` so subsequent runs can
        skip unchanged files.

        Uses ``httpx`` with ``follow_redirects=True`` and a 300-second timeout.
        Files larger than 1 MB are streamed in 1 MB chunks.
        """
        import httpx

        etag_file = dest.with_suffix(dest.suffix + ".etag")
        headers: dict[str, str] = {}
        if dest.exists() and etag_file.exists():
            headers["If-None-Match"] = etag_file.read_text().strip()

        with httpx.stream(
            "GET", url, headers=headers, follow_redirects=True, timeout=300
        ) as response:
            if response.status_code == 304:
                self._log(f"Already current (ETag matched): {dest.name}")
                return False

            response.raise_for_status()

            dest.parent.mkdir(parents=True, exist_ok=True)
            chunk_size = 1024 * 1024  # 1 MB
            with dest.open("wb") as fh:
                for chunk in response.iter_bytes(chunk_size=chunk_size):
                    fh.write(chunk)

            etag = response.headers.get("ETag", "")
            if etag:
                etag_file.write_text(etag)

        self._log(f"Downloaded: {dest.name}")
        return True

    def _ogr2ogr_to_staging_table(
        self,
        input_path: str,
        layer: str,
        staging_table: str,
        extra_args: Optional[list[str]] = None,
    ) -> None:
        """Load a vector layer into a PostGIS staging table via ``ogr2ogr``.

        The staging table is overwritten on each call (``-overwrite``).
        Geometry is always reprojected to EPSG:4326 and promoted to multi-part.

        Args:
            input_path: Path to the source file or GDB directory.
            layer: Layer name inside the source.
            staging_table: Target table name in the PostGIS database.
            extra_args: Additional ogr2ogr arguments inserted before the source
                path, e.g. ``["-spat", "minx", "miny", "maxx", "maxy"]``.

        Raises:
            RuntimeError: If ogr2ogr exits with a non-zero status code.
        """
        import subprocess

        s = self.settings
        pg_dsn = (
            f"PG:host={s.postgres_host} port={s.postgres_port} "
            f"dbname={s.postgres_db} user={s.postgres_user} "
            f"password={s.postgres_password}"
        )

        cmd = [
            "ogr2ogr",
            "-f", "PostgreSQL",
            pg_dsn,
            "-overwrite",
            "-nln", staging_table,
            "-t_srs", "EPSG:4326",
            "-nlt", "PROMOTE_TO_MULTI",
            "-lco", "GEOMETRY_NAME=geom",
            "-lco", "FID=gid",
        ]
        if extra_args:
            cmd.extend(extra_args)
        cmd.extend([input_path, layer])

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"ogr2ogr failed loading {layer!r} into {staging_table!r}.\n"
                f"stderr: {result.stderr}"
            )

    def _log(self, msg: str) -> None:
        print(f"[{self.source_name}] {msg}", flush=True)
