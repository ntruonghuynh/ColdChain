"""Centralized configuration loaded from environment variables (see .env.example)."""

from functools import lru_cache

from ipaddress import ip_address

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url

APP_NAME = "Cold Chain Monitoring and Excursion Response"
APP_VERSION = "0.1.0"
CURRENT_MILESTONE = "M6"


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

    # Easy classroom accounts are permitted only on an explicitly local loopback demo.
    local_demo_mode: bool = False
    frontend_bind_address: str = "127.0.0.1"

    # Local-demo authentication. Do not use these demo secrets outside an isolated demo.
    jwt_secret: SecretStr = SecretStr("")
    jwt_expires_min: int = 120
    chain_rpc_url: str = "http://chain:8545"
    chain_id: int = 31337
    chain_contract_address: str = ""
    chain_confirmations: int = 1
    outbox_max_attempts: int = 8
    outbox_base_delay_ms: int = 500
    audit_signing_key: SecretStr = SecretStr("")
    chain_deployment_file: str = "blockchain/deployments/local.json"
    chain_mnemonic: SecretStr = SecretStr("test test test test test test test test test test test junk")
    chain_account_index_shipper: int = 1
    chain_account_index_carrier: int = 2
    chain_account_index_quality: int = 3
    chain_account_index_warehouse: int = 4
    chain_account_index_monitor: int = 5

    # M6 provider calls are disabled by default and never required for stack startup.
    llm_provider: str = "disabled"
    llm_model: str = ""
    llm_api_base_url: str = ""
    llm_corpus_dir: str = ""
    llm_api_key: SecretStr = SecretStr("")
    llm_timeout_s: float = 30.0
    llm_max_retries: int = 1
    llm_max_output_tokens: int = 1200
    llm_fallback_enabled: bool = False
    llm_price_input_per_mtok_usd: float | None = None
    llm_price_output_per_mtok_usd: float | None = None
    m6_runtime_version: str = "m6-source-unversioned"

    @model_validator(mode="after")
    def local_demo_must_be_loopback_only(self) -> "Settings":
        if self.local_demo_mode:
            try:
                loopback_only = ip_address(self.frontend_bind_address).is_loopback
            except ValueError:
                loopback_only = False
            if self.app_env.lower() != "local" or not loopback_only:
                raise ValueError(
                    "LOCAL_DEMO_MODE requires APP_ENV=local and FRONTEND_BIND_ADDRESS set to a loopback IP"
                )
        return self

    @field_validator("llm_price_input_per_mtok_usd", "llm_price_output_per_mtok_usd", mode="before")
    @classmethod
    def empty_optional_prices_are_unset(cls, value: object) -> object:
        """Compose may pass empty optional numeric variables as empty strings."""
        return None if value == "" else value

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
