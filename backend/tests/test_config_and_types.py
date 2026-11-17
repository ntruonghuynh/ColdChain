"""Unit tests without a database: configuration and timestamp type (NFR-05)."""

from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.db.types import NaiveDatetimeError, UTCDateTime


def test_database_url_escapes_special_characters_in_password() -> None:
    settings = Settings(postgres_host="db", postgres_user="u", postgres_db="d",
                        postgres_password=SecretStr("p@ss:w/rd#1"), database_url=None)
    url = settings.sqlalchemy_url()
    assert url.password == "p@ss:w/rd#1"
    assert url.host == "db" and url.database == "d" and url.drivername == "postgresql+psycopg"
    assert "p%40ss%3Aw%2Frd%231" in url.render_as_string(hide_password=False)


def test_database_url_override_takes_precedence() -> None:
    settings = Settings(database_url=SecretStr("postgresql+psycopg://a:b@h:6543/x"))
    url = settings.sqlalchemy_url()
    assert (url.host, url.port, url.database) == ("h", 6543, "x")


def test_empty_optional_llm_prices_are_treated_as_unset() -> None:
    settings = Settings(llm_price_input_per_mtok_usd="", llm_price_output_per_mtok_usd="")
    assert settings.llm_price_input_per_mtok_usd is None
    assert settings.llm_price_output_per_mtok_usd is None


def test_utc_datetime_rejects_naive_timestamps() -> None:
    with pytest.raises(NaiveDatetimeError):
        UTCDateTime().process_bind_param(datetime(2026, 1, 1, 12, 0), dialect=None)  # type: ignore[arg-type]


def test_utc_datetime_converts_aware_timestamps_to_utc() -> None:
    local = datetime(2026, 1, 1, 19, 0, tzinfo=timezone(timedelta(hours=7)))
    stored = UTCDateTime().process_bind_param(local, dialect=None)  # type: ignore[arg-type]
    assert stored == datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    assert stored.utcoffset() == timedelta(0)
