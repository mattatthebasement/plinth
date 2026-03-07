"""MinIO (S3-compatible) helpers for raster COG tiles."""
from pathlib import Path
from typing import Optional

import boto3
from botocore.exceptions import ClientError

from plinth.config import get_settings


def get_minio_client():
    """Return a boto3 S3 client pointed at the configured MinIO endpoint."""
    s = get_settings()
    endpoint = s.minio_endpoint
    if not endpoint.startswith("http"):
        protocol = "https" if s.minio_secure else "http"
        endpoint = f"{protocol}://{endpoint}"
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=s.minio_access_key,
        aws_secret_access_key=s.minio_secret_key,
    )


def upload_cog(local_path: Path, s3_key: str, *, bucket: Optional[str] = None) -> str:
    """Upload a local COG file to MinIO. Returns the S3 key.

    MinIO key pattern: {dataset}/{version}/{tile_id}.tif
    e.g. usgs-3dep/2023/n37w096.tif
    """
    raise NotImplementedError("MinIO upload — Phase 3")


def download_cog(s3_key: str, local_path: Path, *, bucket: Optional[str] = None) -> Path:
    """Download a COG from MinIO to *local_path*. Returns the local path."""
    raise NotImplementedError("MinIO download — Phase 3")


def presign_url(s3_key: str, expires_in: int = 3600, *, bucket: Optional[str] = None) -> str:
    """Generate a pre-signed URL for a MinIO object."""
    raise NotImplementedError("MinIO presign — Phase 3")
