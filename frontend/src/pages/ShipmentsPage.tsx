import { Package } from 'lucide-react';
import { useCallback, useState } from 'react';
import { Link } from 'react-router';
import { api } from '../api/client';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { PageHeader } from '../components/ui/PageHeader';
import { EmptyState, ErrorState, LoadingState } from '../components/ui/States';
import { formatUtc } from '../format';
import { useApi } from '../hooks/useApi';

const PAGE_SIZE = 25;

export function ShipmentsPage() {
  const [offset, setOffset] = useState(0);
  const fetcher = useCallback((signal: AbortSignal) => api.shipments({ limit: PAGE_SIZE, offset }, { signal }), [offset]);
  const shipments = useApi(fetcher);

  return (
    <>
      <PageHeader title="Shipments" description="Shipments recorded in the operational database." />
      <Card>
        {shipments.status === 'loading' && <LoadingState label="Loading shipments…" />}
        {shipments.status === 'error' && <ErrorState error={shipments.error} onRetry={shipments.reload} />}
        {shipments.status === 'success' && shipments.data.meta.total === 0 && (
          <EmptyState
            icon={<Package className="h-6 w-6" />}
            title="No shipments recorded"
            description="Simulated shipments appear after the synthetic dataset is imported (see the README). Readings arrive through the ingestion API. Nothing is shown until real records exist."
          />
        )}
        {shipments.status === 'success' && shipments.data.meta.total > 0 && (
          <>
            <div className="-mx-5 overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="border-b border-slate-200 text-left text-xs tracking-wide text-slate-500 uppercase">
                  <tr>
                    <th className="px-5 py-2 font-medium">Shipment</th>
                    <th className="px-5 py-2 font-medium">Route</th>
                    <th className="px-5 py-2 font-medium">Status</th>
                    <th className="px-5 py-2 font-medium">Data</th>
                    <th className="px-5 py-2 font-medium">Created</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {shipments.data.data.map((s) => (
                    <tr key={s.shipment_id}>
                      <td className="px-5 py-2.5 font-mono text-xs">
                        <Link className="text-cyan-700 hover:underline" to={`/temperature?shipment=${encodeURIComponent(s.shipment_id)}`}>
                          {s.shipment_id}
                        </Link>
                      </td>
                      <td className="px-5 py-2.5 text-slate-700">
                        {s.origin ?? '—'} → {s.destination ?? '—'}
                      </td>
                      <td className="px-5 py-2.5"><Badge>{s.status}</Badge></td>
                      <td className="px-5 py-2.5">
                        <Badge tone={s.data_origin === 'SIMULATED' ? 'warning' : 'info'}>{s.data_origin}</Badge>
                      </td>
                      <td className="px-5 py-2.5 whitespace-nowrap text-slate-500">{formatUtc(s.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="mt-4 flex items-center justify-between text-sm text-slate-500">
              <span>
                {offset + 1}–{offset + shipments.data.data.length} of {shipments.data.meta.total}
              </span>
              <div className="flex gap-2">
                <Button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>Previous</Button>
                <Button
                  disabled={offset + PAGE_SIZE >= shipments.data.meta.total}
                  onClick={() => setOffset(offset + PAGE_SIZE)}
                >
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
