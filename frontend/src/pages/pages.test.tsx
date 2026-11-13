import { screen, within } from '@testing-library/react';
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

  it.each([
    ['/temperature', 'Temperature Monitoring'],
    ['/excursions', 'Excursion Queue'],
    ['/quality-review', 'Quality Review'],
    ['/audit', 'Audit History'],
  ])('%s says "Not implemented yet" and shows no data', (route, title) => {
    mockFetch(baseRoutes);
    renderApp(<AppRoutes />, route);
    expect(screen.getByRole('heading', { level: 1, name: title })).toBeInTheDocument();
    expect(screen.getByText('Not implemented yet')).toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });

  it('shows a not-found page for unknown routes', () => {
    mockFetch(baseRoutes);
    renderApp(<AppRoutes />, '/no-such-page');
    expect(screen.getAllByText('Page not found')).toHaveLength(2); // header title + page body
    expect(screen.getByRole('link', { name: 'Go to the overview' })).toBeInTheDocument();
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
    expect(screen.getByText('None yet: ingestion arrives in M3')).toBeInTheDocument();
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
