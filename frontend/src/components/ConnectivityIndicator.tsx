import { useConnectivity, type ConnectivityStatus } from '../hooks/connectivity';

const LABELS: Record<ConnectivityStatus, string> = {
  checking: 'Checking API…',
  online: 'API connected',
  degraded: 'API degraded',
  offline: 'API unreachable',
};

const DOT: Record<ConnectivityStatus, string> = {
  checking: 'bg-slate-400 animate-pulse',
  online: 'bg-emerald-500',
  degraded: 'bg-amber-500',
  offline: 'bg-rose-500',
};

export function connectivityDetail(state: ReturnType<typeof useConnectivity>): string {
  if (state.status === 'checking') return 'Contacting the backend health endpoint.';
  if (state.status === 'offline') return state.error?.message ?? 'The API did not respond.';
  const db = state.report?.database;
  if (!db) return '';
  if (db.status === 'ok') return `Database OK · migration ${db.migration_revision ?? '?'}`;
  if (db.status === 'migration_pending')
    return `Database migration pending (at ${db.migration_revision ?? 'none'}, expected ${db.expected_revision ?? '?'})`;
  return 'Database unavailable';
}

export function ConnectivityIndicator() {
  const state = useConnectivity();
  const detail = connectivityDetail(state);
  return (
    <button
      type="button"
      onClick={state.checkNow}
      title={`${detail}${state.lastChecked ? ` · checked ${state.lastChecked.toLocaleTimeString()}` : ''} · click to re-check`}
      className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50"
      data-testid="connectivity-indicator"
      data-status={state.status}
    >
      <span className={`h-2 w-2 rounded-full ${DOT[state.status]}`} aria-hidden="true" />
      <span role="status" aria-live="polite">{LABELS[state.status]}</span>
    </button>
  );
}
