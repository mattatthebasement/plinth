import sys

import click


@click.group()
def infra() -> None:
    """Infrastructure initialization commands."""


@infra.command()
def init() -> None:
    """Create MinIO buckets and verify infrastructure is ready."""
    click.echo("Initializing infrastructure...")

    _create_minio_bucket()

    click.echo("Infrastructure initialization complete.")


def _create_minio_bucket() -> None:
    import boto3
    from botocore.exceptions import ClientError

    from plinth.config import get_settings

    s = get_settings()
    endpoint = s.minio_endpoint
    if not endpoint.startswith("http"):
        protocol = "https" if s.minio_secure else "http"
        endpoint = f"{protocol}://{endpoint}"

    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=s.minio_access_key,
        aws_secret_access_key=s.minio_secret_key,
    )

    bucket = s.minio_bucket_rasters
    try:
        client.create_bucket(Bucket=bucket)
        click.echo(f"  ✓ Created MinIO bucket: {bucket}")
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        if code in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
            click.echo(f"  ✓ MinIO bucket already exists: {bucket}")
        else:
            click.echo(f"  ✗ Failed to create bucket '{bucket}': {exc}", err=True)
            sys.exit(1)
