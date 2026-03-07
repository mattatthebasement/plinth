from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # PostgreSQL
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_db: str = "plinth"
    postgres_user: str = "plinth"
    postgres_password: str = ""

    # MinIO
    minio_endpoint: str = "minio:9000"
    minio_access_key: str = ""
    minio_secret_key: str = ""
    minio_bucket_rasters: str = "plinth-rasters"
    minio_secure: bool = False

    # Mapbox
    mapbox_token: str = ""

    # Prefect
    prefect_api_url: str = "http://prefect-server:4200/api"

    # API keys
    census_api_key: str = ""
    epa_aqs_key: str = ""
    epa_aqs_email: str = ""

    # Regional bounding box (NE Oklahoma for POC)
    region_bbox_minx: float = -96.5
    region_bbox_miny: float = 35.5
    region_bbox_maxx: float = -94.5
    region_bbox_maxy: float = 37.0

    # Staging directory for downloaded source files
    staging_dir: str = "/staging"

    model_config = {"env_file": ".env", "case_sensitive": False, "extra": "ignore"}


def get_settings() -> Settings:
    return Settings()
