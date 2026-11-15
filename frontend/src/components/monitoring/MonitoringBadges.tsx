import type { GapStatus, Incident, MonitoringState } from '../../api/types';
import { Badge, type BadgeTone } from '../ui/Badge';

const STATE_TONE: Record<MonitoringState, BadgeTone> = {
  CURRENT: 'success',
  STALE: 'warning',
  UNKNOWN: 'danger',
  NOT_STARTED: 'muted',
  ENDED: 'muted',
};

/** Missing or stale telemetry is never shown in a "safe" colour. */
export function MonitoringStateBadge({ state }: { state: MonitoringState }) {
  return <Badge tone={STATE_TONE[state]}>{state}</Badge>;
}

const GAP_LABEL: Record<GapStatus, string> = {
  SHORT_GAP: 'Short gap',
  UNKNOWN: 'UNKNOWN',
  UNKNOWN_REVIEW_REQUIRED: 'UNKNOWN · review required',
};

export function GapStatusBadge({ status }: { status: GapStatus }) {
  return <Badge tone={status === 'SHORT_GAP' ? 'warning' : 'danger'}>{GAP_LABEL[status]}</Badge>;
}

export function CategoryBadge({ category }: { category: Incident['category'] }) {
  if (category === 'TEMPERATURE_EXCURSION') return <Badge tone="danger">Temperature excursion</Badge>;
  if (category === 'DATA_GAP') return <Badge tone="warning">Data gap</Badge>;
  return <Badge tone="info">Suspected sensor fault</Badge>;
}

export function BasisBadge({ basis }: { basis: string }) {
  if (basis === 'CURRENT') return <Badge tone="neutral">Evidence current</Badge>;
  if (basis === 'SUPERSEDED_BY_DATA') return <Badge tone="info">Superseded by later data</Badge>;
  return <Badge tone="info">Merged</Badge>;
}

export function SimulatedBadge({ origin }: { origin: string | null | undefined }) {
  return origin === 'SIMULATED' ? <Badge tone="warning">SIMULATED DATA</Badge> : <Badge tone="info">{origin ?? '—'}</Badge>;
}
