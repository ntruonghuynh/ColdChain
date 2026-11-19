import { ExternalLink, RefreshCw } from 'lucide-react';
import { API_BASE_URL, api } from '../api/client';
import { connectivityDetail } from '../components/ConnectivityIndicator';
import { PolicySummary } from '../components/PolicySummary';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { KeyValueList } from '../components/ui/KeyValueList';
import { PageHeader } from '../components/ui/PageHeader';
import { EmptyState, ErrorState, LoadingState } from '../components/ui/States';
import { formatUtc } from '../format';
import { useConnectivity } from '../hooks/connectivity';
import { useApi } from '../hooks/useApi';

const fetchSystemInfo = (signal: AbortSignal) => api.systemInfo({ signal });
const fetchPolicies = (signal: AbortSignal) => api.policies(undefined, { signal });
const fetchOrganizations = (signal: AbortSignal) => api.organizations({ signal });

export function SettingsPage() {
  const connectivity = useConnectivity();
  const info = useApi(fetchSystemInfo);
  const policies = useApi(fetchPolicies);
  const orgs = useApi(fetchOrganizations);
  const db = connectivity.report?.database;

  return (
    <>
      <PageHeader
        title="System Settings"
        description="Read-only view of the running configuration. Settings are changed through configuration files, not this page."
      />
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card
          title="API connectivity"
          actions={
            <Button onClick={connectivity.checkNow}>
              <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" /> Check now
            </Button>
          }
        >
          <KeyValueList
            items={[
              { label: 'Status', value: connectivity.status },
              { label: 'Detail', value: connectivityDetail(connectivity) },
              { label: 'API base path', value: <code className="font-mono text-xs">{API_BASE_URL}</code> },
              { label: 'Database latency', value: db?.latency_ms != null ? `${db.latency_ms} ms` : '—' },
              { label: 'Schema revision', value: db ? `${db.migration_revision ?? 'none'} (expected ${db.expected_revision ?? '?'})` : '—' },
              { label: 'Last checked', value: connectivity.lastChecked ? connectivity.lastChecked.toLocaleString() : '—' },
            ]}
          />
          <a
            href={`${API_BASE_URL}/docs`}
            target="_blank"
            rel="noreferrer"
            className="mt-3 inline-flex items-center gap-1 text-sm font-medium text-cyan-700 hover:underline"
          >
            Open API documentation <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
          </a>
        </Card>

        <Card title="Application">
          {info.status === 'loading' && <LoadingState />}
          {info.status === 'error' && <ErrorState error={info.error} onRetry={info.reload} />}
          {info.status === 'success' && (
            <>
              <KeyValueList
                items={[
                  { label: 'Name', value: info.data.data.app_name },
                  { label: 'Version', value: info.data.data.version },
                  { label: 'Milestone', value: info.data.data.milestone },
                  { label: 'Environment', value: info.data.data.environment },
                  { label: 'Server time', value: formatUtc(info.data.data.server_time) },
                ]}
              />
              <h3 className="mt-4 mb-2 text-xs font-semibold tracking-wide text-slate-500 uppercase">Features</h3>
              <ul className="space-y-2">
                {info.data.data.features.map((f) => (
                  <li key={f.key} className="flex items-start justify-between gap-3 text-sm">
                    <span>
                      <span className="text-slate-800">{f.name}</span>
                      {f.note && <span className="block text-xs text-slate-500">{f.note}</span>}
                    </span>
                    {f.status === 'available' ? (
                      <Badge tone="success">Available</Badge>
                    ) : (
                      <Badge tone="muted">Not implemented · {f.milestone}</Badge>
                    )}
                  </li>
                ))}
              </ul>
            </>
          )}
        </Card>

        <Card
          title="Temperature policies"
          description="Configuration data loaded from backend/app/seed/data/policies. A policy version cannot be edited; publish a new version instead."
          className="lg:col-span-2"
        >
          {policies.status === 'loading' && <LoadingState />}
          {policies.status === 'error' && <ErrorState error={policies.error} onRetry={policies.reload} />}
          {policies.status === 'success' &&
            (policies.data.data.length === 0 ? (
              <EmptyState title="No policies loaded" />
            ) : (
              <div className="space-y-6">
                {policies.data.data.map((p) => (
                  <PolicySummary key={p.policy_id} policy={p} detailed />
                ))}
              </div>
            ))}
        </Card>

        <Card
          title="Organizations and roles"
          description="Participant accounts and assigned roles exposed by the backend. Sign-in credentials are configured outside the frontend."
          className="lg:col-span-2"
        >
          {orgs.status === 'loading' && <LoadingState />}
          {orgs.status === 'error' && <ErrorState error={orgs.error} onRetry={orgs.reload} />}
          {orgs.status === 'success' && (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              {orgs.data.data.map((org) => (
                <div key={org.org_id} className="rounded-lg border border-slate-200 p-4">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-sm font-semibold text-slate-900">{org.name}</p>
                    <Badge tone="info">{org.org_type}</Badge>
                  </div>
                  <ul className="mt-3 space-y-1.5">
                    {org.users.map((u) => (
                      <li key={u.username} className="flex flex-wrap items-center justify-between gap-2 text-sm">
                        <span className="text-slate-700">
                          {u.display_name} <code className="font-mono text-xs text-slate-400">{u.username}</code>
                        </span>
                        <span className="flex gap-1">
                          {u.roles.map((r) => (
                            <Badge key={r} tone={r === 'QUALITY' ? 'success' : 'neutral'}>{r}</Badge>
                          ))}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </>
  );
}
