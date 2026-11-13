import { describe, expect, it } from 'vitest';
import { mockFetch } from '../test/utils';
import { ApiError, apiGet, getHealth } from './client';

describe('api client', () => {
  it('returns the parsed success envelope', async () => {
    mockFetch({ '/api/system/info': { status: 200, body: { data: { version: '0.1.0' }, meta: null } } });
    await expect(apiGet('/system/info')).resolves.toEqual({ data: { version: '0.1.0' }, meta: null });
  });

  it('maps the backend error envelope to ApiError', async () => {
    mockFetch({
      '/api/shipments/X': {
        status: 404,
        body: { error: { code: 'not_found', message: 'Shipment X not found.', details: null, request_id: 'r1' } },
      },
    });
    const error = await apiGet('/shipments/X').catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ kind: 'http', status: 404, code: 'not_found', requestId: 'r1', message: 'Shipment X not found.' });
  });

  it('reports network failures as kind "network"', async () => {
    mockFetch({ '/api/system/info': new TypeError('Failed to fetch') });
    await expect(apiGet('/system/info')).rejects.toMatchObject({ kind: 'network' });
  });

  it('reports non-JSON responses as invalid_response', async () => {
    const fn = mockFetch({});
    fn.mockResolvedValueOnce(new Response('<html>Bad Gateway</html>', { status: 502 }));
    await expect(apiGet('/system/info')).rejects.toMatchObject({ kind: 'invalid_response', status: 502 });
  });

  it('returns the health report for both 200 and 503', async () => {
    const degraded = { status: 'degraded', api: 'ok', database: { status: 'unavailable' }, checked_at: 'x' };
    mockFetch({ '/api/health': { status: 503, body: { data: degraded, meta: null } } });
    await expect(getHealth()).resolves.toMatchObject({ status: 'degraded' });
  });

  it('maps the proxy "api_unreachable" error', async () => {
    mockFetch({
      '/api/health': {
        status: 502,
        body: { error: { code: 'api_unreachable', message: 'The backend API is not reachable.', details: null, request_id: 'n1' } },
      },
    });
    await expect(getHealth()).rejects.toMatchObject({ kind: 'http', status: 502, code: 'api_unreachable' });
  });
});
