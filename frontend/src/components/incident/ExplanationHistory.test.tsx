import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { describe, expect, it } from 'vitest';
import { AuthProvider, useAuth } from '../../auth/AuthContext';
import { mockFetch } from '../../test/utils';
import { ExplanationHistory } from './ExplanationHistory';

function AuthProbe() {
  const auth = useAuth();
  if (!auth.identity) return <button type="button" onClick={() => void auth.login('quality.demo', 'local-only-password')}>Authenticate test session</button>;
  return <ExplanationHistory incidentId="incident-1" />;
}

describe('stored M6 explanation history', () => {
  it('renders stored citations and validator limits without generating a new explanation', async () => {
    const user = userEvent.setup();
    const fetch = mockFetch({
      '/api/auth/login': { status: 200, body: { data: { access_token: 'quality-token', token_type: 'bearer', expires_in_seconds: 300, username: 'quality.demo', organization_id: 'ORG-RECEIVER', roles: ['QUALITY'] }, meta: null } },
      '/api/auth/me': { status: 200, body: { data: { user_id: 'q1', username: 'quality.demo', organization_id: 'ORG-RECEIVER', roles: ['QUALITY'] }, meta: null } },
      '/api/llm/incidents/incident-1/explanations': { status: 200, body: { data: [{ explanation_id: 'ex-1', explanation_status: 'draft', source_mode: 'llm', provider: 'disabled', model: 'mock-v1', prompt_version: 'prompt-3', explained_at: '2026-11-18T12:00:00Z', evidence_cutoff_at: '2026-11-18T11:55:00Z', citation_verification: 'passed' }], meta: null } },
      '/api/llm/explanations/ex-1': { status: 200, body: { data: {
        explanation_id: 'ex-1', shipment_id: 'SHP-1', incident_id: 'incident-1', incident_ref: 'INC-1', explained_at: '2026-11-18T12:00:00Z', evidence_cutoff_at: '2026-11-18T11:55:00Z', explanation_status: 'draft', source_mode: 'llm', provider: 'disabled', model: 'mock-v1', prompt_version: 'prompt-3', policy_version: 'POL-1.0', procedure_version: 'SOP-1.0', sensor_interval_start_at: '2026-11-18T10:00:00Z', sensor_interval_end_at: '2026-11-18T11:00:00Z', evidence_references: ['SYS:incident/INC-1', 'SYS:gaps/g1'], document_versions: ['SOP-1.0#DELAYED_OCEAN'], citation_verification: 'passed', summary_vi: 'Stored advisory summary.', observations_vi: [], policy_findings_vi: [], ml_advisories_vi: [], potential_factors_vi: [], recommended_steps_vi: [], evidence_needed_vi: [], unknowns_vi: ['No temperature is known during the data gap.'], citations: [{ source_id: 'SOP-1.0#DELAYED_OCEAN', claim: 'Follow the approved delayed data procedure.', quote: 'Preserve original sensor event times.' }], validation_diagnostics: { application_validation_status: 'passed', citation_validation_status: 'passed', evidence_validation_status: 'passed', temporal_validation_status: 'passed', provider_call_status: 'succeeded' },
      }, meta: null } },
    });
    render(<MemoryRouter><AuthProvider><AuthProbe /></AuthProvider></MemoryRouter>);
    await user.click(screen.getByRole('button', { name: 'Authenticate test session' }));
    expect(await screen.findByText('Stored advisory summary.')).toBeInTheDocument();
    expect(screen.getAllByText('SOP-1.0#DELAYED_OCEAN')).toHaveLength(2);
    expect(screen.getByText(/Preserve original sensor event times\./)).toBeInTheDocument();
    expect(screen.getByText(/do not independently establish that every explanation is factually or clinically correct/)).toBeInTheDocument();
    expect(screen.getByText(/No temperature is known during the data gap/)).toBeInTheDocument();
    expect(fetch.mock.calls.some(([input, init]) => String(input).includes('/llm/incidents/incident-1/explanations') && init?.method === 'POST')).toBe(false);
    expect(fetch.mock.calls.filter(([input, init]) => String(input).includes('/llm/') && init?.method === 'POST')).toHaveLength(0);
  });
});
