import type {
  Envelope,
  ErrorBody,
  HealthReport,
  Incident,
  IncidentDetail,
  ListEnvelope,
  MonitoringSummary,
  Organization,
  Policy,
  Shipment,
  SystemInfo,
  Telemetry,
} from './types';

/** Same-origin base path. nginx (Docker) or the Vite dev proxy forwards it to the backend. */
export const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? '/api';

const DEFAULT_TIMEOUT_MS = 10_000;

export type ApiErrorKind = 'http' | 'network' | 'timeout' | 'invalid_response';

let bearerToken: string | null = null;

/** Keep bearer tokens in memory only; reloading the page requires a fresh sign-in. */
export function setBearerToken(token: string | null): void {
  bearerToken = token;
}

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status: number | null;
  readonly code: string;
  readonly details: unknown;
  readonly requestId: string | null;

  constructor(opts: {
    kind: ApiErrorKind;
    message: string;
    status?: number | null;
    code?: string;
    details?: unknown;
    requestId?: string | null;
  }) {
    super(opts.message);
    this.name = 'ApiError';
    this.kind = opts.kind;
    this.status = opts.status ?? null;
    this.code = opts.code ?? opts.kind;
    this.details = opts.details ?? null;
    this.requestId = opts.requestId ?? null;
  }
}

interface RequestOptions {
  signal?: AbortSignal;
  timeoutMs?: number;
  unauthenticated?: boolean;
}

function isErrorBody(value: unknown): value is { error: ErrorBody } {
  return (
    typeof value === 'object' &&
    value !== null &&
    'error' in value &&
    typeof (value as { error: unknown }).error === 'object'
  );
}

/** Low-level request. Returns the parsed JSON body and HTTP status, or throws ApiError. */
async function request(path: string, opts: RequestOptions = {}): Promise<{ status: number; body: unknown }> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort('timeout'), opts.timeoutMs ?? DEFAULT_TIMEOUT_MS);
  const onAbort = () => controller.abort(opts.signal?.reason);
  opts.signal?.addEventListener('abort', onAbort);

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      headers: {
        Accept: 'application/json',
        ...(bearerToken && !opts.unauthenticated ? { Authorization: `Bearer ${bearerToken}` } : {}),
      },
      signal: controller.signal,
    });
  } catch (err) {
    if (controller.signal.aborted && controller.signal.reason === 'timeout') {
      throw new ApiError({ kind: 'timeout', message: 'The API did not respond in time.' });
    }
    if (opts.signal?.aborted) throw err; // caller cancelled; propagate as-is
    throw new ApiError({ kind: 'network', message: 'Cannot reach the API. Check that the system is running.' });
  } finally {
    clearTimeout(timeout);
    opts.signal?.removeEventListener('abort', onAbort);
  }

  let body: unknown;
  try {
    body = await response.json();
  } catch {
    throw new ApiError({
      kind: 'invalid_response',
      status: response.status,
      message: `The API returned an unreadable response (HTTP ${response.status}).`,
    });
  }
  return { status: response.status, body };
}

function toHttpError(status: number, body: unknown): ApiError {
  if (isErrorBody(body)) {
    return new ApiError({
      kind: 'http',
      status,
      code: body.error.code,
      message: body.error.message,
      details: body.error.details,
      requestId: body.error.request_id,
    });
  }
  if (status === 401) {
    return new ApiError({ kind: 'http', status, code: 'unauthorized', message: 'Your session expired or is not signed in. Please sign in again.' });
  }
  if (status === 403) {
    return new ApiError({ kind: 'http', status, code: 'forbidden', message: 'This account is not authorized for this action.' });
  }
  return new ApiError({ kind: 'http', status, code: `http_${status}`, message: `Request failed (HTTP ${status}).` });
}

export async function apiGet<T>(path: string, opts?: RequestOptions): Promise<T> {
  const { status, body } = await request(path, opts);
  if (status < 200 || status >= 300) {
    if (status === 401 && bearerToken) {
      setBearerToken(null);
      window.dispatchEvent(new Event('coldchain:unauthorized'));
    }
    throw toHttpError(status, body);
  }
  return body as T;
}

export async function apiPost<T>(path: string, payload: unknown, opts: RequestOptions = {}): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort('timeout'), opts.timeoutMs ?? DEFAULT_TIMEOUT_MS);
  const onAbort = () => controller.abort(opts.signal?.reason);
  opts.signal?.addEventListener('abort', onAbort);
  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      method: 'POST',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
        ...(bearerToken && !opts.unauthenticated ? { Authorization: `Bearer ${bearerToken}` } : {}),
      },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
    let body: unknown;
    try {
      body = await response.json();
    } catch {
      throw new ApiError({ kind: 'invalid_response', status: response.status, message: `The API returned an unreadable response (HTTP ${response.status}).` });
    }
    if (response.status < 200 || response.status >= 300) {
      if (response.status === 401 && bearerToken && !opts.unauthenticated) {
        setBearerToken(null);
        window.dispatchEvent(new Event('coldchain:unauthorized'));
      }
      throw toHttpError(response.status, body);
    }
    return body as T;
  } catch (err) {
    if (err instanceof ApiError) throw err;
    if (controller.signal.aborted && controller.signal.reason === 'timeout') {
      throw new ApiError({ kind: 'timeout', message: 'The API did not respond in time.' });
    }
    if (opts.signal?.aborted) throw err;
    throw new ApiError({ kind: 'network', message: 'Cannot reach the API. Check that the system is running.' });
  } finally {
    clearTimeout(timeout);
    opts.signal?.removeEventListener('abort', onAbort);
  }
}

/**
 * Health is special: the backend answers 503 with a full report when a dependency
 * (database, migrations) is not ready, so both 200 and 503 bodies are returned.
 */
export async function getHealth(opts?: RequestOptions): Promise<HealthReport> {
  const { status, body } = await request('/health', { timeoutMs: 5_000, ...opts });
  if ((status === 200 || status === 503) && typeof body === 'object' && body !== null && 'data' in body) {
    return (body as Envelope<HealthReport>).data;
  }
  throw toHttpError(status, body);
}

export const api = {
  login: (username: string, password: string) =>
    apiPost<Envelope<LoginResponse>>('/auth/login', { username, password }, { unauthenticated: true }),
  me: (opts?: RequestOptions) => apiGet<Envelope<AuthIdentity>>('/auth/me', opts),
  systemInfo: (opts?: RequestOptions) => apiGet<Envelope<SystemInfo>>('/system/info', opts),
  policies: (status?: string, opts?: RequestOptions) =>
    apiGet<ListEnvelope<Policy>>(`/policies${status ? `?status=${encodeURIComponent(status)}` : ''}`, opts),
  organizations: (opts?: RequestOptions) => apiGet<ListEnvelope<Organization>>('/organizations', opts),
  shipments: (params: { limit?: number; offset?: number } = {}, opts?: RequestOptions) => {
    const query = new URLSearchParams();
    if (params.limit !== undefined) query.set('limit', String(params.limit));
    if (params.offset !== undefined) query.set('offset', String(params.offset));
    const qs = query.toString();
    return apiGet<ListEnvelope<Shipment>>(`/shipments${qs ? `?${qs}` : ''}`, opts);
  },
  telemetry: (shipmentId: string, asOf?: string, opts?: RequestOptions) =>
    apiGet<Envelope<Telemetry>>(
      `/shipments/${encodeURIComponent(shipmentId)}/telemetry${asOf ? `?as_of=${encodeURIComponent(asOf)}` : ''}`,
      opts,
    ),
  incidents: (
    params: { status?: string; category?: string; shipmentId?: string; limit?: number; offset?: number } = {},
    opts?: RequestOptions,
  ) => {
    const query = new URLSearchParams();
    if (params.status) query.set('status', params.status);
    if (params.category) query.set('category', params.category);
    if (params.shipmentId) query.set('shipment_id', params.shipmentId);
    if (params.limit !== undefined) query.set('limit', String(params.limit));
    if (params.offset !== undefined) query.set('offset', String(params.offset));
    const qs = query.toString();
    return apiGet<ListEnvelope<Incident>>(`/incidents${qs ? `?${qs}` : ''}`, opts);
  },
  incident: (incidentId: string, opts?: RequestOptions) =>
    apiGet<Envelope<IncidentDetail>>(`/incidents/${encodeURIComponent(incidentId)}`, opts),
  monitoringSummary: (opts?: RequestOptions) => apiGet<Envelope<MonitoringSummary>>('/monitoring/summary', opts),
  modelReadiness: (opts?: RequestOptions) => apiGet<Envelope<ModelReadiness>>('/predictions/model', opts),
  explanationHistory: (incidentId: string, opts?: RequestOptions) =>
    apiGet<Envelope<ExplanationHistoryItem[]>>(`/llm/incidents/${encodeURIComponent(incidentId)}/explanations`, opts),
  explanation: (explanationId: string, opts?: RequestOptions) =>
    apiGet<Envelope<StoredExplanation>>(`/llm/explanations/${encodeURIComponent(explanationId)}`, opts),
  transactions: (limit = 100, opts?: RequestOptions) =>
    apiGet<Envelope<LedgerTransaction[]>>(`/ledger/transactions?limit=${limit}`, opts),
  auditHistory: (limit = 100, opts?: RequestOptions) =>
    apiGet<Envelope<AuditEntry[]>>(`/ledger/audit?limit=${limit}`, opts),
  verifyBusinessRef: (businessRef: string, opts?: RequestOptions) =>
    apiGet<Envelope<BusinessVerification>>(`/ledger/verify/${encodeURIComponent(businessRef)}`, opts),
  reconcile: (opts?: RequestOptions) => apiGet<Envelope<Reconciliation>>('/ledger/reconciliation', opts),
  verifyAudit: (opts?: RequestOptions) => apiGet<Envelope<AuditVerification>>('/ledger/audit/verify', opts),
  disposition: (shipmentId: string, payload: DispositionRequest) =>
    apiPost<Envelope<WorkflowResult>>(`/workflow/shipments/${encodeURIComponent(shipmentId)}/disposition`, payload),
  release: (shipmentId: string, business_ref: string) =>
    apiPost<Envelope<WorkflowResult>>(`/workflow/shipments/${encodeURIComponent(shipmentId)}/release`, { business_ref }),
};

export interface LoginResponse { access_token: string; token_type: 'bearer'; expires_in_seconds: number; username: string; organization_id: string; roles: string[] }
export interface AuthIdentity { user_id: string; username: string; organization_id: string; roles: string[] }
export interface ModelReadiness { status: 'ready' | 'unavailable'; model_version: string; detail: string | null }
export interface ExplanationHistoryItem { explanation_id: string; explanation_status: string; source_mode: string; provider: string; model: string | null; prompt_version: string; explained_at: string; evidence_cutoff_at: string; citation_verification: string }
export interface StoredExplanation {
  explanation_id: string; shipment_id: string; incident_id: string; incident_ref: string; explained_at: string; evidence_cutoff_at: string;
  explanation_status: 'draft' | 'insufficient_evidence' | 'not_configured' | 'provider_error' | 'fallback'; source_mode: 'llm' | 'deterministic_fallback' | 'none'; provider: string; model: string | null;
  prompt_version: string; policy_version: string; procedure_version: string; sensor_interval_start_at: string; sensor_interval_end_at: string;
  evidence_references: string[]; document_versions: string[]; citation_verification: 'passed' | 'failed' | 'not_applicable';
  summary_vi: string; observations_vi: string[]; policy_findings_vi: string[]; ml_advisories_vi: string[]; potential_factors_vi: string[];
  recommended_steps_vi: string[]; evidence_needed_vi: string[]; unknowns_vi: string[]; citations: { source_id: string; claim: string; quote: string | null }[];
  validation_diagnostics: { application_validation_status: string; citation_validation_status: string; evidence_validation_status: string; temporal_validation_status: string; provider_call_status: string };
}
export interface LedgerTransaction { event_id: string; business_ref: string; event_type: string; shipment_id: string; outbox_status: string; attempts: number; last_error: string | null; transaction: { chain_id: number; contract_address: string; tx_hash: string; block_number: number; confirmed_at: string } | null }
export interface AuditEntry { sequence_no: number; business_ref: string; actor_user_id: string | null; actor_org_id: string | null; action: string; record: Record<string, unknown>; previous_hash: string; entry_hash: string; signature: string; public_key: string; created_at: string }
export interface BusinessVerification { business_ref: string; event_type: string; outbox_status: string; chain_record_present: boolean; verified: boolean; verification_status: string; database_payload_sha256?: string; evidence_sha256?: string | null }
export interface Reconciliation { checked_at: string; chain_connected: boolean; event_count: number; counts_by_finding: Record<string, number>; findings: { business_ref: string; event_type: string; shipment_id: string; outbox_status: string; chain_record_present: boolean; attempt_count: number; finding: string; detail: string | null }[] }
export interface AuditVerification { valid: boolean; entry_count: number; [key: string]: unknown }
export interface DispositionRequest { business_ref: string; decision: 'RELEASE' | 'QUARANTINE'; rationale: string; incident_refs: string[] }
export interface WorkflowResult { business_ref: string; event_id: string; idempotent_replay: boolean; status: string }
