import { useCallback } from 'react';
import { api } from '../../api/client';
import { Badge } from '../ui/Badge';
import { Card } from '../ui/Card';
import { ErrorState, LoadingState } from '../ui/States';
import { useApi } from '../../hooks/useApi';

export function ModelReadinessCard() {
  const fetcher = useCallback((signal: AbortSignal) => api.modelReadiness({ signal }), []);
  const readiness = useApi(fetcher);
  return <Card title="M4 advisory model" description="Readiness only. This view does not score a window or append a prediction record.">
    {readiness.status === 'loading' && <LoadingState label="Checking frozen model readiness…" />}
    {readiness.status === 'error' && <ErrorState error={readiness.error} onRetry={readiness.reload} />}
    {readiness.status === 'success' && <div className="space-y-2 text-sm"><div className="flex items-center gap-2"><Badge tone={readiness.data.data.status === 'ready' ? 'success' : 'warning'}>{readiness.data.data.status}</Badge><span className="font-mono text-xs">{readiness.data.data.model_version}</span></div>{readiness.data.data.detail && <p className="text-slate-600">Detail: {readiness.data.data.detail}</p>}<p className="text-slate-600">Prediction history is not available through a GET API. Scoring is an append-only POST and is not invoked from this page. No prediction is treated as a safety determination.</p></div>}
  </Card>;
}
