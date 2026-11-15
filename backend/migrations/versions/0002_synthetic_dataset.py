"""synthetic dataset provenance and ground truth schema (Milestone 2)

Additive only; no Milestone 1 table or row is changed or removed.

- ``dataset_release``: provenance of each imported dataset (generator, config, seed,
  policy hash, content fingerprint, full manifest) [DATA-07, NFR-03].
- ``shipment.source_dataset_id``: nullable link from a shipment to the dataset that
  created it. Existing shipments keep NULL.
- Schema ``ground_truth`` with ``journey`` and ``event``: simulator labels kept apart
  from the operational tables that detection code reads [DATA-09].

Generated with Alembic autogenerate from app.db.models, then edited by hand:
schema creation/removal added, column types rendered as in revision 0001.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0002'
down_revision: str | None = '0001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

GT = 'ground_truth'


def upgrade() -> None:
    op.create_table('dataset_release',
    sa.Column('dataset_id', sa.String(length=100), nullable=False),
    sa.Column('dataset_name', sa.String(length=60), nullable=False),
    sa.Column('dataset_version', sa.String(length=20), nullable=False),
    sa.Column('data_origin', sa.Enum('SIMULATED', 'MEASURED', name='data_origin', native_enum=False, create_constraint=True, length=40), nullable=False),
    sa.Column('generator_name', sa.String(length=60), nullable=False),
    sa.Column('generator_version', sa.String(length=20), nullable=False),
    sa.Column('config_version', sa.String(length=20), nullable=False),
    sa.Column('config_sha256', sa.String(length=64), nullable=False),
    sa.Column('seed', sa.BigInteger(), nullable=False),
    sa.Column('split_seed', sa.BigInteger(), nullable=False),
    sa.Column('journey_count', sa.Integer(), nullable=False),
    sa.Column('policy_id', sa.Uuid(), nullable=False),
    sa.Column('policy_content_sha256', sa.String(length=64), nullable=False),
    sa.Column('dataset_fingerprint', sa.String(length=64), nullable=False),
    sa.Column('manifest', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('imported_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("config_sha256 ~ '^[0-9a-f]{64}$'", name=op.f('ck_dataset_release_config_sha256_hex')),
    sa.CheckConstraint("dataset_fingerprint ~ '^[0-9a-f]{64}$'", name=op.f('ck_dataset_release_dataset_fingerprint_hex')),
    sa.CheckConstraint("policy_content_sha256 ~ '^[0-9a-f]{64}$'", name=op.f('ck_dataset_release_policy_content_sha256_hex')),
    sa.CheckConstraint('journey_count > 0', name=op.f('ck_dataset_release_journey_count_positive')),
    sa.ForeignKeyConstraint(['policy_id'], ['policy.policy_id'], name=op.f('fk_dataset_release_policy_id_policy')),
    sa.PrimaryKeyConstraint('dataset_id', name=op.f('pk_dataset_release')),
    sa.UniqueConstraint('dataset_fingerprint', name=op.f('uq_dataset_release_dataset_fingerprint'))
    )

    op.add_column('shipment', sa.Column('source_dataset_id', sa.String(length=100), nullable=True))
    op.create_foreign_key(op.f('fk_shipment_source_dataset_id_dataset_release'), 'shipment', 'dataset_release', ['source_dataset_id'], ['dataset_id'])
    op.create_index('ix_shipment_source_dataset_id', 'shipment', ['source_dataset_id'], unique=False)

    op.execute(f'CREATE SCHEMA {GT}')
    op.create_table('journey',
    sa.Column('journey_id', sa.String(length=60), nullable=False),
    sa.Column('dataset_id', sa.String(length=100), nullable=False),
    sa.Column('shipment_id', sa.String(length=60), nullable=False),
    sa.Column('primary_scenario', sa.Enum('NORMAL', 'GRADUAL_WARMING', 'HIGH_EXCURSION', 'LOW_EXCURSION', 'SENSOR_SPIKE', 'SENSOR_BIAS_DRIFT', 'MISSING_READINGS', 'OCEAN_COVERAGE_GAP', 'DOOR_OPENING', name='primary_scenario', native_enum=False, create_constraint=True, length=40), nullable=False),
    sa.Column('scenario_tags', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('ambient_profile', sa.Enum('TEMPERATE', 'HOT', 'COLD', 'VARIABLE', name='ambient_profile', native_enum=False, create_constraint=True, length=40), nullable=False),
    sa.Column('route_type', sa.String(length=20), nullable=False),
    sa.Column('policy_excursion_count', sa.Integer(), nullable=False),
    sa.Column('parameters', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('policy_excursion_count >= 0', name=op.f('ck_journey_policy_excursion_count_non_negative')),
    sa.ForeignKeyConstraint(['dataset_id'], ['dataset_release.dataset_id'], name=op.f('fk_journey_dataset_id_dataset_release')),
    sa.ForeignKeyConstraint(['shipment_id'], ['shipment.shipment_id'], name=op.f('fk_journey_shipment_id_shipment')),
    sa.PrimaryKeyConstraint('journey_id', name=op.f('pk_journey')),
    sa.UniqueConstraint('shipment_id', name=op.f('uq_journey_shipment_id')),
    schema=GT
    )
    op.create_index('ix_journey_dataset_id', 'journey', ['dataset_id'], unique=False, schema=GT)
    op.create_table('event',
    sa.Column('event_id', sa.String(length=80), nullable=False),
    sa.Column('dataset_id', sa.String(length=100), nullable=False),
    sa.Column('journey_id', sa.String(length=60), nullable=False),
    sa.Column('event_type', sa.Enum('TEMP_ABOVE_MAX', 'TEMP_BELOW_MIN', 'EXCURSION_HIGH', 'EXCURSION_LOW', 'REEFER_FAILURE', 'SETPOINT_FAULT_HIGH', 'SETPOINT_FAULT_LOW', 'GRADUAL_WARMING', 'DOOR_OPEN', 'DEFROST_CYCLE', 'SENSOR_SPIKE', 'SENSOR_BIAS', 'SENSOR_DRIFT', 'MISSING_DATA', 'TRANSMISSION_DELAY', name='event_type', native_enum=False, create_constraint=True, length=40), nullable=False),
    sa.Column('label_source', sa.Enum('PHYSICAL_SIMULATION', 'POLICY_RULE_ON_TRUE_TEMPERATURE', 'INJECTED_SCENARIO', 'OBSERVATION_MODEL', name='label_source', native_enum=False, create_constraint=True, length=40), nullable=False),
    sa.Column('cause', sa.String(length=200), nullable=False),
    sa.Column('start_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('end_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('duration_min', sa.Integer(), nullable=False),
    sa.Column('attributes', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('duration_min >= 0', name=op.f('ck_event_duration_non_negative')),
    sa.CheckConstraint('end_at >= start_at', name=op.f('ck_event_interval_ordered')),
    sa.ForeignKeyConstraint(['dataset_id'], ['dataset_release.dataset_id'], name=op.f('fk_event_dataset_id_dataset_release')),
    sa.ForeignKeyConstraint(['journey_id'], [f'{GT}.journey.journey_id'], name=op.f('fk_event_journey_id_journey')),
    sa.PrimaryKeyConstraint('event_id', name=op.f('pk_event')),
    schema=GT
    )
    op.create_index('ix_event_journey_id_event_type', 'event', ['journey_id', 'event_type'], unique=False, schema=GT)


def downgrade() -> None:
    op.drop_index('ix_event_journey_id_event_type', table_name='event', schema=GT)
    op.drop_table('event', schema=GT)
    op.drop_index('ix_journey_dataset_id', table_name='journey', schema=GT)
    op.drop_table('journey', schema=GT)
    op.execute(f'DROP SCHEMA {GT}')  # no CASCADE: fails loudly if anything else was put there
    op.drop_index('ix_shipment_source_dataset_id', table_name='shipment')
    op.drop_constraint(op.f('fk_shipment_source_dataset_id_dataset_release'), 'shipment', type_='foreignkey')
    op.drop_column('shipment', 'source_dataset_id')
    op.drop_table('dataset_release')
