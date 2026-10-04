from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BG_", env_file=".env", extra="ignore")
    database_url: str = "postgresql+psycopg://browsergrid:browsergrid@postgres/browsergrid"
    redis_url: str = "redis://redis:6379/0"
    encryption_key: str = ""
    key_file: str = "/state/encryption.key"
    origins: str = "http://localhost:3000"
    secure_cookies: bool = False
    s3_endpoint: str = "http://minio:9000"
    s3_public_endpoint: str = "http://localhost:9000"
    s3_access_key: str = "browsergrid-local"
    s3_secret_key: str = "browsergrid-local-development-only"
    s3_bucket: str = "browsergrid"
    runtime_image: str = "browsergrid-runtime:1.58.2"
    sandbox_network: str = "browsergrid_sandbox"
    egress_proxy: str = "http://egress:3128"
    max_artifact_bytes: int = 100 * 1024 * 1024
    max_run_artifacts_bytes: int = 256 * 1024 * 1024
    max_report_bytes: int = 5 * 1024 * 1024
    max_bundle_bytes: int = 10 * 1024 * 1024
    max_run_jobs: int = 12
    max_daily_jobs: int = 100
    lease_seconds: int = 45
    worker_version: str = "0.1.0"

    def key(self) -> bytes:
        value = self.encryption_key or Path(self.key_file).read_text().strip()
        return value.encode()


@lru_cache
def settings() -> Settings:
    return Settings()
