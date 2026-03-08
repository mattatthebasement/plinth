import click


@click.group()
def raster() -> None:
    """Raster tile management commands."""


@raster.command()
def index() -> None:
    """Rebuild the raster_tiles PostGIS index from MinIO bucket listing.

    Walks every .tif object in the MinIO rasters bucket, downloads each COG
    to a temp file to read bounds/resolution via rasterio, then upserts a
    row in raster_tiles.  Stale rows for missing objects are removed.
    """
    import tempfile
    import rasterio
    from pathlib import Path
    from plinth.config import get_settings
    from plinth.db.connection import get_connection
    from plinth.raster.minio import list_objects, download_cog

    s = get_settings()
    bucket = s.minio_bucket_rasters

    click.echo("Listing objects in MinIO rasters bucket…")
    keys = [k for k in list_objects(bucket=bucket) if k.endswith(".tif")]
    click.echo(f"  Found {len(keys)} .tif objects.")

    rows = []
    with tempfile.TemporaryDirectory() as tmpdir:
        for s3_key in keys:
            tmp_path = Path(tmpdir) / s3_key.replace("/", "_")
            try:
                download_cog(s3_key, tmp_path)
                with rasterio.open(tmp_path) as ds:
                    b = ds.bounds
                    res_deg = (ds.res[0] + ds.res[1]) / 2
                    res_m = res_deg * 111_320
                parts = s3_key.split("/")
                dataset = parts[0] if parts else s3_key
                version = parts[1] if len(parts) > 1 else None
                tile_id = parts[-1].replace(".tif", "") if parts else s3_key
                rows.append({
                    "dataset": dataset,
                    "s3_key": s3_key,
                    "minx": b.left, "miny": b.bottom,
                    "maxx": b.right, "maxy": b.top,
                    "res_m": round(res_m, 1),
                    "tile_id": tile_id,
                    "version": version,
                })
                click.echo(f"  OK  {s3_key}  ({res_m:.0f} m)")
            except Exception as exc:
                click.echo(f"  ERR {s3_key}: {exc}", err=True)

    with get_connection() as conn:
        with conn.cursor() as cur:
            for row in rows:
                cur.execute(
                    """
                    INSERT INTO raster_tiles
                        (dataset, s3_key, bounds, resolution_m, tile_id, dataset_version)
                    VALUES
                        (%(dataset)s, %(s3_key)s,
                         ST_MakeEnvelope(%(minx)s,%(miny)s,%(maxx)s,%(maxy)s, 4326),
                         %(res_m)s, %(tile_id)s, %(version)s)
                    ON CONFLICT (s3_key) DO UPDATE SET
                        bounds           = EXCLUDED.bounds,
                        resolution_m     = EXCLUDED.resolution_m,
                        dataset_version  = EXCLUDED.dataset_version
                    """,
                    row,
                )
            if keys:
                cur.execute(
                    "DELETE FROM raster_tiles WHERE s3_key != ALL(%s)",
                    (keys,),
                )
        conn.commit()

    click.echo(f"raster_tiles updated: {len(rows)} tile(s) indexed.")

