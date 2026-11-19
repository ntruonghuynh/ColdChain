import { Thermometer } from 'lucide-react';
import { useCallback, useState } from 'react';
import { Link, useSearchParams } from 'react-router';
import { api } from '../api/client';
import type { SensorTelemetry, Telemetry } from '../api/types';
import { GapStatusBadge, MonitoringStateBadge, SimulatedBadge } from '../components/monitoring/MonitoringBadges';
import { TelemetryStatusPanel } from '../components/monitoring/TelemetryStatusPanel';
import { ModelReadinessCard } from '../components/monitoring/ModelReadinessCard';
import { TemperatureChart } from '../components/monitoring/TemperatureChart';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { KeyValueList } from '../components/ui/KeyValueList';
import { PageHeader } from '../components/ui/PageHeader';
import { EmptyState, ErrorState, LoadingState } from '../components/ui/States';
import { formatMinutes, formatOptionalUtc, formatUtc } from '../format';
import { useApi } from '../hooks/useApi';

const fetchShipments = (signal: AbortSignal) => api.shipments({ limit: 500, offset: 0 }, { signal });

/** datetime-local value (interpreted as UTC) -> ISO string with Z. */
function toIsoUtc(local: string): string | undefined {
  if (!local) return undefined;
  const withSeconds = local.length === 16 ? `${local}:00` : local;
  return `${withSeconds}Z`;
}

function SensorPanel({ sensor, telemetry }: { sensor: SensorTelemetry; telemetry: Telemetry }) {
  const s = sensor.status;
  const policy = telemetry.policy;
  const tail = s.state === 'ENDED' || s.state === 'NOT_STARTED' ? null : s.unobserved_since_at;
  return (
    <div className="space-y-6">
      <Card
        title={
          <span className="flex flex-wrap items-center gap-2">
            Sensor {sensor.sensor_id} <MonitoringStateBadge state={s.state} />
            {s.provisional_review_threshold_reached && <Badge tone="danger">No data for 30 min or more</Badge>}
          </span>
        }
        description={s.note}
      >
        <TelemetryStatusPanel status={s} reviewAtMin={policy.gap_review_at_min} />
        <h3 className="mt-5 mb-1 text-xs font-medium tracking-wide text-slate-500 uppercase">Details</h3>
        <KeyValueList
          items={[
            { label: 'Viewed as of (processing time)', value: formatUtc(s.as_of) },
            { label: 'Newest reading (event time)', value: formatOptionalUtc(s.newest_event_at) },
            { label: 'Newest receipt', value: formatOptionalUtc(s.newest_received_at) },
            {
              label: 'Without data since',
              value: s.unobserved_since_at
                ? `${formatUtc(s.unobserved_since_at)} (${formatMinutes(Number(s.unobserved_duration_s) / 60)})`
                : '—',
            },
            {
              label: 'Monitoring window',
              value: `${formatOptionalUtc(s.monitoring_window.assigned_from)} → ${
                s.monitoring_window.assigned_to ? formatUtc(s.monitoring_window.assigned_to) : 'not documented yet (UNKNOWN)'
              }`,
            },
            {
              label: 'Confirmed gaps',
              value: `${s.confirmed_gaps.SHORT_GAP} short, ${s.confirmed_gaps.UNKNOWN} UNKNOWN, ${s.confirmed_gaps.UNKNOWN_REVIEW_REQUIRED} review required`,
            },
          ]}
        />
      </Card>

      <Card title="Temperature timeline" description="Readings received by the selected time. Gaps are never drawn as in range.">
        <TemperatureChart
          title={`Temperature of sensor ${sensor.sensor_id}`}
          readings={sensor.readings}
          gaps={sensor.gaps}
          runs={sensor.runs}
          minC={Number(policy.min_temp_c)}
          maxC={Number(policy.max_temp_c)}
          maxContinuousS={telemetry.detector_config.max_continuous_interval_s}
          xStart={s.monitoring_window.assigned_from}
          xEnd={s.state === 'ENDED' ? s.monitoring_window.assigned_to : s.as_of}
          notReceivedFrom={tail}
        />
      </Card>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <Card title="Missing-data intervals" description="Bracketing span is compared with the policy; missing samples are an estimate.">
          {sensor.gaps.length === 0 ? (
            <p className="text-sm text-slate-500">No confirmed gap at this time.</p>
          ) : (
            <div className="-mx-5 overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="border-b border-slate-200 text-left text-xs text-slate-500 uppercase">
                  <tr>
                    <th className="px-5 py-2 font-medium">From → to (event time)</th>
                    <th className="px-5 py-2 font-medium">Bracketing span</th>
                    <th className="px-5 py-2 font-medium">Est. missing samples</th>
                    <th className="px-5 py-2 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {sensor.gaps.map((g) => (
                    <tr key={g.gap_key}>
                      <td className="px-5 py-2 whitespace-nowrap">
                        {formatUtc(g.start_at)} → {formatUtc(g.end_at)}
                      </td>
                      <td className="px-5 py-2">{formatMinutes(g.bracketing_span_min)}</td>
                      <td className="px-5 py-2">≈ {g.estimated_missing_samples}</td>
                      <td className="px-5 py-2"><GapStatusBadge status={g.gap_status} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
        <Card title="Observed out-of-range runs" description={`Policy ${policy.policy_code} v${policy.policy_version}: above ${policy.max_temp_c} °C for ${policy.high_excursion_min_duration_min} min, below ${policy.min_temp_c} °C for ${policy.low_excursion_min_duration_min} min.`}>
          {sensor.runs.length === 0 ? (
            <p className="text-sm text-slate-500">No reading outside the policy range at this time.</p>
          ) : (
            <ul className="divide-y divide-slate-100 text-sm">
              {sensor.runs.map((r) => (
                <li key={r.run_key} className="flex flex-wrap items-center justify-between gap-2 py-2">
                  <span>
                    {r.direction} {formatUtc(r.first_event_at)} → {formatUtc(r.last_event_at)} ·{' '}
                    {formatMinutes(r.observed_duration_min)} observed, peak {Number(r.peak_c).toFixed(1)} °C
                  </span>
                  {r.meets_policy_duration ? <Badge tone="danger">Policy excursion</Badge> : <Badge tone="muted">Below duration</Badge>}
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}

export function TemperatureMonitoringPage() {
  const [params, setParams] = useSearchParams();
  const shipments = useApi(fetchShipments);
  const selected = params.get('shipment') ?? (shipments.status === 'success' ? shipments.data.data[0]?.shipment_id : undefined);
  const asOf = params.get('as_of') ?? undefined;
  const [asOfInput, setAsOfInput] = useState(asOf ? asOf.slice(0, 19) : '');

  const fetchTelemetry = useCallback(
    (signal: AbortSignal) =>
      selected ? api.telemetry(selected, asOf, { signal }) : Promise.reject(new Error('no shipment selected')),
    [selected, asOf],
  );
  const telemetry = useApi(fetchTelemetry);

  const update = (next: Record<string, string | undefined>) => {
    const merged = new URLSearchParams(params);
    for (const [k, v] of Object.entries(next)) {
      if (v) merged.set(k, v);
      else merged.delete(k);
    }
    setParams(merged);
  };

  return (
    <>
      <PageHeader
        title="Temperature Monitoring"
        description="Sensor event-time timeline with policy limits, confirmed missing-data intervals and the current monitoring state."
      />
      <div className="mb-6"><ModelReadinessCard /></div>
      <Card className="mb-6">
        {shipments.status === 'loading' && <LoadingState label="Loading shipments…" />}
        {shipments.status === 'error' && <ErrorState error={shipments.error} onRetry={shipments.reload} />}
        {shipments.status === 'success' && shipments.data.meta.total === 0 && (
          <EmptyState
            icon={<Thermometer className="h-6 w-6" />}
            title="No shipments recorded"
            description="Import the synthetic dataset or ingest readings first. Nothing is shown until real records exist."
          />
        )}
        {shipments.status === 'success' && shipments.data.meta.total > 0 && (
          <form
            className="flex flex-wrap items-end gap-4"
            onSubmit={(e) => {
              e.preventDefault();
              update({ as_of: toIsoUtc(asOfInput) });
            }}
          >
            <label className="flex flex-col gap-1 text-sm text-slate-600">
              Shipment
              <select
                className="rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
                value={selected ?? ''}
                onChange={(e) => update({ shipment: e.target.value })}
              >
                {shipments.data.data.map((s) => (
                  <option key={s.shipment_id} value={s.shipment_id}>
                    {s.shipment_id}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-sm text-slate-600">
              View as of (UTC, processing time)
              <input
                type="datetime-local"
                step="1"
                className="rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
                value={asOfInput}
                onChange={(e) => setAsOfInput(e.target.value)}
              />
            </label>
            <Button type="submit" variant="primary">Apply</Button>
            <Button
              onClick={() => {
                setAsOfInput('');
                update({ as_of: undefined });
              }}
            >
              Now
            </Button>
            <p className="basis-full text-xs text-slate-500">
              Causal view: only readings received and results raised by the selected time are shown.
            </p>
          </form>
        )}
      </Card>

      {selected && telemetry.status === 'loading' && <LoadingState label="Loading telemetry…" />}
      {selected && telemetry.status === 'error' && <ErrorState error={telemetry.error} onRetry={telemetry.reload} />}
      {telemetry.status === 'success' && (
        <>
          <div className="mb-4 flex flex-wrap items-center gap-2 text-sm text-slate-600">
            <SimulatedBadge origin={telemetry.data.data.data_origin} />
            <span>
              Policy {telemetry.data.data.policy.policy_code} v{telemetry.data.data.policy.policy_version} · detector{' '}
              {telemetry.data.data.detector_config.detector_code} v{telemetry.data.data.detector_config.config_version} (nominal
              interval {telemetry.data.data.detector_config.nominal_sampling_interval_s / 60} min)
            </span>
            <Link className="font-medium text-cyan-700 hover:underline" to={`/excursions?shipment=${encodeURIComponent(telemetry.data.data.shipment_id)}`}>
              Incidents of this shipment
            </Link>
          </div>
          {telemetry.data.data.sensors.length === 0 ? (
            <EmptyState title="No sensor assigned" description="This shipment has no documented sensor monitoring window." />
          ) : (
            telemetry.data.data.sensors.map((s) => <SensorPanel key={s.sensor_id} sensor={s} telemetry={telemetry.data.data} />)
          )}
        </>
      )}
    </>
  );
}
