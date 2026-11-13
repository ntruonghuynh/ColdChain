"""Test fixtures.

Tests use their own databases on the same PostgreSQL server:

* ``<POSTGRES_DB>_test``           — migrated + seeded once per session; each test runs
                                     inside a transaction that is rolled back.
* ``<POSTGRES_DB>_test_migrations`` — used only by migration round-trip tests.

The main application database is never touched. If PostgreSQL is not reachable,
database tests FAIL (they are not skipped), so a green run always means they ran.
"""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

# ---- Point the application at the test database BEFORE importing app modules ----
_MAIN_DB = os.environ.get("POSTGRES_DB", "coldchain")
TEST_DB = os.environ.get("TEST_POSTGRES_DB", f"{_MAIN_DB}_test")
MIGRATIONS_DB = f"{TEST_DB}_migrations"
if TEST_DB == _MAIN_DB or not TEST_DB.endswith("_test"):
    raise RuntimeError(f"Refusing to run tests against database {TEST_DB!r}: name must end with '_test'.")
os.environ["POSTGRES_DB"] = TEST_DB
os.environ.pop("DATABASE_URL", None)

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import Connection, Engine, create_engine, text  # noqa: E402
from sqlalchemy.engine import URL  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.config import Settings, get_settings  # noqa: E402
from app.db.session import build_engine, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.seed.loader import run_seed  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parents[1]


def settings_for(database: str) -> Settings:
    return get_settings().model_copy(update={"postgres_db": database, "database_url": None})


def _admin_url() -> URL:
    return get_settings().sqlalchemy_url().set(database="postgres")


def recreate_database(name: str) -> None:
    admin = create_engine(_admin_url(), isolation_level="AUTOCOMMIT",
                          connect_args={"connect_timeout": 5})
    try:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
            conn.execute(text(f'CREATE DATABASE "{name}"'))
    except Exception as exc:  # pragma: no cover - environment problem
        pytest.fail(f"PostgreSQL not reachable for tests ({exc.__class__.__name__}: {exc}). "
                    "Run tests with `docker compose --profile test run --rm backend-tests`.")
    finally:
        admin.dispose()


def alembic_config(connection: Connection) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    cfg.attributes["connection"] = connection
    return cfg


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    """Fresh test database, migrated to head and seeded with reference data."""
    recreate_database(TEST_DB)
    eng = build_engine(settings_for(TEST_DB))
    with eng.begin() as conn:
        command.upgrade(alembic_config(conn), "head")
    with Session(eng) as session:
        run_seed(session)
    yield eng
    eng.dispose()


@pytest.fixture
def db_session(engine: Engine) -> Iterator[Session]:
    """Session inside an outer transaction that is always rolled back."""
    connection = engine.connect()
    outer = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
        outer.rollback()
        connection.close()


@pytest.fixture
def client(db_session: Session) -> Iterator[TestClient]:
    def _override() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db] = _override
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def migrations_engine() -> Iterator[Engine]:
    """Empty database for migration round-trip tests."""
    recreate_database(MIGRATIONS_DB)
    eng = build_engine(settings_for(MIGRATIONS_DB))
    yield eng
    eng.dispose()
