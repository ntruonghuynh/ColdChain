"""ingestion, telemetry monitoring and policy-baseline detection (Milestone 3)

Additive only; no Milestone 1 or 2 row is changed or removed.

- ``detector_config``: immutable detector configuration versions (nominal sampling interval,
  7 min 30 s continuity limit; D-01, C-01). Kept apart from the policy on purpose.
- ``detector_evaluation``: one row per causal evaluation of a sensor (as_of, input fingerprint,
  policy and detector configuration versions; C-07, C-09).
- ``data_gap``, ``detection``, ``data_quality_warning``: append-only revisions of confirmed
  gaps, observed temperature runs and data-quality warnings (BR-03 to BR-05, C-03, U-01).
- ``incident_revision``: append-only evidence revisions of incidents (C-08).
- ``decision_reassessment``: late evidence that touches an existing quality decision (U-04).
- ``incident``: new nullable columns ``sensor_id``, ``detector_config_id``, ``opened_by_evaluation_id``.
- ``ingest_batch``: ``duplicate_count`` (BR-07) and ``ingest_mode`` (IMPORT / LIVE / REPLAY,
  C-09; existing rows are M2 imports and get IMPORT). The counts check now includes
  duplicates.

Generated with Alembic autogenerate from app.db.models, then edited by hand: column types
rendered as in 0001/0002, CHECK constraints for the added columns written explicitly.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0003'
down_revision: str | None = '0002'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('detector_config',
    sa.Column('detector_config_id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('detector_code', sa.String(length=40), nullable=False),
    sa.Column('config_version', sa.String(length=20), nullable=False),
    sa.Column('nominal_sampling_interval_s', sa.Integer(), nullable=False),
    sa.Column('max_continuous_interval_s', sa.Integer(), nullable=False),
    sa.Column('document', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('content_sha256', sa.String(length=64), nullable=False),
    sa.Column('source_file', sa.String(length=255), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('max_continuous_interval_s > nominal_sampling_interval_s AND max_continuous_interval_s < 2 * nominal_sampling_interval_s', name=op.f('ck_detector_config_continuity_between_one_and_two_intervals')),
    sa.CheckConstraint('nominal_sampling_interval_s > 0', name=op.f('ck_detector_config_nominal_positive')),
    sa.PrimaryKeyConstraint('detector_config_id', name=op.f('pk_detector_config')),
    sa.UniqueConstraint('detector_code', 'config_version', name=op.f('uq_detector_config_detector_code_config_version'))
    )
    op.create_table('detector_evaluation',
    sa.Column('evaluation_id', sa.Uuid(), nullable=False),
    sa.Column('shipment_id', sa.String(length=60), nullable=False),
    sa.Column('sensor_id', sa.String(length=60), nullable=False),
    sa.Column('mode', sa.Enum('LIVE', 'REPLAY', name='evaluation_mode', native_enum=False, create_constraint=True, length=40), nullable=False),
    sa.Column('trigger', sa.Enum('BATCH', 'MONITORING_START', 'MONITORING_END', 'CATCH_UP', name='evaluation_trigger', native_enum=False, create_constraint=True, length=40), nullable=False),
    sa.Column('trigger_batch_id', sa.Uuid(), nullable=True),
    sa.Column('as_of', sa.DateTime(timezone=True), nullable=False),
    sa.Column('affected_from_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('affected_to_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('visible_reading_count', sa.Integer(), nullable=False),
    sa.Column('input_fingerprint', sa.String(length=64), nullable=False),
    sa.Column('policy_id', sa.Uuid(), nullable=False),
    sa.Column('detector_config_id', sa.Uuid(), nullable=False),
    sa.Column('detector_code_version', sa.String(length=40), nullable=False),
    sa.Column('start_boundary_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('end_boundary_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['detector_config_id'], ['detector_config.detector_config_id'], name=op.f('fk_detector_evaluation_detector_config_id_detector_config')),
    sa.ForeignKeyConstraint(['policy_id'], ['policy.policy_id'], name=op.f('fk_detector_evaluation_policy_id_policy')),
    sa.ForeignKeyConstraint(['sensor_id'], ['sensor.sensor_id'], name=op.f('fk_detector_evaluation_sensor_id_sensor')),
    sa.ForeignKeyConstraint(['shipment_id'], ['shipment.shipment_id'], name=op.f('fk_detector_evaluation_shipment_id_shipment')),
    sa.ForeignKeyConstraint(['trigger_batch_id'], ['ingest_batch.batch_id'], name=op.f('fk_detector_evaluation_trigger_batch_id_ingest_batch')),
    sa.PrimaryKeyConstraint('evaluation_id', name=op.f('pk_detector_evaluation'))
    )
    op.create_index('ix_detector_evaluation_shipment_id_sensor_id_as_of', 'detector_evaluation', ['shipment_id', 'sensor_id', 'as_of'], unique=False)
    op.create_table('data_gap',
    sa.Column('gap_revision_id', sa.Uuid(), nullable=False),
    sa.Column('gap_key', sa.String(length=64), nullable=False),
    sa.Column('shipment_id', sa.String(length=60), nullable=False),
    sa.Column('sensor_id', sa.String(length=60), nullable=False),
    sa.Column('start_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('end_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('start_bound', sa.Enum('READING', 'MONITORING_START', 'MONITORING_END', name='gap_start_bound', native_enum=False, create_constraint=True, length=40), nullable=False),
    sa.Column('end_bound', sa.Enum('READING', 'MONITORING_START', 'MONITORING_END', name='gap_end_bound', native_enum=False, create_constraint=True, length=40), nullable=False),
    sa.Column('bracketing_span_s', sa.Numeric(precision=14, scale=6), nullable=False),
    sa.Column('estimated_missing_samples', sa.Integer(), nullable=False),
    sa.Column('estimated_missing_duration_s', sa.Integer(), nullable=False),
    sa.Column('gap_status', sa.Enum('SHORT_GAP', 'UNKNOWN', 'UNKNOWN_REVIEW_REQUIRED', name='gap_status', native_enum=False, create_constraint=True, length=40), nullable=False),
    sa.Column('out_of_range_before', sa.Boolean(), nullable=False),
    sa.Column('out_of_range_after', sa.Boolean(), nullable=False),
    sa.Column('evaluation_id', sa.Uuid(), nullable=False),
    sa.Column('raised_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('superseded_by_evaluation_id', sa.Uuid(), nullable=True),
    sa.Column('superseded_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('(superseded_at IS NULL) = (superseded_by_evaluation_id IS NULL)', name=op.f('ck_data_gap_supersession_pair')),
    sa.CheckConstraint('end_at > start_at', name=op.f('ck_data_gap_interval_ordered')),
    sa.CheckConstraint('estimated_missing_samples >= 0', name=op.f('ck_data_gap_samples_not_negative')),
    sa.ForeignKeyConstraint(['evaluation_id'], ['detector_evaluation.evaluation_id'], name=op.f('fk_data_gap_evaluation_id_detector_evaluation')),
    sa.ForeignKeyConstraint(['sensor_id'], ['sensor.sensor_id'], name=op.f('fk_data_gap_sensor_id_sensor')),
    sa.ForeignKeyConstraint(['shipment_id'], ['shipment.shipment_id'], name=op.f('fk_data_gap_shipment_id_shipment')),
    sa.ForeignKeyConstraint(['superseded_by_evaluation_id'], ['detector_evaluation.evaluation_id'], name=op.f('fk_data_gap_superseded_by_evaluation_id_detector_evaluation')),
    sa.PrimaryKeyConstraint('gap_revision_id', name=op.f('pk_data_gap'))
    )
    op.create_index('ix_data_gap_shipment_id_sensor_id_start_at', 'data_gap', ['shipment_id', 'sensor_id', 'start_at'], unique=False)
    op.create_table('detection',
    sa.Column('detection_id', sa.Uuid(), nullable=False),
    sa.Column('run_key', sa.String(length=80), nullable=False),
    sa.Column('shipment_id', sa.String(length=60), nullable=False),
    sa.Column('sensor_id', sa.String(length=60), nullable=False),
    sa.Column('source', sa.Enum('POLICY_BASELINE', 'ML_MODEL', 'GAP_DETECTOR', 'MANUAL', name='detection_source', native_enum=False, create_constraint=True, length=40), nullable=False),
    sa.Column('direction', sa.Enum('HIGH', 'LOW', name='temperature_direction', native_enum=False, create_constraint=True, length=40), nullable=False),
    sa.Column('first_event_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_event_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('reading_count', sa.Integer(), nullable=False),
    sa.Column('observed_duration_s', sa.Numeric(precision=14, scale=6), nullable=False),
    sa.Column('threshold_min', sa.Integer(), nullable=False),
    sa.Column('meets_policy_duration', sa.Boolean(), nullable=False),
    sa.Column('confirmed_event_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('evidence_received_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('peak_c', sa.Numeric(precision=6, scale=2), nullable=False),
    sa.Column('run_open', sa.Boolean(), nullable=False),
    sa.Column('preceded_by_gap_key', sa.String(length=64), nullable=True),
    sa.Column('followed_by_gap_key', sa.String(length=64), nullable=True),
    sa.Column('evaluation_id', sa.Uuid(), nullable=False),
    sa.Column('raised_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('superseded_by_evaluation_id', sa.Uuid(), nullable=True),
    sa.Column('superseded_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('(superseded_at IS NULL) = (superseded_by_evaluation_id IS NULL)', name=op.f('ck_detection_supersession_pair')),
    sa.CheckConstraint('last_event_at >= first_event_at', name=op.f('ck_detection_interval_ordered')),
    sa.CheckConstraint('reading_count >= 1', name=op.f('ck_detection_reading_count_positive')),
    sa.ForeignKeyConstraint(['evaluation_id'], ['detector_evaluation.evaluation_id'], name=op.f('fk_detection_evaluation_id_detector_evaluation')),
    sa.ForeignKeyConstraint(['sensor_id'], ['sensor.sensor_id'], name=op.f('fk_detection_sensor_id_sensor')),
    sa.ForeignKeyConstraint(['shipment_id'], ['shipment.shipment_id'], name=op.f('fk_detection_shipment_id_shipment')),
    sa.ForeignKeyConstraint(['superseded_by_evaluation_id'], ['detector_evaluation.evaluation_id'], name=op.f('fk_detection_superseded_by_evaluation_id_detector_evaluation')),
    sa.PrimaryKeyConstraint('detection_id', name=op.f('pk_detection'))
    )
    op.create_index('ix_detection_shipment_id_sensor_id_first_event_at', 'detection', ['shipment_id', 'sensor_id', 'first_event_at'], unique=False)
    op.create_table('data_quality_warning',
    sa.Column('warning_revision_id', sa.Uuid(), nullable=False),
    sa.Column('warning_key', sa.String(length=200), nullable=False),
    sa.Column('kind', sa.Enum('GAP_ADJACENT_OUT_OF_RANGE', 'MISSING_READINGS', 'READING_CONFLICT', 'CONTEXT_CONFLICT', name='warning_kind', native_enum=False, create_constraint=True, length=40), nullable=False),
    sa.Column('affects_quality_evidence', sa.Boolean(), nullable=False),
    sa.Column('shipment_id', sa.String(length=60), nullable=False),
    sa.Column('sensor_id', sa.String(length=60), nullable=False),
    sa.Column('run_key', sa.String(length=80), nullable=True),
    sa.Column('gap_key', sa.String(length=64), nullable=True),
    sa.Column('interval_start_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('interval_end_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('linked_incident_id', sa.Uuid(), nullable=True),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('evaluation_id', sa.Uuid(), nullable=True),
    sa.Column('ingest_batch_id', sa.Uuid(), nullable=True),
    sa.Column('raised_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('superseded_by_evaluation_id', sa.Uuid(), nullable=True),
    sa.Column('superseded_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('(superseded_at IS NULL) = (superseded_by_evaluation_id IS NULL)', name=op.f('ck_data_quality_warning_supersession_pair')),
    sa.CheckConstraint('evaluation_id IS NOT NULL OR ingest_batch_id IS NOT NULL', name=op.f('ck_data_quality_warning_has_origin')),
    sa.CheckConstraint('interval_end_at >= interval_start_at', name=op.f('ck_data_quality_warning_interval_ordered')),
    sa.ForeignKeyConstraint(['evaluation_id'], ['detector_evaluation.evaluation_id'], name=op.f('fk_data_quality_warning_evaluation_id_detector_evaluation')),
    sa.ForeignKeyConstraint(['ingest_batch_id'], ['ingest_batch.batch_id'], name=op.f('fk_data_quality_warning_ingest_batch_id_ingest_batch')),
    sa.ForeignKeyConstraint(['linked_incident_id'], ['incident.incident_id'], name=op.f('fk_data_quality_warning_linked_incident_id_incident')),
    sa.ForeignKeyConstraint(['sensor_id'], ['sensor.sensor_id'], name=op.f('fk_data_quality_warning_sensor_id_sensor')),
    sa.ForeignKeyConstraint(['shipment_id'], ['shipment.shipment_id'], name=op.f('fk_data_quality_warning_shipment_id_shipment')),
    sa.ForeignKeyConstraint(['superseded_by_evaluation_id'], ['detector_evaluation.evaluation_id'], name=op.f('fk_data_quality_warning_superseded_by_evaluation_id_detector_evaluation')),
    sa.PrimaryKeyConstraint('warning_revision_id', name=op.f('pk_data_quality_warning'))
    )
    op.create_index('ix_data_quality_warning_shipment_id_sensor_id', 'data_quality_warning', ['shipment_id', 'sensor_id'], unique=False)
    op.create_table('incident_revision',
    sa.Column('incident_revision_id', sa.Uuid(), nullable=False),
    sa.Column('incident_id', sa.Uuid(), nullable=False),
    sa.Column('revision', sa.Integer(), nullable=False),
    sa.Column('extent_start_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('extent_end_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('extent_open', sa.Boolean(), nullable=False),
    sa.Column('direction', sa.Enum('HIGH', 'LOW', name='incident_direction', native_enum=False, create_constraint=True, length=40), nullable=True),
    sa.Column('observed_duration_s', sa.Numeric(precision=14, scale=6), nullable=True),
    sa.Column('bracketing_span_s', sa.Numeric(precision=14, scale=6), nullable=True),
    sa.Column('gap_status', sa.Enum('SHORT_GAP', 'UNKNOWN', 'UNKNOWN_REVIEW_REQUIRED', name='incident_gap_status', native_enum=False, create_constraint=True, length=40), nullable=True),
    sa.Column('peak_c', sa.Numeric(precision=6, scale=2), nullable=True),
    sa.Column('confirmed_event_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('evidence_received_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('gap_continuity_warning', sa.Boolean(), nullable=False),
    sa.Column('basis', sa.Enum('CURRENT', 'SUPERSEDED_BY_DATA', 'MERGED_INTO', name='incident_basis', native_enum=False, create_constraint=True, length=40), nullable=False),
    sa.Column('merged_into_incident_id', sa.Uuid(), nullable=True),
    sa.Column('basis_key', sa.String(length=80), nullable=False),
    sa.Column('detection_id', sa.Uuid(), nullable=True),
    sa.Column('gap_revision_id', sa.Uuid(), nullable=True),
    sa.Column('incident_status_at_revision', sa.String(length=10), nullable=False),
    sa.Column('evaluation_id', sa.Uuid(), nullable=False),
    sa.Column('raised_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("(basis = 'MERGED_INTO') = (merged_into_incident_id IS NOT NULL)", name=op.f('ck_incident_revision_merge_target')),
    sa.CheckConstraint('extent_end_at >= extent_start_at', name=op.f('ck_incident_revision_extent_ordered')),
    sa.CheckConstraint('revision >= 1', name=op.f('ck_incident_revision_revision_positive')),
    sa.ForeignKeyConstraint(['detection_id'], ['detection.detection_id'], name=op.f('fk_incident_revision_detection_id_detection')),
    sa.ForeignKeyConstraint(['evaluation_id'], ['detector_evaluation.evaluation_id'], name=op.f('fk_incident_revision_evaluation_id_detector_evaluation')),
    sa.ForeignKeyConstraint(['gap_revision_id'], ['data_gap.gap_revision_id'], name=op.f('fk_incident_revision_gap_revision_id_data_gap')),
    sa.ForeignKeyConstraint(['incident_id'], ['incident.incident_id'], name=op.f('fk_incident_revision_incident_id_incident')),
    sa.ForeignKeyConstraint(['merged_into_incident_id'], ['incident.incident_id'], name=op.f('fk_incident_revision_merged_into_incident_id_incident')),
    sa.PrimaryKeyConstraint('incident_revision_id', name=op.f('pk_incident_revision')),
    sa.UniqueConstraint('incident_id', 'revision', name=op.f('uq_incident_revision_incident_id_revision'))
    )
    op.create_table('decision_reassessment',
    sa.Column('reassessment_id', sa.Uuid(), nullable=False),
    sa.Column('disposition_id', sa.Uuid(), nullable=False),
    sa.Column('shipment_id', sa.String(length=60), nullable=False),
    sa.Column('incident_id', sa.Uuid(), nullable=False),
    sa.Column('incident_revision_id', sa.Uuid(), nullable=False),
    sa.Column('reason', sa.Enum('INCIDENT_EVIDENCE_REVISED', 'NEW_INCIDENT_AFTER_DISPOSITION', name='reassessment_reason', native_enum=False, create_constraint=True, length=40), nullable=False),
    sa.Column('warehouse_release_id', sa.Uuid(), nullable=True),
    sa.Column('evaluation_id', sa.Uuid(), nullable=False),
    sa.Column('raised_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['disposition_id'], ['disposition.disposition_id'], name=op.f('fk_decision_reassessment_disposition_id_disposition')),
    sa.ForeignKeyConstraint(['evaluation_id'], ['detector_evaluation.evaluation_id'], name=op.f('fk_decision_reassessment_evaluation_id_detector_evaluation')),
    sa.ForeignKeyConstraint(['incident_id'], ['incident.incident_id'], name=op.f('fk_decision_reassessment_incident_id_incident')),
    sa.ForeignKeyConstraint(['incident_revision_id'], ['incident_revision.incident_revision_id'], name=op.f('fk_decision_reassessment_incident_revision_id_incident_revision')),
    sa.ForeignKeyConstraint(['shipment_id'], ['shipment.shipment_id'], name=op.f('fk_decision_reassessment_shipment_id_shipment')),
    sa.ForeignKeyConstraint(['warehouse_release_id'], ['warehouse_release.release_id'], name=op.f('fk_decision_reassessment_warehouse_release_id_warehouse_release')),
    sa.PrimaryKeyConstraint('reassessment_id', name=op.f('pk_decision_reassessment')),
    sa.UniqueConstraint('disposition_id', 'incident_revision_id', name=op.f('uq_decision_reassessment_disposition_id_incident_revision_id'))
    )
    op.add_column('incident', sa.Column('sensor_id', sa.String(length=60), nullable=True))
    op.add_column('incident', sa.Column('detector_config_id', sa.Uuid(), nullable=True))
    op.add_column('incident', sa.Column('opened_by_evaluation_id', sa.Uuid(), nullable=True))
    op.create_index('ix_incident_shipment_id', 'incident', ['shipment_id'], unique=False)
    op.create_foreign_key(op.f('fk_incident_sensor_id_sensor'), 'incident', 'sensor', ['sensor_id'], ['sensor_id'])
    op.create_foreign_key(op.f('fk_incident_detector_config_id_detector_config'), 'incident', 'detector_config', ['detector_config_id'], ['detector_config_id'])
    op.create_foreign_key(op.f('fk_incident_opened_by_evaluation_id_detector_evaluation'), 'incident', 'detector_evaluation', ['opened_by_evaluation_id'], ['evaluation_id'])
    op.add_column('ingest_batch', sa.Column('duplicate_count', sa.Integer(), server_default=sa.text('0'), nullable=False))
    op.add_column('ingest_batch', sa.Column('ingest_mode', sa.Enum('IMPORT', 'LIVE', 'REPLAY', name='ingest_mode', native_enum=False, create_constraint=False, length=40), server_default='IMPORT', nullable=False))
    op.create_check_constraint(op.f('ck_ingest_batch_ingest_mode'), 'ingest_batch',
                               "ingest_mode IN ('IMPORT', 'LIVE', 'REPLAY')")
    op.drop_constraint(op.f('ck_ingest_batch_counts_consistent'), 'ingest_batch', type_='check')
    op.create_check_constraint(
        op.f('ck_ingest_batch_counts_consistent'), 'ingest_batch',
        'record_count >= 0 AND accepted_count >= 0 AND rejected_count >= 0 AND duplicate_count >= 0 '
        'AND accepted_count + rejected_count + duplicate_count <= record_count')


def downgrade() -> None:
    op.drop_constraint(op.f('ck_ingest_batch_counts_consistent'), 'ingest_batch', type_='check')
    op.create_check_constraint(
        op.f('ck_ingest_batch_counts_consistent'), 'ingest_batch',
        'record_count >= 0 AND accepted_count >= 0 AND rejected_count >= 0 '
        'AND accepted_count + rejected_count <= record_count')
    op.drop_constraint(op.f('ck_ingest_batch_ingest_mode'), 'ingest_batch', type_='check')
    op.drop_column('ingest_batch', 'ingest_mode')
    op.drop_column('ingest_batch', 'duplicate_count')
    op.drop_constraint(op.f('fk_incident_opened_by_evaluation_id_detector_evaluation'), 'incident', type_='foreignkey')
    op.drop_constraint(op.f('fk_incident_detector_config_id_detector_config'), 'incident', type_='foreignkey')
    op.drop_constraint(op.f('fk_incident_sensor_id_sensor'), 'incident', type_='foreignkey')
    op.drop_index('ix_incident_shipment_id', table_name='incident')
    op.drop_column('incident', 'opened_by_evaluation_id')
    op.drop_column('incident', 'detector_config_id')
    op.drop_column('incident', 'sensor_id')
    op.drop_table('decision_reassessment')
    op.drop_table('incident_revision')
    op.drop_index('ix_data_quality_warning_shipment_id_sensor_id', table_name='data_quality_warning')
    op.drop_table('data_quality_warning')
    op.drop_index('ix_detection_shipment_id_sensor_id_first_event_at', table_name='detection')
    op.drop_table('detection')
    op.drop_index('ix_data_gap_shipment_id_sensor_id_start_at', table_name='data_gap')
    op.drop_table('data_gap')
    op.drop_index('ix_detector_evaluation_shipment_id_sensor_id_as_of', table_name='detector_evaluation')
    op.drop_table('detector_evaluation')
    op.drop_table('detector_config')
