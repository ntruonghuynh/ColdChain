import { screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { AppRoutes } from '../App';
import type { Incident, IncidentDetail, Telemetry } from '../api/types';
import { healthOk, mockFetch, renderApp } from '../test/utils';

// Deliberately not the seeded values: the UI must render what the API returns.
const policy = {
  policy_id: 'p1', policy_code: 'POL-TEST', policy_version: '7.3', content_sha256: 'a'.repeat(64),
  min_temp_c: '3.50', max_temp_c: '7.50', high_excursion_min_duration_min: 45, low_excursion_min_duration_min: 20,
  gap_unknown_after_min: 12, gap_review_at_min: 33,
};
const detector = {
  detector_config_id: 'd1', detector_code: 'DET-TEST', config_version: '9.9.9', content_sha256: 'b'.repeat(64),
  nominal_sampling_interval_s: 300, max_continuous_interval_s: 450,
};
const latest = {
  revision: 2, extent_start_at: '2026-09-01T01:00:00Z', extent_end_at: '2026-09-01T01:40:00Z', extent_open: false,
  direction: 'HIGH' as const, observed_duration_s: '2400', observed_duration_min: 40, bracketing_span_s: null,
  bracketing_span_min: null, gap_status: null, peak_c: '11.20', confirmed_event_at: '2026-09-01T01:45:00Z',
  evidence_received_at: '2026-09-01T06:00:00Z', gap_continuity_warning: true, basis: 'CURRENT' as const,
  merged_into_incident_id: null, incident_status_at_revision: 'OPEN', evaluation_id: 'e1', raised_at: '2026-09-01T06:00:00Z',
};
const incident: Incident = {
  incident_id: 'inc-1', business_ref: 'INC-SHP-1-SNS-1-TEX-H-20260901T010000Z', shipment_id: 'SHP-1', sensor_id: 'SNS-1',
  category: 'TEMPERATURE_EXCURSION', status: 'OPEN', opened_at: '2026-09-01T06:00:00Z', closed_at: null,
  detected_by: 'POLICY_BASELINE', detector_version: 'DET-TEST v9.9.9', summary: 'Observed temperature above limit.',
  data_origin: 'SIMULATED', policy_code: 'POL-TEST', policy_version: '7.3', latest, review_state: 'PENDING_QUALITY_REVIEW',
};
const gap = {
  gap_key: 'g1', sensor_id: 'SNS-1', start_at: '2026-09-01T02:00:00Z', end_at: '2026-09-01T02:40:00Z',
  start_bound: 'READING', end_bound: 'READING', bracketing_span_s: '2400.000000', bracketing_span_min: 40,
  estimated_missing_samples: 7, estimated_missing_duration_s: 2100, gap_status: 'UNKNOWN_REVIEW_REQUIRED' as const,
  out_of_range_before: false, out_of_range_after: false, raised_at: '2026-09-01T03:00:00Z', superseded_at: null,
  state: 'CURRENT' as const,
};
const reading = (t: string, c: string, state: 'IN_RANGE' | 'HIGH') => ({
  event_at: t, received_at: '2026-09-01T06:00:00Z', temperature_c: c, batch_ref: 'U1', delivery_lag_s: '60',
  temperature_state: state,
});
const readings = [reading('2026-09-01T01:55:00Z', '5.0', 'IN_RANGE'), reading('2026-09-01T02:00:00Z', '9.1', 'HIGH'),
  reading('2026-09-01T02:40:00Z', '5.2', 'IN_RANGE')];
const telemetry: Telemetry = {
  shipment_id: 'SHP-1', data_origin: 'SIMULATED', as_of: '2026-09-01T03:10:00Z', policy, detector_config: detector,
  sensors: [{
    sensor_id: 'SNS-1',
    status: {
      shipment_id: 'SHP-1', sensor_id: 'SNS-1', as_of: '2026-09-01T03:10:00Z', state: 'UNKNOWN',
      newest_event_at: '2026-09-01T02:40:00Z', newest_received_at: '2026-09-01T03:00:00Z', visible_reading_count: 3,
      unobserved_since_at: '2026-09-01T02:40:00Z', unobserved_duration_s: '1800', provisional_review_threshold_reached: true,
      end_boundary_established: false, monitoring_window: { assigned_from: '2026-09-01T00:00:00Z', assigned_to: null },
      confirmed_gaps: { SHORT_GAP: 0, UNKNOWN: 0, UNKNOWN_REVIEW_REQUIRED: 1 }, confirmed_gap_span_s: '2400',
      note: 'No reading for more than 15 min: temperature UNKNOWN.',
      last_observed_temperature_c: '5.20', last_observed_event_at: '2026-09-01T02:40:00Z',
      last_observed_temperature_state: 'IN_RANGE',
      communication: {
        status: 'WITHIN_RECENT_UPLOAD_INTERVALS', last_upload_received_at: '2026-09-01T03:00:00Z',
        since_last_upload_s: '600', observed_upload_interval_s: '900', longest_recent_upload_interval_s: '960',
        recent_intervals_used: 10, expected_schedule_configured: false,
      },
      open_incidents_as_of: { TEMPERATURE_EXCURSION: 0, DATA_GAP: 1 },
    },
    readings,
    gaps: [gap],
    runs: [],
  }],
};
const detail: IncidentDetail = {
  ...incident,
  revisions: [{ ...latest, revision: 1 }, latest],
  evidence: { readings, gaps: [gap], warnings: [] },
  policy, detector_config: detector,
  opening_evaluation: { evaluation_id: 'e1', mode: 'REPLAY', trigger: 'BATCH', as_of: '2026-09-01T06:00:00Z',
    input_fingerprint: 'c'.repeat(64), detector_code_version: 'x', visible_reading_count: 10 },
  dispositions: [], reassessments: [],
};
const summary = {
  data: {
    as_of: '2026-11-15T00:00:00Z', shipments_total: 1, shipments_evaluated: 1,
    sensors_by_monitoring_state: { NOT_STARTED: 0, CURRENT: 0, STALE: 0, UNKNOWN: 1, ENDED: 0 },
    open_incidents_by_category: { TEMPERATURE_EXCURSION: 17, DATA_GAP: 4, SENSOR_FAULT_SUSPECTED: 0 },
    open_incidents_by_basis: { CURRENT: 20, SUPERSEDED_BY_DATA: 1, MERGED_INTO: 0 },
    current_warnings_by_kind: {}, current_evidence_warnings: 0, batches_total: 1, rejected_records_total: 0,
    duplicates_ignored_total: 0, readings_total: 3, detector_config: detector,
  },
  meta: null,
};
const routes = {
  '/api/health': { status: 200, body: { data: healthOk, meta: null } },
  '/api/monitoring/summary': { status: 200, body: summary },
  '/api/incidents?status=OPEN&limit=25&offset=0': { status: 200, body: { data: [incident], meta: { total: 1, limit: 25, offset: 0 } } },
  '/api/shipments?limit=500&offset=0': {
    status: 200,
    body: { data: [{ shipment_id: 'SHP-1', product_id: 'P', policy_id: 'p1', shipper_org_id: 'A', carrier_org_id: 'B',
      receiver_org_id: 'C', origin: null, destination: null, status: 'CREATED', data_origin: 'SIMULATED',
      created_at: '2026-09-01T00:00:00Z' }], meta: { total: 1, limit: 500, offset: 0 } },
  },
  '/api/shipments/SHP-1/telemetry': { status: 200, body: { data: telemetry, meta: null } },
  '/api/incidents/inc-1': { status: 200, body: { data: detail, meta: null } },
};

describe('Excursion queue', () => {
  it('lists open incidents returned by the API with counts by category', async () => {
    mockFetch(routes);
    renderApp(<AppRoutes />, '/excursions');
    expect(await screen.findByText(incident.business_ref)).toBeInTheDocument();
    expect(screen.getByText('17 temperature excursions')).toBeInTheDocument();
    expect(screen.getByText('May have continued during gap')).toBeInTheDocument();
    expect(screen.getByText('SIMULATED DATA')).toBeInTheDocument();
    expect(screen.queryByText('Not implemented yet')).not.toBeInTheDocument();
  });

  it('shows an honest empty state', async () => {
    mockFetch({ ...routes, '/api/incidents?status=OPEN&limit=25&offset=0': { status: 200, body: { data: [], meta: { total: 0, limit: 25, offset: 0 } } } });
    renderApp(<AppRoutes />, '/excursions');
    expect(await screen.findByText('No open incidents')).toBeInTheDocument();
  });
});

describe('Temperature monitoring', () => {
  it('shows the monitoring state and missing data as UNKNOWN, never as in range', async () => {
    mockFetch(routes);
    renderApp(<AppRoutes />, '/temperature');
    expect(await screen.findByText('Sensor SNS-1')).toBeInTheDocument();
    expect(screen.getAllByText('UNKNOWN').length).toBeGreaterThan(0);
    expect(screen.getByText('No data for 30 min or more')).toBeInTheDocument();
    expect(screen.getByText('UNKNOWN · review required')).toBeInTheDocument();
    expect(screen.getByText('≈ 7')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: /3 readings, 1 confirmed gaps/ })).toBeInTheDocument();
    expect(screen.getAllByText(/Policy POL-TEST v7.3/).length).toBeGreaterThan(0);
    expect(screen.getByText(/detector DET-TEST v9.9.9/)).toBeInTheDocument();
  });

  it('shows an error state with retry when telemetry fails', async () => {
    mockFetch({ ...routes, '/api/shipments/SHP-1/telemetry': { status: 503, body: { error: { code: 'database_unavailable', message: 'The database is not reachable.', details: null, request_id: 'r' } } } });
    renderApp(<AppRoutes />, '/temperature?shipment=SHP-1');
    expect(await screen.findByText('The database is not reachable.')).toBeInTheDocument();
  });
});

describe('Communication status (presentation only)', () => {
  it('explains a scheduled upload without implying the temperature is safe', async () => {
    mockFetch(routes);
    renderApp(<AppRoutes />, '/temperature');
    const panel = await screen.findByRole('region', { name: 'Monitoring status in plain language' });
    expect(within(panel).getByText('Current temperature not known')).toBeInTheDocument();
    expect(within(panel).getByText(/Missing data is never treated as safe/)).toBeInTheDocument();
    expect(within(panel).getByText(/Waiting for the next scheduled upload/)).toBeInTheDocument();
    expect(within(panel).getByText(/not a\s+communication failure/)).toBeInTheDocument();
    expect(within(panel).getByText(/no expected upload schedule is configured/)).toBeInTheDocument();
    expect(within(panel).getByText(/only a confirmed gap of 33 min or more/)).toBeInTheDocument();
    expect(within(panel).queryByText(/temperature is (safe|normal|ok)/i)).not.toBeInTheDocument();
  });

  it('flags a silence longer than every recent upload interval as a possible outage', async () => {
    const outage = structuredClone(telemetry);
    const status = outage.sensors[0]!.status;
    status.communication = { ...status.communication, status: 'LONGER_THAN_RECENT_UPLOAD_INTERVALS', since_last_upload_s: '5400' };
    mockFetch({ ...routes, '/api/shipments/SHP-1/telemetry': { status: 200, body: { data: outage, meta: null } } });
    renderApp(<AppRoutes />, '/temperature');
    const panel = await screen.findByRole('region', { name: 'Monitoring status in plain language' });
    expect(within(panel).getByText('No upload for 90 min')).toBeInTheDocument();
    expect(within(panel).getByText(/Possible communication delay or outage/)).toBeInTheDocument();
    expect(within(panel).getByText('Current temperature not known')).toBeInTheDocument();
  });
});

describe('Incident detail', () => {
  it('shows revisions, versions and pending review, and offers no release action', async () => {
    mockFetch(routes);
    renderApp(<AppRoutes />, '/incidents/inc-1');
    expect(await screen.findByText('Pending human quality review')).toBeInTheDocument();
    const revisions = screen.getByRole('table');
    expect(within(revisions).getAllByRole('row')).toHaveLength(3);
    expect(screen.getByText(/POL-TEST v7.3/)).toBeInTheDocument();
    expect(screen.getByText(/DET-TEST v9.9.9, nominal 5 min/)).toBeInTheDocument();
    expect(screen.getByText('Incident Details', { selector: 'p' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /release|approve|quarantine|disposition|close incident/i })).not.toBeInTheDocument();
  });
});
