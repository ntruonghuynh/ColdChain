import { useCallback, useState } from 'react';
import type { FormEvent } from 'react';
import { Link } from 'react-router';
import { api, ApiError } from '../api/client';
import type { AuditEntry, BusinessVerification, LedgerTransaction } from '../api/client';
import { useAuth } from '../auth/AuthContext';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { PageHeader } from '../components/ui/PageHeader';
import { EmptyState, ErrorState, LoadingState } from '../components/ui/States';
import { formatUtc } from '../format';
import { useApi } from '../hooks/useApi';

const loadTransactions = (signal: AbortSignal) => api.transactions(200, { signal });
const loadAudit = (signal: AbortSignal) => api.auditHistory(200, { signal });

function TransactionTable({ rows }: { rows: LedgerTransaction[] }) {
  if (!rows.length) return <EmptyState title="No ledger transactions" />;
  return <div className="overflow-x-auto"><table className="min-w-full text-sm"><thead className="border-b text-left text-xs uppercase text-slate-500"><tr><th className="px-3 py-2">Business reference</th><th className="px-3 py-2">Event</th><th className="px-3 py-2">Shipment</th><th className="px-3 py-2">Outbox</th><th className="px-3 py-2">Attempts</th><th className="px-3 py-2">Transaction</th></tr></thead><tbody className="divide-y divide-slate-100">{rows.map((row) => <tr key={row.event_id}><td className="px-3 py-2 font-mono text-xs">{row.business_ref}</td><td className="px-3 py-2">{row.event_type}</td><td className="px-3 py-2 font-mono text-xs">{row.shipment_id}</td><td className="px-3 py-2"><Badge tone={row.outbox_status === 'CONFIRMED' ? 'success' : row.outbox_status === 'FAILED' ? 'danger' : 'warning'}>{row.outbox_status}</Badge>{row.last_error && <p className="mt-1 max-w-xs text-xs text-rose-700">{row.last_error}</p>}</td><td className="px-3 py-2">{row.attempts}</td><td className="px-3 py-2 font-mono text-xs">{row.transaction ? <><span>{row.transaction.tx_hash.slice(0, 16)}…</span><div>Block {row.transaction.block_number} · {formatUtc(row.transaction.confirmed_at)}</div></> : 'Not confirmed'}</td></tr>)}</tbody></table></div>;
}

function AuditTable({ rows }: { rows: AuditEntry[] }) {
  if (!rows.length) return <EmptyState title="No signed audit entries" />;
  return <div className="overflow-x-auto"><table className="min-w-full text-sm"><thead className="border-b text-left text-xs uppercase text-slate-500"><tr><th className="px-3 py-2">Sequence</th><th className="px-3 py-2">Time</th><th className="px-3 py-2">Action</th><th className="px-3 py-2">Business reference</th><th className="px-3 py-2">Actor</th><th className="px-3 py-2">Entry hash</th><th className="px-3 py-2">Record</th></tr></thead><tbody className="divide-y divide-slate-100">{rows.map((row) => <tr key={row.sequence_no}><td className="px-3 py-2">{row.sequence_no}</td><td className="px-3 py-2 whitespace-nowrap">{formatUtc(row.created_at)}</td><td className="px-3 py-2">{row.action}</td><td className="px-3 py-2 font-mono text-xs">{row.business_ref}</td><td className="px-3 py-2 text-xs">{row.actor_org_id ?? 'system'} · {row.actor_user_id ?? '—'}</td><td className="px-3 py-2 font-mono text-xs">{row.entry_hash.slice(0, 18)}…</td><td className="px-3 py-2"><details><summary className="cursor-pointer text-cyan-700">Details</summary><pre className="mt-2 max-w-xl overflow-auto rounded bg-slate-50 p-2 text-xs">{JSON.stringify(row.record, null, 2)}</pre></details></td></tr>)}</tbody></table></div>;
}

function AdminChecks() {
  const [reconciliation, setReconciliation] = useState<unknown>(null);
  const [auditCheck, setAuditCheck] = useState<unknown>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const run = async (kind: 'reconciliation' | 'audit') => {
    setBusy(true); setError(null);
    try {
      if (kind === 'reconciliation') setReconciliation((await api.reconcile()).data);
      else setAuditCheck((await api.verifyAudit()).data);
    } catch (reason) { setError(reason instanceof ApiError ? reason.message : 'Verification could not be completed.'); }
    finally { setBusy(false); }
  };
  return <Card title="Administrator verification" description="These read-only checks are available only to ADMIN; the backend enforces the role.">
    <div className="flex flex-wrap gap-2"><Button disabled={busy} onClick={() => run('reconciliation')}>Run chain reconciliation</Button><Button disabled={busy} onClick={() => run('audit')}>Verify signed audit chain</Button></div>
    {error && <p role="alert" className="mt-3 text-sm text-rose-800">{error}</p>}
    {reconciliation !== null && <pre className="mt-3 max-h-80 overflow-auto rounded-lg bg-slate-950 p-3 text-xs text-slate-100">{JSON.stringify(reconciliation, null, 2) ?? ''}</pre>}
    {auditCheck !== null && <pre className="mt-3 max-h-80 overflow-auto rounded-lg bg-slate-950 p-3 text-xs text-slate-100">{JSON.stringify(auditCheck, null, 2) ?? ''}</pre>}
  </Card>;
}

export function AuditHistoryPage() {
  const { identity, hasRole } = useAuth();
  const txFetcher = useCallback((signal: AbortSignal) => identity ? loadTransactions(signal) : Promise.resolve({ data: [], meta: null }), [identity]);
  const auditFetcher = useCallback((signal: AbortSignal) => identity ? loadAudit(signal) : Promise.resolve({ data: [], meta: null }), [identity]);
  const transactions = useApi(txFetcher);
  const audit = useApi(auditFetcher);
  const [businessRef, setBusinessRef] = useState('');
  const [verification, setVerification] = useState<BusinessVerification | null>(null);
  const [verifyError, setVerifyError] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);
  const admin = hasRole('ADMIN');

  const verify = async (event: FormEvent) => {
    event.preventDefault(); setChecking(true); setVerifyError(null); setVerification(null);
    if (!identity) { setVerifyError('Sign in before verifying a business reference.'); setChecking(false); return; }
    try { setVerification((await api.verifyBusinessRef(businessRef.trim())).data); }
    catch (reason) { setVerifyError(reason instanceof ApiError ? reason.message : 'Reference verification failed.'); }
    finally { setChecking(false); }
  };

  return <>
    <PageHeader title="Audit History" description="Read-only blockchain transaction status, signed audit records and partner reference verification." />
    {!identity && <div role="note" className="mb-4 rounded-lg border border-cyan-200 bg-cyan-50 p-3 text-sm text-cyan-900">Sign in to read ledger and signed-audit records. <Link className="font-medium underline" to="/login">Sign in</Link></div>}
    <Card className="mb-5" title="Business reference verification" description="Checks the stored event and on-chain hash using the existing read-only verification API.">
      <form className="flex flex-wrap gap-2" onSubmit={verify}><input aria-label="Business reference" className="min-w-64 flex-1 rounded-lg border border-slate-300 px-3 py-2 font-mono text-sm" value={businessRef} onChange={(e) => setBusinessRef(e.target.value)} placeholder="Enter a business reference" required /><Button variant="primary" disabled={checking || !identity}>{checking ? 'Checking…' : 'Verify reference'}</Button></form>
      {verifyError && <p role="alert" className="mt-3 text-sm text-rose-800">{verifyError}</p>}
      {verification && <div className="mt-3 rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm"><p><strong>{verification.verification_status}</strong> · verified {verification.verified ? 'yes' : 'no'}</p><p>Outbox: {verification.outbox_status} · chain record present: {String(verification.chain_record_present)}</p>{verification.database_payload_sha256 && <p className="break-all font-mono text-xs">Database payload SHA-256: {verification.database_payload_sha256}</p>}</div>}
    </Card>
    <Card className="mb-5" title="Blockchain transactions" description="Worker retries are automatic. Status and attempt count are observed here; this page does not trigger retries.">
      {transactions.status === 'loading' && <LoadingState />}{transactions.status === 'error' && <ErrorState error={transactions.error} onRetry={transactions.reload} />}{transactions.status === 'success' && <TransactionTable rows={transactions.data.data} />}
    </Card>
    <Card className="mb-5" title="Signed audit history" description="Append-only signed records returned by the backend.">
      {audit.status === 'loading' && <LoadingState />}{audit.status === 'error' && <ErrorState error={audit.error} onRetry={audit.reload} />}{audit.status === 'success' && <AuditTable rows={audit.data.data} />}
    </Card>
    {admin && <AdminChecks />}
    {identity && !admin && <p role="note" className="text-xs text-slate-500">Chain reconciliation and signed-audit verification controls are only shown to ADMIN. The API independently enforces both restrictions.</p>}
  </>;
}
