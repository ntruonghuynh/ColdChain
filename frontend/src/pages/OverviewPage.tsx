import { Activity, Database, Package, ShieldCheck } from 'lucide-react';
import type { ReactNode } from 'react';
import { Link } from 'react-router';
import { api } from '../api/client';
import { connectivityDetail } from '../components/ConnectivityIndicator';
import { PolicySummary } from '../components/PolicySummary';
import { Badge } from '../components/ui/Badge';
import { Card } from '../components/ui/Card';
import { PageHeader } from '../components/ui/PageHeader';
import { EmptyState, ErrorState, LoadingState } from '../components/ui/States';
import { useConnectivity } from '../hooks/connectivity';
import { useApi } from '../hooks/useApi';

const fetchActivePolicies = (signal: AbortSignal) => api.policies('ACTIVE', { signal });
const fetchShipmentCount = (signal: AbortSignal) => api.shipments({ limit: 1 }, { signal });
const fetchSystemInfo = (signal: AbortSignal) => api.systemInfo({ signal });

function StatTile({ icon, label, value, hint }: { icon: ReactNode; label: string; value: ReactNode; hint?: ReactNode }) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="rounded-lg bg-navy-900/5 p-2 text-navy-800">{icon}</div>
      <div className="min-w-0">
        <p className="text-xs font-medium tracking-wide text-slate-500 uppercase">{label}</p>
        <div className="mt-1 text-base font-semibold text-slate-900">{value}</div>
        {hint && <p className="mt-0.5 text-xs text-slate-500">{hint}</p>}
      </div>
    </div>
  );
}

export function OverviewPage() {
  const connectivity = useConnectivity();
  const policies = useApi(fetchActivePolicies);
  const shipments = useApi(fetchShipmentCount);
  const info = useApi(fetchSystemInfo);

  const apiValue =
    connectivity.status === 'online' ? (
      <Badge tone="success">Connected</Badge>
    ) : connectivity.status === 'degraded' ? (
      <Badge tone="warning">Degraded</Badge>
    ) : connectivity.status === 'offline' ? (
      <Badge tone="danger">Unreachable</Badge>
    ) : (
      <Badge tone="muted">Checking…</Badge>
    );
  const db = connectivity.report?.database;

  return (
    <>
      <PageHeader
        title="Overview"
        description="Status of the monitoring platform. Operational views fill in as later milestones are delivered."
      />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile icon={<Activity className="h-5 w-5" />} label="Backend API" value={apiValue} hint={connectivityDetail(connectivity)} />
        <StatTile
          icon={<Database className="h-5 w-5" />}
          label="Database"
          value={db ? (db.status === 'ok' ? <Badge tone="success">Ready</Badge> : <Badge tone="warning">{db.status}</Badge>) : <Badge tone="muted">Unknown</Badge>}
          hint={db?.migration_revision ? `Schema revision ${db.migration_revision}` : undefined}
        />
        <StatTile
          icon={<Package className="h-5 w-5" />}
          label="Shipments recorded"
          value={
            shipments.status === 'success' ? shipments.data.meta.total : shipments.status === 'loading' ? '…' : '—'
          }
          hint={
            shipments.status === 'success' && shipments.data.meta.total === 0
              ? 'None yet: import the dataset or ingest readings'
              : shipments.status === 'error'
                ? 'Could not load'
                : undefined
          }
        />
        <StatTile
          icon={<ShieldCheck className="h-5 w-5" />}
          label="Release authority"
          value={policies.status === 'success' && policies.data.data[0] ? policies.data.data[0].release_authority_role : '—'}
          hint="From the active policy"
        />
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-5">
        <Card
          className="lg:col-span-3"
          title="Active temperature policy"
          description="Loaded from the database. Values are configuration data, not hardcoded in the dashboard."
        >
          {policies.status === 'loading' && <LoadingState label="Loading policy…" />}
          {policies.status === 'error' && <ErrorState error={policies.error} onRetry={policies.reload} />}
          {policies.status === 'success' &&
            (policies.data.data[0] ? (
              <PolicySummary policy={policies.data.data[0]} />
            ) : (
              <EmptyState title="No active policy" description="The reference data has not been loaded. Restart the system to run the seed step." />
            ))}
        </Card>

        <Card className="lg:col-span-2" title="Delivery status" description="What this build can and cannot do yet.">
          {info.status === 'loading' && <LoadingState />}
          {info.status === 'error' && <ErrorState error={info.error} onRetry={info.reload} />}
          {info.status === 'success' && (
            <ul className="space-y-2.5">
              {info.data.data.features.map((f) => (
                <li key={f.key} className="flex items-start justify-between gap-3 text-sm">
                  <span className="text-slate-700">{f.name}</span>
                  {f.status === 'available' ? (
                    <Badge tone="success">Available</Badge>
                  ) : (
                    <Badge tone="muted">{f.milestone}</Badge>
                  )}
                </li>
              ))}
            </ul>
          )}
          <p className="mt-4 text-xs text-slate-500">
            Full details on the <Link className="font-medium text-cyan-700 hover:underline" to="/settings">System Settings</Link> page.
          </p>
        </Card>
      </div>
    </>
  );
}
