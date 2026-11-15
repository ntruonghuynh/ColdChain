import { useCallback } from 'react';
import { Link, useParams } from 'react-router';
import { api } from '../api/client';
import { BasisBadge, CategoryBadge, GapStatusBadge, SimulatedBadge } from '../components/monitoring/MonitoringBadges';
import { TemperatureChart } from '../components/monitoring/TemperatureChart';
import { Badge } from '../components/ui/Badge';
import { Card } from '../components/ui/Card';
import { KeyValueList } from '../components/ui/KeyValueList';
import { PageHeader } from '../components/ui/PageHeader';
import { ErrorState, LoadingState } from '../components/ui/States';
import { formatMinutes, formatOptionalUtc, formatUtc } from '../format';
import { useApi } from '../hooks/useApi';

export function IncidentDetailPage() {
  const { incidentId = '' } = useParams();
  const fetcher = useCallback((signal: AbortSignal) => api.incident(incidentId, { signal }), [incidentId]);
  const detail = useApi(fetcher);

  if (detail.status === 'loading') return <LoadingState label="Loading incident…" />;
  if (detail.status === 'error') return <ErrorState error={detail.error} onRetry={detail.reload} />;
  const inc = detail.data.data;
  const latest = inc.latest;

  return (
    <>
      <PageHeader
        title={inc.business_ref}
        description={inc.summary ?? undefined}
        actions={<Link className="text-sm font-medium text-cyan-700 hover:underline" to="/excursions">Back to the queue</Link>}
      />
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <CategoryBadge category={inc.category} />
        <SimulatedBadge origin={inc.data_origin} />
        {latest && <BasisBadge basis={latest.basis} />}
        {inc.status === 'OPEN' ? (
          <Badge tone="warning">Pending human quality review</Badge>
        ) : (
          <Badge tone="neutral">Closed by quality disposition</Badge>
        )}
      </div>
      {inc.status === 'OPEN' && (
        <p role="note" className="mb-6 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
          This incident is advisory evidence from the policy baseline. Only the Quality Officer can decide on the shipment;
          dispositions and release are implemented in Milestone 5. Nothing on this page releases goods.
        </p>
      )}
      {latest?.basis === 'SUPERSEDED_BY_DATA' && (
        <p role="note" className="mb-6 rounded-lg border border-cyan-200 bg-cyan-50 p-3 text-sm text-cyan-900">
          Later data changed the evidence (for example delayed readings filled a gap). The incident stays open until a
          quality disposition closes it; its history is kept below.
        </p>
      )}
      {inc.reassessments.length > 0 && (
        <p role="note" className="mb-6 rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-900">
          New evidence arrived after a quality decision: {inc.reassessments.length} decision(s) flagged for human
          reassessment. Existing decisions and releases are unchanged.
        </p>
      )}

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-5">
        <Card className="xl:col-span-3" title="Evidence timeline" description="Readings around the incident, by sensor event time.">
          {inc.policy && inc.detector_config ? (
            <TemperatureChart
              title={`Evidence for ${inc.business_ref}`}
              readings={inc.evidence.readings}
              gaps={inc.evidence.gaps.filter((g) => g.state === 'CURRENT')}
              minC={Number(inc.policy.min_temp_c)}
              maxC={Number(inc.policy.max_temp_c)}
              maxContinuousS={inc.detector_config.max_continuous_interval_s}
            />
          ) : (
            <p className="text-sm text-slate-500">No policy or detector reference recorded.</p>
          )}
        </Card>
        <Card className="xl:col-span-2" title="Facts">
          <KeyValueList
            items={[
              { label: 'Shipment / sensor', value: `${inc.shipment_id} / ${inc.sensor_id ?? '—'}` },
              {
                label: 'Interval (event time)',
                value: latest ? `${formatUtc(latest.extent_start_at)} → ${latest.extent_open ? 'ongoing' : formatUtc(latest.extent_end_at)}` : '—',
              },
              {
                label: inc.category === 'DATA_GAP' ? 'Bracketing span' : 'Observed duration',
                value: latest
                  ? formatMinutes((latest.observed_duration_min ?? latest.bracketing_span_min) as number)
                  : '—',
              },
              { label: 'Peak', value: latest?.peak_c ? `${Number(latest.peak_c).toFixed(2)} °C` : '—' },
              { label: 'Gap continuity', value: latest?.gap_continuity_warning ? 'Excursion may have continued during gap' : 'No adjacent gap' },
              { label: 'Raised (processing time)', value: formatUtc(inc.opened_at) },
              { label: 'Evidence complete (receipt)', value: formatOptionalUtc(latest?.evidence_received_at ?? null) },
              { label: 'Detected by', value: `${inc.detected_by} · ${inc.detector_version ?? '—'}` },
              {
                label: 'Policy',
                value: inc.policy ? `${inc.policy.policy_code} v${inc.policy.policy_version} (sha256 ${inc.policy.content_sha256.slice(0, 12)}…)` : '—',
              },
              {
                label: 'Detector configuration',
                value: inc.detector_config
                  ? `${inc.detector_config.detector_code} v${inc.detector_config.config_version}, nominal ${inc.detector_config.nominal_sampling_interval_s / 60} min, continuity ≤ ${inc.detector_config.max_continuous_interval_s} s`
                  : '—',
              },
              {
                label: 'Opening evaluation',
                value: inc.opening_evaluation
                  ? `${inc.opening_evaluation.mode} · ${inc.opening_evaluation.trigger} · as of ${formatUtc(inc.opening_evaluation.as_of)}`
                  : '—',
              },
            ]}
          />
        </Card>
      </div>

      <Card className="mt-6" title="Revisions" description="Append-only. Earlier evidence is never overwritten.">
        <div className="-mx-5 overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="border-b border-slate-200 text-left text-xs text-slate-500 uppercase">
              <tr>
                <th className="px-5 py-2 font-medium">#</th>
                <th className="px-5 py-2 font-medium">Raised</th>
                <th className="px-5 py-2 font-medium">Extent</th>
                <th className="px-5 py-2 font-medium">Evidence</th>
                <th className="px-5 py-2 font-medium">Status then</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {inc.revisions.map((r) => (
                <tr key={r.revision}>
                  <td className="px-5 py-2">{r.revision}</td>
                  <td className="px-5 py-2 whitespace-nowrap">{formatUtc(r.raised_at)}</td>
                  <td className="px-5 py-2 whitespace-nowrap">
                    {formatUtc(r.extent_start_at)} → {r.extent_open ? 'ongoing' : formatUtc(r.extent_end_at)}
                  </td>
                  <td className="px-5 py-2"><BasisBadge basis={r.basis} /></td>
                  <td className="px-5 py-2">{r.incident_status_at_revision}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div className="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-2">
        <Card title="Data-quality warnings in the evidence package" description="Persisted warnings; not incidents.">
          {inc.evidence.warnings.length === 0 ? (
            <p className="text-sm text-slate-500">None.</p>
          ) : (
            <ul className="space-y-2 text-sm">
              {inc.evidence.warnings.map((w) => (
                <li key={`${w.warning_key}-${w.raised_at}`} className="rounded-lg border border-slate-200 p-2">
                  <Badge tone="warning">{w.kind}</Badge> {w.state === 'SUPERSEDED' && <Badge tone="muted">superseded</Badge>}
                  <p className="mt-1 text-slate-700">{w.message}</p>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card title="Missing-data intervals nearby" description="Including superseded revisions (history).">
          {inc.evidence.gaps.length === 0 ? (
            <p className="text-sm text-slate-500">None.</p>
          ) : (
            <ul className="divide-y divide-slate-100 text-sm">
              {inc.evidence.gaps.map((g) => (
                <li key={`${g.gap_key}-${g.raised_at}`} className="flex flex-wrap items-center justify-between gap-2 py-2">
                  <span>
                    {formatUtc(g.start_at)} → {formatUtc(g.end_at)} · {formatMinutes(g.bracketing_span_min)} (≈{' '}
                    {g.estimated_missing_samples} samples missing)
                  </span>
                  <span className="flex gap-1">
                    <GapStatusBadge status={g.gap_status} />
                    {g.state === 'SUPERSEDED' && <Badge tone="muted">superseded</Badge>}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </>
  );
}
