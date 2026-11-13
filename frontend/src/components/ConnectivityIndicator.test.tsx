import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { healthOk, mockFetch, renderApp } from '../test/utils';
import { ConnectivityIndicator } from './ConnectivityIndicator';

describe('ConnectivityIndicator', () => {
  it('shows connected when API and database are ready', async () => {
    mockFetch({ '/api/health': { status: 200, body: { data: healthOk, meta: null } } });
    renderApp(<ConnectivityIndicator />);
    expect(await screen.findByText('API connected')).toBeInTheDocument();
    expect(screen.getByTestId('connectivity-indicator')).toHaveAttribute('data-status', 'online');
  });

  it('shows degraded when the database is unavailable', async () => {
    const degraded = { ...healthOk, status: 'degraded', database: { ...healthOk.database, status: 'unavailable' } };
    mockFetch({ '/api/health': { status: 503, body: { data: degraded, meta: null } } });
    renderApp(<ConnectivityIndicator />);
    expect(await screen.findByText('API degraded')).toBeInTheDocument();
  });

  it('shows unreachable when the API cannot be contacted', async () => {
    mockFetch({ '/api/health': new TypeError('Failed to fetch') });
    renderApp(<ConnectivityIndicator />);
    expect(await screen.findByText('API unreachable')).toBeInTheDocument();
  });
});
