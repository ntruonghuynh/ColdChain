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
  created_at: string;
}
