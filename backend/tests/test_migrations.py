"""Migration workflow: upgrade, schema matches models, downgrade, re-upgrade."""

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Engine, inspect, text

from app.db.base import Base, include_name
from tests.conftest import alembic_config

EXPECTED_TABLES = {
    "organization", "app_user", "user_role", "product", "policy",
    "shipment", "sensor", "sensor_assignment",
    "ingest_batch", "reading", "context_reading", "rejected_record",
    "incident", "disposition", "disposition_incident", "custody_event", "warehouse_release",
    "business_event", "outbox_entry", "chain_record",
    "dataset_release",  # Milestone 2
}
GROUND_TRUTH_TABLES = {"journey", "event"}  # schema ground_truth, Milestone 2 (DATA-09)
M1_TABLES = EXPECTED_TABLES - {"dataset_release"}


def test_upgrade_creates_all_tables_and_matches_models(migrations_engine: Engine) -> None:
    with migrations_engine.begin() as conn:
        command.upgrade(alembic_config(conn), "head")
    tables = set(inspect(migrations_engine).get_table_names())
    assert tables == EXPECTED_TABLES | {"alembic_version"}
    assert set(inspect(migrations_engine).get_table_names(schema="ground_truth")) == GROUND_TRUTH_TABLES
    with migrations_engine.connect() as conn:
        ctx = MigrationContext.configure(conn, opts={"compare_type": True, "include_schemas": True,
                                                     "include_name": include_name})
        diff = compare_metadata(ctx, Base.metadata)
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
    assert "ground_truth" not in inspect(migrations_engine).get_schema_names()
    with migrations_engine.begin() as conn:
        command.upgrade(alembic_config(conn), "head")
    assert EXPECTED_TABLES <= set(inspect(migrations_engine).get_table_names())


def test_m2_migration_is_additive_and_reversible_to_m1(migrations_engine: Engine) -> None:
    """0002 only adds; downgrading to 0001 restores exactly the Milestone 1 schema."""
    with migrations_engine.begin() as conn:
        command.upgrade(alembic_config(conn), "0001")
    m1_columns = {c["name"] for c in inspect(migrations_engine).get_columns("shipment")}
    with migrations_engine.begin() as conn:
        command.upgrade(alembic_config(conn), "head")
    head_columns = {c["name"] for c in inspect(migrations_engine).get_columns("shipment")}
    assert head_columns - m1_columns == {"source_dataset_id"}
    with migrations_engine.begin() as conn:
        command.downgrade(alembic_config(conn), "0001")
    inspector = inspect(migrations_engine)
    assert set(inspector.get_table_names()) == M1_TABLES | {"alembic_version"}
    assert "ground_truth" not in inspector.get_schema_names()
    assert {c["name"] for c in inspector.get_columns("shipment")} == m1_columns
