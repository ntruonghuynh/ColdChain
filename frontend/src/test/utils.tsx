import { render } from '@testing-library/react';
import type { ReactElement } from 'react';
import { MemoryRouter } from 'react-router';
import { vi } from 'vitest';
import { ConnectivityProvider } from '../hooks/connectivity';
import type { HealthReport, Policy } from '../api/types';

export type MockResponse = { status: number; body: unknown } | Error;

/** Replaces global fetch. Keys are request paths (with query), e.g. "/api/shipments?limit=1". */
export function mockFetch(routes: Record<string, MockResponse>) {
  const fn = vi.fn(async (input: RequestInfo | URL) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
    const path = url.replace(/^https?:\/\/[^/]+/, '');
    const route = routes[path];
    if (route === undefined) {
      return new Response(JSON.stringify({ error: { code: 'not_found', message: `No mock for ${path}`, details: null, request_id: null } }), { status: 404 });
    }
    if (route instanceof Error) throw route;
    return new Response(JSON.stringify(route.body), { status: route.status, headers: { 'Content-Type': 'application/json' } });
  });
  vi.stubGlobal('fetch', fn);
  return fn;
}

export function renderApp(ui: ReactElement, route = '/') {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <ConnectivityProvider intervalMs={60_000}>{ui}</ConnectivityProvider>
    </MemoryRouter>,
  );
}

export const healthOk: HealthReport = {
  status: 'ok',
  api: 'ok',
  database: { status: 'ok', latency_ms: 1.2, migration_revision: '0001', expected_revision: '0001', detail: null },
  checked_at: '2026-11-14T00:00:00Z',
};

/** Deliberately NOT the real seeded values, to prove the UI renders what the API returns. */
export const testPolicy: Policy = {
  policy_id: '00000000-0000-0000-0000-000000000001',
  policy_code: 'POL-TEST',
  policy_version: '7.3',
  product_id: 'PRD-TEST',
  product_name: 'Test product',
  status: 'ACTIVE',
  limits: { min_temp_c: '3.50', max_temp_c: '7.50' },
  duration_rule: { high_excursion_min_duration_min: 45, low_excursion_min_duration_min: 20 },
  missing_data_rule: { gap_unknown_after_min: 12, gap_review_at_min: 33 },
  release_authority_role: 'QUALITY',
  procedure_version: 'SOP-TEST',
  effective_from: '2026-01-01T00:00:00Z',
  is_teaching_policy: true,
  disclaimer: 'Test disclaimer text.',
  approval_reference: 'test',
  source_file: 'test.json',
  content_sha256: 'a'.repeat(64),
};

export const emptyList = { data: [], meta: { total: 0, limit: 50, offset: 0 } };
