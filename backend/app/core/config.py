"""Centralized configuration loaded from environment variables (see .env.example)."""

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url

APP_NAME = "Cold Chain Monitoring and Excursion Response"
APP_VERSION = "0.1.0"
CURRENT_MILESTONE = "M2"


class Settings(BaseSettings):
    """Application settings.

    The database URL is built from its parts so that passwords with special
    characters are escaped correctly. ``DATABASE_URL`` overrides the parts when set.
    """

    model_config = SettingsConfigDict(env_file=None, extra="ignore", case_sensitive=False)

    app_env: str = Field(default="local", description="local | test | production")

    postgres_host: str = "db"
    postgres_port: int = 5432
    postgres_db: str = "coldchain"
    postgres_user: str = "coldchain"
    postgres_password: SecretStr = SecretStr("")
    database_url: SecretStr | None = None

    db_pool_size: int = 5
    db_connect_timeout_s: int = 5

    # Comma-separated list; empty means same-origin only (the nginx proxy serves /api).
    cors_allow_origins: str = ""

    def sqlalchemy_url(self) -> URL:
        if self.database_url is not None and self.database_url.get_secret_value():
            return make_url(self.database_url.get_secret_value())
        return URL.create(
            drivername="postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value() or None,
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )

    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
