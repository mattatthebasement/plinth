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


def _bucket(bucket: Optional[str] = None) -> str:
    return bucket or get_settings().minio_bucket_rasters


def ensure_bucket(bucket: Optional[str] = None) -> None:
    """Create the rasters bucket if it does not already exist."""
    client = get_minio_client()
    name = _bucket(bucket)
    try:
        client.head_bucket(Bucket=name)
    except ClientError as exc:
        if exc.response["Error"]["Code"] in ("404", "NoSuchBucket"):
            client.create_bucket(Bucket=name)
        else:
            raise


def upload_cog(local_path: Path, s3_key: str, *, bucket: Optional[str] = None) -> str:
    """Upload a local COG file to MinIO. Returns the S3 key.

    MinIO key pattern: {dataset}/{version}/{tile_id}.tif
    e.g. usgs-3dep/2025/ne-oklahoma.tif
    """
    client = get_minio_client()
    b = _bucket(bucket)
    ensure_bucket(b)
    client.upload_file(str(local_path), b, s3_key)
    return s3_key


def download_cog(s3_key: str, local_path: Path, *, bucket: Optional[str] = None) -> Path:
    """Download a COG from MinIO to *local_path*. Returns the local path."""
    client = get_minio_client()
    local_path.parent.mkdir(parents=True, exist_ok=True)
    client.download_file(_bucket(bucket), s3_key, str(local_path))
    return local_path


def presign_url(s3_key: str, expires_in: int = 3600, *, bucket: Optional[str] = None) -> str:
    """Generate a pre-signed URL for a MinIO object."""
    client = get_minio_client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": _bucket(bucket), "Key": s3_key},
        ExpiresIn=expires_in,
    )


def list_objects(prefix: str = "", *, bucket: Optional[str] = None) -> list[str]:
    """Return all S3 keys under *prefix* in the rasters bucket."""
    client = get_minio_client()
    b = _bucket(bucket)
    keys: list[str] = []
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=b, Prefix=prefix):
        for obj in page.get("Contents", []):
            keys.append(obj["Key"])
    return keys
