import { ListChecks } from 'lucide-react';
import { useCallback, useState } from 'react';
import { Link, useSearchParams } from 'react-router';
import { api } from '../api/client';
import { BasisBadge, CategoryBadge, SimulatedBadge } from '../components/monitoring/MonitoringBadges';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { PageHeader } from '../components/ui/PageHeader';
import { EmptyState, ErrorState, LoadingState } from '../components/ui/States';
import { formatMinutes, formatUtc } from '../format';
import { useApi } from '../hooks/useApi';

const PAGE_SIZE = 25;
const FILTERS = [
  { key: '', label: 'All open' },
  { key: 'TEMPERATURE_EXCURSION', label: 'Temperature excursions' },
  { key: 'DATA_GAP', label: 'Data gaps' },
];
const fetchSummary = (signal: AbortSignal) => api.monitoringSummary({ signal });

export function ExcursionQueuePage() {
  const [params, setParams] = useSearchParams();
  const category = params.get('category') ?? '';
  const shipmentId = params.get('shipment') ?? undefined;
  const [offset, setOffset] = useState(0);
  const fetcher = useCallback(
    (signal: AbortSignal) =>
      api.incidents({ status: 'OPEN', category: category || undefined, shipmentId, limit: PAGE_SIZE, offset }, { signal }),
    [category, shipmentId, offset],
  );
  const incidents = useApi(fetcher);
  const summary = useApi(fetchSummary);

  const choose = (key: string) => {
    const next = new URLSearchParams(params);
    if (key) next.set('category', key);
    else next.delete('category');
    setParams(next);
    setOffset(0);
  };

  return (
    <>
      <PageHeader
        title="Excursion Queue"
        description="Open incidents waiting for quality review. Product-risk alerts (temperature) are kept apart from missing-data alerts."
      />
      {summary.status === 'success' && (
        <div className="mb-4 flex flex-wrap gap-2 text-sm">
          <Badge tone="danger">{summary.data.data.open_incidents_by_category.TEMPERATURE_EXCURSION ?? 0} temperature excursions</Badge>
          <Badge tone="warning">{summary.data.data.open_incidents_by_category.DATA_GAP ?? 0} data gaps</Badge>
          <Badge tone="info">{summary.data.data.open_incidents_by_basis.SUPERSEDED_BY_DATA ?? 0} with evidence superseded</Badge>
        </div>
      )}
      <Card
        title={shipmentId ? `Open incidents of ${shipmentId}` : 'Open incidents'}
        description="No incident is closed automatically. Only an authenticated receiving-organization QUALITY disposition can close an incident."
        actions={
          <div className="flex flex-wrap gap-2" role="group" aria-label="Filter by category">
            {FILTERS.map((f) => (
              <Button key={f.key} variant={category === f.key ? 'primary' : 'secondary'} onClick={() => choose(f.key)}>
                {f.label}
              </Button>
            ))}
          </div>
        }
      >
        {incidents.status === 'loading' && <LoadingState label="Loading incidents…" />}
        {incidents.status === 'error' && <ErrorState error={incidents.error} onRetry={incidents.reload} />}
        {incidents.status === 'success' && incidents.data.meta.total === 0 && (
          <EmptyState
            icon={<ListChecks className="h-6 w-6" />}
            title="No open incidents"
            description="Incidents appear when the baseline detector confirms a policy excursion or a missing-data interval of at least 30 minutes."
          />
        )}
        {incidents.status === 'success' && incidents.data.meta.total > 0 && (
          <>
            <div className="-mx-5 overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="border-b border-slate-200 text-left text-xs tracking-wide text-slate-500 uppercase">
                  <tr>
                    <th className="px-5 py-2 font-medium">Incident</th>
                    <th className="px-5 py-2 font-medium">Shipment</th>
                    <th className="px-5 py-2 font-medium">Interval (event time)</th>
                    <th className="px-5 py-2 font-medium">Observed</th>
                    <th className="px-5 py-2 font-medium">Evidence</th>
                    <th className="px-5 py-2 font-medium">Raised</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {incidents.data.data.map((i) => (
                    <tr key={i.incident_id}>
                      <td className="px-5 py-2.5">
                        <CategoryBadge category={i.category} />
                        <Link className="mt-1 block font-mono text-xs text-cyan-700 hover:underline" to={`/incidents/${i.incident_id}`}>
                          {i.business_ref}
                        </Link>
                      </td>
                      <td className="px-5 py-2.5">
                        <span className="font-mono text-xs">{i.shipment_id}</span>
                        <div className="mt-1"><SimulatedBadge origin={i.data_origin} /></div>
                      </td>
                      <td className="px-5 py-2.5 whitespace-nowrap text-slate-700">
                        {i.latest ? `${formatUtc(i.latest.extent_start_at)} → ${i.latest.extent_open ? 'ongoing' : formatUtc(i.latest.extent_end_at)}` : '—'}
                      </td>
                      <td className="px-5 py-2.5 text-slate-700">
                        {i.latest?.observed_duration_min != null && `${i.latest.direction} for ${formatMinutes(i.latest.observed_duration_min)}`}
                        {i.latest?.bracketing_span_min != null && `no data for ${formatMinutes(i.latest.bracketing_span_min)}`}
                        {i.latest?.gap_continuity_warning && (
                          <div className="mt-1"><Badge tone="warning">May have continued during gap</Badge></div>
                        )}
                      </td>
                      <td className="px-5 py-2.5">{i.latest && <BasisBadge basis={i.latest.basis} />}</td>
                      <td className="px-5 py-2.5 whitespace-nowrap text-slate-500">{formatUtc(i.opened_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="mt-4 flex items-center justify-between text-sm text-slate-500">
              <span>
                {offset + 1}–{offset + incidents.data.data.length} of {incidents.data.meta.total}
              </span>
              <div className="flex gap-2">
                <Button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>Previous</Button>
                <Button disabled={offset + PAGE_SIZE >= incidents.data.meta.total} onClick={() => setOffset(offset + PAGE_SIZE)}>
                  Next
                </Button>
              </div>
            </div>
          </>
        )}
      </Card>
    </>
  );
}
