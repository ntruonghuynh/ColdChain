import { useCallback, useState } from 'react';
import { Link } from 'react-router';
import { api } from '../../api/client';
import type { ExplanationHistoryItem, StoredExplanation } from '../../api/client';
import { useAuth } from '../../auth/AuthContext';
import { Badge } from '../ui/Badge';
import { Card } from '../ui/Card';
import { EmptyState, ErrorState, LoadingState } from '../ui/States';
import { formatUtc } from '../../format';
import { useApi } from '../../hooks/useApi';

function ExplanationDetail({ id }: { id: string }) {
  const fetcher = useCallback((signal: AbortSignal) => api.explanation(id, { signal }), [id]);
  const detail = useApi(fetcher);
  if (detail.status === 'loading') return <LoadingState label="Loading stored explanation…" />;
  if (detail.status === 'error') return <ErrorState error={detail.error} onRetry={detail.reload} />;
  const item: StoredExplanation = detail.data.data;
  const validation = item.validation_diagnostics;
  return <div className="space-y-4">
    <div className="flex flex-wrap gap-2"><Badge tone={item.explanation_status === 'draft' || item.explanation_status === 'fallback' ? 'info' : 'warning'}>{item.explanation_status}</Badge><Badge>{item.source_mode}</Badge><Badge tone={item.citation_verification === 'passed' ? 'success' : item.citation_verification === 'failed' ? 'danger' : 'muted'}>Citation checks: {item.citation_verification}</Badge></div>
    <dl className="grid gap-x-4 gap-y-2 text-sm sm:grid-cols-2"><div><dt className="text-xs text-slate-500">Provider / model</dt><dd>{item.provider} / {item.model ?? 'not specified'}</dd></div><div><dt className="text-xs text-slate-500">Prompt version</dt><dd>{item.prompt_version}</dd></div><div><dt className="text-xs text-slate-500">Evidence cutoff</dt><dd>{formatUtc(item.evidence_cutoff_at)}</dd></div><div><dt className="text-xs text-slate-500">Sensor interval</dt><dd>{formatUtc(item.sensor_interval_start_at)} → {formatUtc(item.sensor_interval_end_at)}</dd></div><div><dt className="text-xs text-slate-500">Policy / SOP version</dt><dd>{item.policy_version} / {item.procedure_version}</dd></div><div><dt className="text-xs text-slate-500">Document versions</dt><dd>{item.document_versions.join(', ') || 'None recorded'}</dd></div></dl>
    <div className="rounded-lg border border-cyan-200 bg-cyan-50 p-3 text-sm text-cyan-950"><p className="font-semibold">Application checks are not semantic review</p><p className="mt-1">Application validation: {validation.application_validation_status}; citation matching: {validation.citation_validation_status}; evidence check: {validation.evidence_validation_status}; temporal check: {validation.temporal_validation_status}. These checks establish that stored claims and citations passed the recorded validators; they do not independently establish that every explanation is factually or clinically correct.</p></div>
    <div><h4 className="text-sm font-semibold text-slate-800">Stored response</h4><p className="mt-1 text-sm text-slate-700">{item.summary_vi}</p></div>
    {!!item.citations.length && <div><h4 className="text-sm font-semibold text-slate-800">SOP and evidence citations</h4><ul className="mt-2 space-y-2">{item.citations.map((citation, index) => <li key={`${citation.source_id}-${index}`} className="rounded-lg border border-slate-200 p-3 text-sm"><p className="font-mono text-xs text-cyan-800">{citation.source_id}</p><p className="mt-1">{citation.claim}</p>{citation.quote && <blockquote className="mt-2 border-l-2 border-slate-300 pl-3 text-slate-600">“{citation.quote}”</blockquote>}</li>)}</ul></div>}
    <div><h4 className="text-sm font-semibold text-slate-800">Evidence references</h4><p className="mt-1 break-words font-mono text-xs text-slate-600">{item.evidence_references.join(' · ') || 'No evidence references recorded.'}</p></div>
    {!!item.unknowns_vi.length && <div role="note" className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-950"><strong>Unknown / missing evidence</strong><ul className="mt-1 list-disc pl-5">{item.unknowns_vi.map((value, index) => <li key={index}>{value}</li>)}</ul></div>}
    {!!item.evidence_needed_vi.length && <div><h4 className="text-sm font-semibold text-slate-800">Evidence still needed</h4><ul className="list-disc pl-5 text-sm text-slate-700">{item.evidence_needed_vi.map((value, index) => <li key={index}>{value}</li>)}</ul></div>}
    <p className="text-xs text-slate-500">Advisory explanation only. It cannot authorize RELEASE or QUARANTINE.</p>
  </div>;
}

function StoredExplanationList({ incidentId }: { incidentId: string }) {
  const fetcher = useCallback((signal: AbortSignal) => api.explanationHistory(incidentId, { signal }), [incidentId]);
  const history = useApi(fetcher);
  const [selected, setSelected] = useState('');
  if (history.status === 'loading') return <LoadingState label="Loading stored explanation history…" />;
  if (history.status === 'error') return <ErrorState error={history.error} onRetry={history.reload} />;
  const rows: ExplanationHistoryItem[] = history.data.data;
  if (!rows.length) return <EmptyState title="No stored explanations" description="Opening an incident does not generate an explanation. No existing M6 record is available for this incident." />;
  const selectedId = rows.some((row) => row.explanation_id === selected) ? selected : (rows[0]?.explanation_id ?? '');
  return <div className="space-y-4"><label className="block text-xs font-medium text-slate-600">Stored explanation<select className="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm" value={selectedId} onChange={(event) => setSelected(event.target.value)}>{rows.map((row) => <option key={row.explanation_id} value={row.explanation_id}>{formatUtc(row.explained_at)} · {row.explanation_status} · {row.source_mode}</option>)}</select></label><ExplanationDetail id={selectedId} /></div>;
}

export function ExplanationHistory({ incidentId }: { incidentId: string }) {
  const { identity } = useAuth();
  return <Card title="Stored M6 explanation history" description="Read-only stored output and citations. This page never requests a new explanation or calls an LLM provider.">{identity ? <StoredExplanationList incidentId={incidentId} /> : <p className="text-sm text-slate-600">Sign in to view stored M6 explanation history. <Link className="text-cyan-700 underline" to="/login">Sign in</Link></p>}</Card>;
}
