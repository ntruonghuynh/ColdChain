import type {
  Envelope,
  ErrorBody,
  HealthReport,
  ListEnvelope,
  Organization,
  Policy,
  Shipment,
  SystemInfo,
} from './types';

/** Same-origin base path. nginx (Docker) or the Vite dev proxy forwards it to the backend. */
export const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? '/api';

const DEFAULT_TIMEOUT_MS = 10_000;

export type ApiErrorKind = 'http' | 'network' | 'timeout' | 'invalid_response';

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
      headers: { Accept: 'application/json' },
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
  return new ApiError({ kind: 'http', status, code: `http_${status}`, message: `Request failed (HTTP ${status}).` });
}

export async function apiGet<T>(path: string, opts?: RequestOptions): Promise<T> {
  const { status, body } = await request(path, opts);
  if (status < 200 || status >= 300) throw toHttpError(status, body);
  return body as T;
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
};
