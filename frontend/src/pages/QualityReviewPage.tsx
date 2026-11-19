import { useMemo, useState } from 'react';
import { Link } from 'react-router';
import { api, ApiError } from '../api/client';
import type { Incident, Shipment } from '../api/types';
import { useAuth } from '../auth/AuthContext';
import { CategoryBadge, BasisBadge, SimulatedBadge } from '../components/monitoring/MonitoringBadges';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { PageHeader } from '../components/ui/PageHeader';
import { EmptyState, ErrorState, LoadingState } from '../components/ui/States';
import { formatMinutes, formatUtc } from '../format';
import { useApi } from '../hooks/useApi';

const loadOpenIncidents = (signal: AbortSignal) => api.incidents({ status: 'OPEN', limit: 500 }, { signal });
const loadShipments = (signal: AbortSignal) => api.shipments({ limit: 500, offset: 0 }, { signal });
const newBusinessRef = () => `CC-DISP-${globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`}`;

function ShipmentWithoutIncidents({ shipment, quality }: { shipment: Shipment; quality: boolean }) {
  const [decision, setDecision] = useState<'RELEASE' | 'QUARANTINE'>('RELEASE');
  const [rationale, setRationale] = useState('');
  const [businessRef, setBusinessRef] = useState(newBusinessRef);
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState('');
  const submit = async () => {
    setBusy(true); setError(''); setResult('');
    try {
      const response = await api.disposition(shipment.shipment_id, { business_ref: businessRef, decision, rationale, incident_refs: [] });
      setResult(`Disposition accepted (${response.data.status}); chain confirmation will appear in Audit History.`);
      setConfirm(false); setRationale(''); setBusinessRef(newBusinessRef());
    } catch (reason) { setError(reason instanceof ApiError ? reason.message : 'Disposition was not recorded.'); }
    finally { setBusy(false); }
  };
  return <Card className="mb-4" title={<span>Shipment <code className="font-mono text-sm">{shipment.shipment_id}</code></span>} description={`Status: ${shipment.status}. No open incidents are currently returned. Backend workflow prerequisites still apply.`}>
    {quality ? <div className="space-y-3"><p className="text-xs text-slate-600">QUALITY may record a shipment disposition with an empty incident list when appropriate. The backend validates custody, delivery, evidence, and state prerequisites.</p><div className="grid gap-3 sm:grid-cols-2"><label className="text-xs font-medium text-slate-600">Decision<select className="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm" value={decision} onChange={(e) => setDecision(e.target.value as 'RELEASE' | 'QUARANTINE')}><option value="RELEASE">RELEASE</option><option value="QUARANTINE">QUARANTINE</option></select></label><label className="text-xs font-medium text-slate-600">Unique business reference<input className="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 font-mono text-sm" value={businessRef} onChange={(e) => setBusinessRef(e.target.value)} /></label></div><label className="block text-xs font-medium text-slate-600">Rationale<textarea className="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm" rows={2} value={rationale} onChange={(e) => setRationale(e.target.value)} maxLength={4000} /></label>{!confirm ? <Button variant="primary" disabled={!rationale.trim() || !businessRef.trim()} onClick={() => setConfirm(true)}>Review disposition</Button> : <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm"><p>Confirm {decision} for {shipment.shipment_id} with no incident references? This submits an append-only workflow event.</p><div className="mt-3 flex gap-2"><Button variant="primary" disabled={busy || !rationale.trim()} onClick={submit}>{busy ? 'Submitting…' : 'Confirm disposition'}</Button><Button disabled={busy} onClick={() => setConfirm(false)}>Cancel</Button></div></div>}{result && <p role="status" className="text-sm text-emerald-800">{result}</p>}{error && <p role="alert" className="text-sm text-rose-800">{error}</p>}</div> : <p className="text-sm text-slate-600">Only an authenticated QUALITY user can record a disposition.</p>}
  </Card>;
}

function IncidentRow({ incident }: { incident: Incident }) {
  return <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 py-3 last:border-0">
    <div className="min-w-0">
      <div className="flex flex-wrap items-center gap-2"><CategoryBadge category={incident.category} /><SimulatedBadge origin={incident.data_origin} />{incident.latest && <BasisBadge basis={incident.latest.basis} />}</div>
      <Link className="mt-1 block font-mono text-xs text-cyan-700 hover:underline" to={`/incidents/${incident.incident_id}`}>{incident.business_ref}</Link>
      <p className="mt-1 text-sm text-slate-600">{incident.summary ?? 'No incident summary supplied.'}</p>
    </div>
    <div className="text-right text-xs text-slate-500">
      {incident.latest?.gap_continuity_warning && <p><Badge tone="warning">Exposure may have continued during gap</Badge></p>}
      <p className="mt-1">{incident.latest?.observed_duration_min != null ? `${incident.latest.direction ?? 'Observed'} · ${formatMinutes(incident.latest.observed_duration_min)}` : incident.latest?.bracketing_span_min != null ? `Missing data · ${formatMinutes(incident.latest.bracketing_span_min)} · UNKNOWN` : 'Evidence extent UNKNOWN'}</p>
      <p>Raised {formatUtc(incident.opened_at)}</p>
    </div>
  </div>;
}

export function QualityReviewPage() {
  const { identity, hasRole } = useAuth();
  const incidents = useApi(loadOpenIncidents);
  const shipments = useApi(loadShipments);
  const [selectedShipment, setSelectedShipment] = useState('');
  const [decision, setDecision] = useState<'RELEASE' | 'QUARANTINE'>('QUARANTINE');
  const [rationale, setRationale] = useState('');
  const [businessRef, setBusinessRef] = useState(newBusinessRef);
  const [confirmationOpen, setConfirmationOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionResult, setActionResult] = useState<string | null>(null);

  const grouped = useMemo(() => {
    if (incidents.status !== 'success') return [] as [string, Incident[]][];
    const groups = new Map<string, Incident[]>();
    for (const incident of incidents.data.data) groups.set(incident.shipment_id, [...(groups.get(incident.shipment_id) ?? []), incident]);
    return [...groups.entries()];
  }, [incidents]);
  const shipmentId = selectedShipment || grouped[0]?.[0] || '';
  const shipmentIncidents = grouped.find(([id]) => id === shipmentId)?.[1] ?? [];
  const quality = hasRole('QUALITY');
  const allOpenLoaded = incidents.status === 'success' && incidents.data.meta.total <= incidents.data.data.length;
  const noIncidentShipments: Shipment[] = shipments.status === 'success' && allOpenLoaded
    ? shipments.data.data.filter((shipment) => !grouped.some(([id]) => id === shipment.shipment_id))
    : [];

  const submit = async () => {
    if (!shipmentId || !quality || shipmentIncidents.length === 0) return;
    setSubmitting(true); setActionError(null); setActionResult(null);
    try {
      const response = await api.disposition(shipmentId, {
        business_ref: businessRef,
        decision,
        rationale,
        incident_refs: shipmentIncidents.map((item) => item.business_ref),
      });
      setActionResult(`Disposition accepted by the API (${response.data.status}). Chain confirmation is shown in Audit History when available.`);
      setConfirmationOpen(false);
      setRationale('');
      setBusinessRef(newBusinessRef());
      incidents.reload();
    } catch (error) {
      setActionError(error instanceof ApiError ? error.message : 'Disposition was not recorded.');
    } finally { setSubmitting(false); }
  };

  return <>
    <PageHeader title="Quality Review" description="Review incident evidence and record an authorized quality disposition. ML and explanation outputs remain advisory." />
    {!identity && <div role="note" className="mb-4 rounded-lg border border-cyan-200 bg-cyan-50 p-3 text-sm text-cyan-900">Sign in to access authenticated M5/M6 records and workflow actions. <Link className="font-medium underline" to="/login">Sign in</Link></div>}
    {incidents.status === 'loading' && <LoadingState label="Loading open quality incidents…" />}
    {incidents.status === 'error' && <ErrorState error={incidents.error} onRetry={incidents.reload} />}
    {incidents.status === 'success' && grouped.length === 0 && <EmptyState title="No open incidents" description="There are no incidents currently awaiting quality review." />}
    {incidents.status === 'success' && grouped.map(([shipment, items]) => <Card key={shipment} className="mb-5" title={<span>Shipment <code className="font-mono text-sm">{shipment}</code></span>} description={`${items.length} open incident(s); the backend requires all current open incident references on a disposition.`}>
      {items.map((incident) => <IncidentRow key={incident.incident_id} incident={incident} />)}
      <div className="mt-3 flex flex-wrap gap-2">{items.map((incident) => <Link key={incident.incident_id} className="text-xs font-medium text-cyan-700 hover:underline" to={`/incidents/${incident.incident_id}`}>Review evidence: {incident.business_ref}</Link>)}</div>
      {quality ? <div className="mt-5 rounded-xl border border-slate-200 bg-slate-50 p-4">
        <h3 className="text-sm font-semibold text-slate-900">QUALITY disposition</h3>
        <p className="mt-1 text-xs text-slate-600">Only the receiving organization’s QUALITY role can authorize RELEASE or QUARANTINE. Prerequisites are validated by the backend.</p>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <label className="text-xs font-medium text-slate-600">Decision<select className="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm" value={decision} onChange={(e) => setDecision(e.target.value as 'RELEASE' | 'QUARANTINE')}><option value="QUARANTINE">QUARANTINE</option><option value="RELEASE">RELEASE</option></select></label>
          <label className="text-xs font-medium text-slate-600">Unique business reference<input className="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 font-mono text-sm" value={businessRef} onChange={(e) => setBusinessRef(e.target.value)} /></label>
        </div>
        <label className="mt-3 block text-xs font-medium text-slate-600">Rationale<textarea className="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm" rows={3} value={rationale} onChange={(e) => setRationale(e.target.value)} maxLength={4000} /></label>
        <div className="mt-3 flex flex-wrap items-center gap-2"><Button variant="primary" disabled={!rationale.trim() || !businessRef.trim() || !items.length || !allOpenLoaded} onClick={() => { setSelectedShipment(shipment); setActionError(null); setConfirmationOpen(true); }}>Review disposition</Button>{!allOpenLoaded && <span className="text-xs text-amber-800">More open incidents exist than this page can load; submission is disabled to avoid omitting required references.</span>}{actionResult && <span role="status" className="text-sm text-emerald-800">{actionResult}</span>}</div>
        {confirmationOpen && shipmentId === shipment && <div className="mt-4 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-950"><p className="font-semibold">Confirm {decision} for {shipment}?</p><p className="mt-1">This records a workflow event and submits it for chain confirmation. The decision cannot be undone in the UI.</p><p className="mt-1">{items.length} open incident reference(s) will be included.</p><div className="mt-3 flex gap-2"><Button variant="primary" disabled={submitting || !rationale.trim()} onClick={submit}>{submitting ? 'Submitting…' : 'Confirm disposition'}</Button><Button disabled={submitting} onClick={() => setConfirmationOpen(false)}>Cancel</Button></div></div>}
        {actionError && <p role="alert" className="mt-3 rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">{actionError}</p>}
      </div> : <p className="mt-4 rounded-lg bg-slate-50 p-3 text-sm text-slate-600">Disposition controls are available only to an authenticated QUALITY user. Backend authorization remains enforced for every request.</p>}
    </Card>)}
    {shipments.status === 'loading' && <LoadingState label="Loading shipments without open incidents…" />}
    {shipments.status === 'error' && <ErrorState error={shipments.error} onRetry={shipments.reload} />}
    {shipments.status === 'success' && noIncidentShipments.length > 0 && <><h2 className="mb-3 mt-8 text-lg font-semibold text-slate-900">Shipments with no open incidents</h2><p className="mb-4 text-sm text-slate-600">The backend still requires an authorized RELEASE disposition before warehouse release for shipments without incidents.</p>{noIncidentShipments.map((shipment) => <ShipmentWithoutIncidents key={shipment.shipment_id} shipment={shipment} quality={quality} />)}</>}
  </>;
}
