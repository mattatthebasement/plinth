"""Legacy API clients — superseded by local bulk data (migration 007).

These modules are retained for reference but are no longer called by any
query function or report context builder. All seven data sources they
previously served at query time are now read from local PostGIS tables
or MinIO COG rasters.

Do not import from this package in new code.
"""
