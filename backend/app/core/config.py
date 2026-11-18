from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]

Environment = Literal["development", "test", "production"]


class Settings(BaseSettings):
    """Конфигурация приложения. Значения читаются из переменных окружения и `.env`."""

    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "FleetGuard AI"
    version: str = "0.1.0"
    environment: Environment = "development"
    debug: bool = False
    docs_enabled: bool = True

    api_v1_prefix: str = "/api/v1"
    allowed_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    database_url: str = "postgresql+psycopg://fleetguard:fleetguard@localhost:5433/fleetguard"
    redis_url: str = "redis://localhost:6379/0"

    s3_endpoint_url: str = "http://localhost:9000"
    # Адрес для браузера: в Docker backend ходит на minio:9000, а ссылки ведут на localhost:9000.
    s3_public_endpoint_url: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket: str = "fleetguard"
    s3_region: str = "us-east-1"
    s3_use_ssl: bool = False
    # 7 суток — верхняя граница SigV4; короткий срок не даёт ссылке «протухнуть» в отчёте.
    s3_presign_expire_seconds: int = Field(default=900, ge=60, le=604800)

    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    max_upload_bytes: int = 10 * 1024 * 1024

    @field_validator("jwt_secret")
    @classmethod
    def _require_jwt_secret(cls, value: str) -> str:
        # Короткий или пустой секрет делает подпись токенов предсказуемой.
        if len(value) < 32:
            raise ValueError(
                "JWT_SECRET должен быть не короче 32 символов: "
                'python -c "import secrets; print(secrets.token_urlsafe(48))"'
            )
        return value

    @field_validator("database_url")
    @classmethod
    def _require_psycopg_driver(cls, value: str) -> str:
        # Alembic и SQLAlchemy в проекте используют синхронный psycopg 3.
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
