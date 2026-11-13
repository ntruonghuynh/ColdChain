"""Migration workflow: upgrade, schema matches models, downgrade, re-upgrade."""

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Engine, inspect, text

from app.db.base import Base
from tests.conftest import alembic_config

EXPECTED_TABLES = {
    "organization", "app_user", "user_role", "product", "policy",
    "shipment", "sensor", "sensor_assignment",
    "ingest_batch", "reading", "context_reading", "rejected_record",
    "incident", "disposition", "disposition_incident", "custody_event", "warehouse_release",
    "business_event", "outbox_entry", "chain_record",
}


def test_upgrade_creates_all_tables_and_matches_models(migrations_engine: Engine) -> None:
    with migrations_engine.begin() as conn:
        command.upgrade(alembic_config(conn), "head")
    tables = set(inspect(migrations_engine).get_table_names())
    assert tables == EXPECTED_TABLES | {"alembic_version"}
    with migrations_engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata)
    assert diff == [], f"Models and migrations differ: {diff}"


def test_event_and_received_time_are_timestamptz(migrations_engine: Engine) -> None:
    """FR-03 / NFR-05: both clocks stored, timezone-aware, NOT NULL."""
    with migrations_engine.begin() as conn:
        command.upgrade(alembic_config(conn), "head")
        rows = conn.execute(text(
            "SELECT table_name, column_name, data_type, is_nullable FROM information_schema.columns "
            "WHERE table_name IN ('reading','context_reading') AND column_name IN ('event_at','received_at')"
        )).all()
    assert len(rows) == 4
    for table, column, data_type, nullable in rows:
        assert data_type == "timestamp with time zone", (table, column)
        assert nullable == "NO", (table, column)


def test_downgrade_removes_schema_and_upgrade_again_works(migrations_engine: Engine) -> None:
    with migrations_engine.begin() as conn:
        cfg = alembic_config(conn)
        command.upgrade(cfg, "head")
        command.downgrade(cfg, "base")
    assert set(inspect(migrations_engine).get_table_names()) <= {"alembic_version"}
    with migrations_engine.begin() as conn:
        command.upgrade(alembic_config(conn), "head")
    assert EXPECTED_TABLES <= set(inspect(migrations_engine).get_table_names())
