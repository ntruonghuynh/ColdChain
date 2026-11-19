import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { AppRoutes } from '../App';
import { NAV_ITEMS } from '../navigation';
import { emptyList, healthOk, mockFetch, renderApp, testPolicy } from '../test/utils';

const systemInfo = {
  data: {
    app_name: 'Test',
    version: '0.1.0',
    milestone: 'M1',
    environment: 'test',
    server_time: '2026-11-14T00:00:00Z',
    features: [
      { key: 'database', name: 'Database and migrations', status: 'available', milestone: 'M1', note: null },
      { key: 'ml', name: 'ML excursion detection', status: 'not_implemented', milestone: 'M4', note: null },
    ],
  },
  meta: null,
};

const baseRoutes = {
  '/api/health': { status: 200, body: { data: healthOk, meta: null } },
  '/api/system/info': { status: 200, body: systemInfo },
  '/api/policies?status=ACTIVE': { status: 200, body: { data: [testPolicy], meta: { total: 1, limit: 1, offset: 0 } } },
  '/api/shipments?limit=1': { status: 200, body: { ...emptyList, meta: { total: 0, limit: 1, offset: 0 } } },
  '/api/shipments?limit=25&offset=0': { status: 200, body: { ...emptyList, meta: { total: 0, limit: 25, offset: 0 } } },
  '/api/shipments?limit=500&offset=0': { status: 200, body: { ...emptyList, meta: { total: 0, limit: 500, offset: 0 } } },
};

describe('application shell', () => {
  it('shows all seven navigation entries', () => {
    mockFetch(baseRoutes);
    renderApp(<AppRoutes />);
    const nav = screen.getByRole('complementary', { name: 'Main navigation' });
    for (const item of NAV_ITEMS) {
      expect(within(nav).getByRole('link', { name: new RegExp(item.label) })).toBeInTheDocument();
    }
    expect(NAV_ITEMS.map((i) => i.label)).toEqual([
      'Overview', 'Shipments', 'Temperature Monitoring', 'Excursion Queue', 'Quality Review', 'Audit History', 'System Settings',
    ]);
  });

  it('shows the authenticated quality queue without placeholder content', async () => {
    mockFetch({ ...baseRoutes, '/api/incidents?status=OPEN&limit=500': { status: 200, body: { data: [], meta: { total: 0, limit: 500, offset: 0 } } } });
    renderApp(<AppRoutes />, '/quality-review');
    expect(await screen.findByText('No open incidents')).toBeInTheDocument();
    expect(screen.queryByText('Not implemented yet')).not.toBeInTheDocument();
    expect(screen.getAllByRole('link', { name: 'Sign in' })).toHaveLength(2);
  });

  it('keeps ledger reads behind sign-in and removes the audit placeholder', () => {
    mockFetch(baseRoutes);
    renderApp(<AppRoutes />, '/audit');
    expect(screen.getByRole('heading', { level: 1, name: 'Audit History' })).toBeInTheDocument();
    expect(screen.getByText(/Sign in to read ledger and signed-audit records/)).toBeInTheDocument();
    expect(screen.queryByText('Not implemented yet')).not.toBeInTheDocument();
  });

  it('shows a not-found page for unknown routes', () => {
    mockFetch(baseRoutes);
    renderApp(<AppRoutes />, '/no-such-page');
    expect(screen.getAllByText('Page not found')).toHaveLength(2); // header title + page body
    expect(screen.getByRole('link', { name: 'Go to the overview' })).toBeInTheDocument();
  });
});

describe('authentication and quality authorization', () => {
  it('logs in, resolves the backend identity and requires a second confirmation for disposition', async () => {
    const user = userEvent.setup();
    const incident = {
      incident_id: 'inc-demo', business_ref: 'INC-DEMO-1', shipment_id: 'SHP-DEMO-1', sensor_id: 'SNS-1',
      category: 'DATA_GAP', status: 'OPEN', opened_at: '2026-11-18T10:00:00Z', closed_at: null,
      detected_by: 'POLICY_BASELINE', detector_version: 'DET-BASELINE', summary: 'Missing data requires review.',
      data_origin: 'SIMULATED', policy_code: 'POL-1', policy_version: '1.0', latest: {
        revision: 1, extent_start_at: '2026-11-18T09:00:00Z', extent_end_at: '2026-11-18T09:40:00Z', extent_open: false,
        direction: null, observed_duration_s: null, observed_duration_min: null, bracketing_span_s: '2400', bracketing_span_min: 40,
        gap_status: 'UNKNOWN_REVIEW_REQUIRED', peak_c: null, confirmed_event_at: null, evidence_received_at: '2026-11-18T10:00:00Z',
        gap_continuity_warning: false, basis: 'CURRENT', merged_into_incident_id: null, incident_status_at_revision: 'OPEN', evaluation_id: 'ev1', raised_at: '2026-11-18T10:00:00Z',
      }, review_state: 'PENDING_QUALITY_REVIEW',
    };
    const fetch = mockFetch({
      ...baseRoutes,
      '/api/auth/login': { status: 200, body: { data: { access_token: 'test-token', token_type: 'bearer', expires_in_seconds: 300, username: 'quality.demo', organization_id: 'ORG-RECEIVER', roles: ['QUALITY'] }, meta: null } },
      '/api/auth/me': { status: 200, body: { data: { user_id: 'u1', username: 'quality.demo', organization_id: 'ORG-RECEIVER', roles: ['QUALITY'] }, meta: null } },
      '/api/incidents?status=OPEN&limit=500': { status: 200, body: { data: [incident], meta: { total: 1, limit: 500, offset: 0 } } },
      '/api/workflow/shipments/SHP-DEMO-1/disposition': { status: 202, body: { data: { business_ref: 'DISP-1', event_id: 'evt-1', idempotent_replay: false, status: 'PENDING_CONFIRMATION' }, meta: null } },
    });
    renderApp(<AppRoutes />, '/login');
    await user.type(screen.getByLabelText('Username'), 'quality.demo');
    await user.type(screen.getByLabelText('Password'), 'local-only-password');
    await user.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByText('QUALITY disposition')).toBeInTheDocument();
    expect(screen.getByText(/quality.demo · QUALITY/)).toBeInTheDocument();
    await user.type(screen.getByLabelText('Rationale'), 'Reviewed evidence; keep disposition advisory context separate.');
    await user.click(screen.getByRole('button', { name: 'Review disposition' }));
    expect(screen.getByRole('button', { name: 'Confirm disposition' })).toBeInTheDocument();
    expect(fetch.mock.calls.some(([input, init]) => String(input).includes('/workflow/') && init?.method === 'POST')).toBe(false);
    await user.click(screen.getByRole('button', { name: 'Confirm disposition' }));
    expect(await screen.findByText(/Disposition accepted by the API/)).toBeInTheDocument();
    const postCall = fetch.mock.calls.find(([input, init]) => String(input).includes('/workflow/') && init?.method === 'POST');
    expect(postCall?.[1]?.headers).toMatchObject({ Authorization: 'Bearer test-token' });
    expect(JSON.parse(String(postCall?.[1]?.body))).toMatchObject({ decision: 'QUARANTINE', incident_refs: ['INC-DEMO-1'] });
  });

  it('does not expose disposition controls to a signed-in non-QUALITY role', async () => {
    const user = userEvent.setup();
    mockFetch({
      ...baseRoutes,
      '/api/auth/login': { status: 200, body: { data: { access_token: 'carrier-token', token_type: 'bearer', expires_in_seconds: 300, username: 'carrier.demo', organization_id: 'ORG-CARRIER', roles: ['CARRIER'] }, meta: null } },
      '/api/auth/me': { status: 200, body: { data: { user_id: 'u2', username: 'carrier.demo', organization_id: 'ORG-CARRIER', roles: ['CARRIER'] }, meta: null } },
      '/api/incidents?status=OPEN&limit=500': { status: 200, body: { data: [{ incident_id: 'i', business_ref: 'INC-1', shipment_id: 'SHP-1', sensor_id: null, category: 'DATA_GAP', status: 'OPEN', opened_at: '2026-11-18T10:00:00Z', closed_at: null, detected_by: 'BASELINE', detector_version: null, summary: null, data_origin: 'SIMULATED', policy_code: null, policy_version: null, latest: null, review_state: 'PENDING_QUALITY_REVIEW' }], meta: { total: 1, limit: 500, offset: 0 } } },
    });
    renderApp(<AppRoutes />, '/login');
    await user.type(screen.getByLabelText('Username'), 'carrier.demo');
    await user.type(screen.getByLabelText('Password'), 'local-only-password');
    await user.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByText(/Disposition controls are available only to an authenticated QUALITY user/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Review disposition' })).not.toBeInTheDocument();
  });

  it('shows reconciliation and signed-audit verification controls only to ADMIN', async () => {
    const user = userEvent.setup();
    mockFetch({
      ...baseRoutes,
      '/api/auth/login': { status: 200, body: { data: { access_token: 'admin-token', token_type: 'bearer', expires_in_seconds: 300, username: 'admin.demo', organization_id: 'ORG-ADMIN', roles: ['ADMIN'] }, meta: null } },
      '/api/auth/me': { status: 200, body: { data: { user_id: 'u3', username: 'admin.demo', organization_id: 'ORG-ADMIN', roles: ['ADMIN'] }, meta: null } },
      '/api/ledger/transactions?limit=200': { status: 200, body: { data: [], meta: null } },
      '/api/ledger/audit?limit=200': { status: 200, body: { data: [], meta: null } },
    });
    renderApp(<AppRoutes />, '/login');
    await user.type(screen.getByLabelText('Username'), 'admin.demo');
    await user.type(screen.getByLabelText('Password'), 'local-only-password');
    await user.click(screen.getByRole('button', { name: 'Sign in' }));
    await user.click(await screen.findByRole('link', { name: 'Audit History' }));
    expect(await screen.findByRole('button', { name: 'Run chain reconciliation' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Verify signed audit chain' })).toBeInTheDocument();
  });
});

describe('Overview', () => {
  it('renders policy values exactly as returned by the API (nothing hardcoded)', async () => {
    mockFetch(baseRoutes);
    renderApp(<AppRoutes />, '/');
    expect(await screen.findByText('POL-TEST v7.3')).toBeInTheDocument();
    expect(screen.getByText('3.5 °C – 7.5 °C')).toBeInTheDocument();
    expect(screen.getByText('Above 7.5 °C for at least 45 min')).toBeInTheDocument();
    expect(screen.getByText('Below 3.5 °C for at least 20 min')).toBeInTheDocument();
    expect(screen.getByText(/Gap longer than 12 min is UNKNOWN/)).toBeInTheDocument();
    expect(screen.getByText('Required for a gap of at least 33 min')).toBeInTheDocument();
    expect(screen.getByText('None yet: import the dataset or ingest readings')).toBeInTheDocument();
  });

  it('shows an error state with retry when the policy request fails', async () => {
    mockFetch({
      ...baseRoutes,
      '/api/policies?status=ACTIVE': {
        status: 503,
        body: { error: { code: 'database_unavailable', message: 'The database is not reachable. Try again shortly.', details: null, request_id: 'q1' } },
      },
    });
    renderApp(<AppRoutes />, '/');
    expect(await screen.findByText('The database is not reachable. Try again shortly.')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /Try again/ }).length).toBeGreaterThan(0);
  });
});

describe('Shipments', () => {
  it('shows a loading state, then an honest empty state', async () => {
    mockFetch(baseRoutes);
    renderApp(<AppRoutes />, '/shipments');
    expect(screen.getByText('Loading shipments…')).toBeInTheDocument();
    expect(await screen.findByText('No shipments recorded')).toBeInTheDocument();
  });

  it('renders rows returned by the API', async () => {
    mockFetch({
      ...baseRoutes,
      '/api/shipments?limit=25&offset=0': {
        status: 200,
        body: {
          data: [{
            shipment_id: 'SHP-API-1', product_id: 'PRD-TEST', policy_id: testPolicy.policy_id,
            shipper_org_id: 'A', carrier_org_id: 'B', receiver_org_id: 'C', origin: 'Port A', destination: 'Port B',
            status: 'CREATED', data_origin: 'SIMULATED', created_at: '2026-11-14T08:30:00Z',
          }],
          meta: { total: 1, limit: 25, offset: 0 },
        },
      },
    });
    renderApp(<AppRoutes />, '/shipments');
    expect(await screen.findByText('SHP-API-1')).toBeInTheDocument();
    expect(screen.getByText('Port A → Port B')).toBeInTheDocument();
    expect(screen.getByText('2026-11-14 08:30 UTC')).toBeInTheDocument();
    expect(screen.getByText('SIMULATED')).toBeInTheDocument();
  });
});
