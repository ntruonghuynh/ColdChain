// Mirrors backend/app/api/schemas.py. Keep in sync when the API changes.

export interface ListMeta {
  total: number;
  limit: number;
  offset: number;
}

export interface Envelope<T> {
  data: T;
  meta: Record<string, unknown> | null;
}

export interface ListEnvelope<T> {
  data: T[];
  meta: ListMeta;
}

export interface ErrorBody {
  code: string;
  message: string;
  details: unknown;
  request_id: string | null;
}

export interface DatabaseHealth {
  status: 'ok' | 'unavailable' | 'migration_pending';
  latency_ms: number | null;
  migration_revision: string | null;
  expected_revision: string | null;
  detail: string | null;
}

export interface HealthReport {
  status: 'ok' | 'degraded';
  api: 'ok';
  database: DatabaseHealth;
  checked_at: string;
}

export interface FeatureStatus {
  key: string;
  name: string;
  status: 'available' | 'not_implemented';
  milestone: string;
  note: string | null;
}

export interface SystemInfo {
  app_name: string;
  version: string;
  milestone: string;
  environment: string;
  server_time: string;
  features: FeatureStatus[];
}

export interface Policy {
  policy_id: string;
  policy_code: string;
  policy_version: string;
  product_id: string;
  product_name: string;
  status: string;
  limits: { min_temp_c: string; max_temp_c: string };
  duration_rule: { high_excursion_min_duration_min: number; low_excursion_min_duration_min: number };
  missing_data_rule: { gap_unknown_after_min: number; gap_review_at_min: number };
  release_authority_role: string;
  procedure_version: string;
  effective_from: string;
  is_teaching_policy: boolean;
  disclaimer: string;
  approval_reference: string;
  source_file: string;
  content_sha256: string;
}

export interface OrganizationUser {
  username: string;
  display_name: string;
  roles: string[];
  is_demo_user: boolean;
  has_credentials: boolean;
}

export interface Organization {
  org_id: string;
  name: string;
  org_type: string;
  users: OrganizationUser[];
}

export interface Shipment {
  shipment_id: string;
  product_id: string;
  policy_id: string;
  shipper_org_id: string;
  carrier_org_id: string;
  receiver_org_id: string;
  origin: string | null;
  destination: string | null;
  status: string;
  data_origin: 'SIMULATED' | 'MEASURED';
  source_dataset_id?: string | null;
  created_at: string;
}

// ---------- Milestone 3: monitoring (mirrors backend/app/api/monitoring_schemas.py) ----------

export type MonitoringState = 'NOT_STARTED' | 'CURRENT' | 'STALE' | 'UNKNOWN' | 'ENDED';
export type GapStatus = 'SHORT_GAP' | 'UNKNOWN' | 'UNKNOWN_REVIEW_REQUIRED';
export type RecordState = 'CURRENT' | 'SUPERSEDED';

export interface PolicyRef {
  policy_id: string | null;
  policy_code: string;
  policy_version: string;
  content_sha256: string;
  min_temp_c: string;
  max_temp_c: string;
  high_excursion_min_duration_min: number;
  low_excursion_min_duration_min: number;
  gap_unknown_after_min: number;
  gap_review_at_min: number;
}

export interface DetectorConfigRef {
  detector_config_id: string | null;
  detector_code: string;
  config_version: string;
  content_sha256: string;
  nominal_sampling_interval_s: number;
  max_continuous_interval_s: number;
}

export type CommunicationStatus =
  | 'NOT_STARTED'
  | 'ENDED'
  | 'NO_UPLOAD_YET'
  | 'PATTERN_NOT_ESTABLISHED'
  | 'WITHIN_RECENT_UPLOAD_INTERVALS'
  | 'LONGER_THAN_RECENT_UPLOAD_INTERVALS';

/** Presentation only: facts about received uploads; never a detector rule. */
export interface Communication {
  status: CommunicationStatus;
  last_upload_received_at: string | null;
  since_last_upload_s: string | null;
  observed_upload_interval_s: string | null;
  longest_recent_upload_interval_s: string | null;
  recent_intervals_used: number;
  expected_schedule_configured: boolean;
}

export interface SensorStatus {
  shipment_id: string;
  sensor_id: string;
  as_of: string;
  state: MonitoringState;
  newest_event_at: string | null;
  newest_received_at: string | null;
  visible_reading_count: number;
  unobserved_since_at: string | null;
  unobserved_duration_s: string | null;
  provisional_review_threshold_reached: boolean;
  end_boundary_established: boolean;
  monitoring_window: { assigned_from: string | null; assigned_to: string | null };
  confirmed_gaps: Record<GapStatus, number>;
  confirmed_gap_span_s: string;
  note: string;
  last_observed_temperature_c: string | null;
  last_observed_event_at: string | null;
  last_observed_temperature_state: 'IN_RANGE' | 'HIGH' | 'LOW' | null;
  communication: Communication;
  open_incidents_as_of: Record<string, number>;
}

export interface ReadingPoint {
  event_at: string;
  received_at: string;
  temperature_c: string;
  batch_ref: string;
  delivery_lag_s: string;
  temperature_state: 'IN_RANGE' | 'HIGH' | 'LOW' | null;
  inside_extent?: boolean | null;
}

export interface DataGap {
  gap_key: string;
  sensor_id: string;
  start_at: string;
  end_at: string;
  start_bound: string;
  end_bound: string;
  bracketing_span_s: string;
  bracketing_span_min: number;
  estimated_missing_samples: number;
  estimated_missing_duration_s: number;
  gap_status: GapStatus;
  out_of_range_before: boolean;
  out_of_range_after: boolean;
  raised_at: string;
  superseded_at: string | null;
  state: RecordState;
}

export interface TemperatureRun {
  run_key: string;
  sensor_id: string;
  source: string;
  direction: 'HIGH' | 'LOW';
  first_event_at: string;
  last_event_at: string;
  reading_count: number;
  observed_duration_s: string;
  observed_duration_min: number;
  threshold_min: number;
  meets_policy_duration: boolean;
  confirmed_event_at: string | null;
  evidence_received_at: string | null;
  peak_c: string;
  run_open: boolean;
  preceded_by_gap_key: string | null;
  followed_by_gap_key: string | null;
  raised_at: string;
  superseded_at: string | null;
  state: RecordState;
}

export interface DataQualityWarning {
  warning_key: string;
  kind: string;
  affects_quality_evidence: boolean;
  sensor_id: string;
  interval_start_at: string;
  interval_end_at: string;
  linked_incident_id: string | null;
  message: string;
  details: Record<string, unknown> | null;
  raised_at: string;
  superseded_at: string | null;
  state: RecordState;
}

export interface SensorTelemetry {
  sensor_id: string;
  status: SensorStatus;
  readings: ReadingPoint[];
  gaps: DataGap[];
  runs: TemperatureRun[];
}

export interface Telemetry {
  shipment_id: string;
  data_origin: 'SIMULATED' | 'MEASURED';
  as_of: string;
  policy: PolicyRef;
  detector_config: DetectorConfigRef;
  sensors: SensorTelemetry[];
}

export interface IncidentRevision {
  revision: number;
  extent_start_at: string;
  extent_end_at: string;
  extent_open: boolean;
  direction: 'HIGH' | 'LOW' | null;
  observed_duration_s: string | null;
  observed_duration_min: number | null;
  bracketing_span_s: string | null;
  bracketing_span_min: number | null;
  gap_status: GapStatus | null;
  peak_c: string | null;
  confirmed_event_at: string | null;
  evidence_received_at: string | null;
  gap_continuity_warning: boolean;
  basis: 'CURRENT' | 'SUPERSEDED_BY_DATA' | 'MERGED_INTO';
  merged_into_incident_id: string | null;
  incident_status_at_revision: string;
  evaluation_id: string;
  raised_at: string;
}

export interface Incident {
  incident_id: string;
  business_ref: string;
  shipment_id: string;
  sensor_id: string | null;
  category: 'TEMPERATURE_EXCURSION' | 'DATA_GAP' | 'SENSOR_FAULT_SUSPECTED';
  status: 'OPEN' | 'CLOSED';
  opened_at: string;
  closed_at: string | null;
  detected_by: string;
  detector_version: string | null;
  summary: string | null;
  data_origin: 'SIMULATED' | 'MEASURED' | null;
  policy_code: string | null;
  policy_version: string | null;
  latest: IncidentRevision | null;
  review_state: 'PENDING_QUALITY_REVIEW' | 'CLOSED_BY_QUALITY_DISPOSITION';
}

export interface IncidentDetail extends Incident {
  revisions: IncidentRevision[];
  evidence: { readings: ReadingPoint[]; gaps: DataGap[]; warnings: DataQualityWarning[] };
  policy: PolicyRef | null;
  detector_config: DetectorConfigRef | null;
  opening_evaluation: {
    evaluation_id: string;
    mode: string;
    trigger: string;
    as_of: string;
    input_fingerprint: string;
    detector_code_version: string;
    visible_reading_count: number;
  } | null;
  dispositions: { disposition_id: string; business_ref: string; decision: string; decided_at: string }[];
  reassessments: {
    reassessment_id: string;
    disposition_id: string;
    reason: string;
    incident_revision_id: string;
    warehouse_release_id: string | null;
    raised_at: string;
  }[];
}

export interface MonitoringSummary {
  as_of: string;
  shipments_total: number;
  shipments_evaluated: number;
  sensors_by_monitoring_state: Record<MonitoringState, number>;
  open_incidents_by_category: Record<string, number>;
  open_incidents_by_basis: Record<string, number>;
  current_warnings_by_kind: Record<string, number>;
  current_evidence_warnings: number;
  batches_total: number;
  rejected_records_total: number;
  duplicates_ignored_total: number;
  readings_total: number;
  detector_config: DetectorConfigRef | null;
}
