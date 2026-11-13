import type { ReactNode } from 'react';
import type { Policy } from '../api/types';
import { formatTempC, formatUtc } from '../format';
import { Badge } from './ui/Badge';
import { KeyValueList } from './ui/KeyValueList';

/** Renders a policy exactly as returned by the API. No values are defined in the frontend. */
export function PolicySummary({ policy, detailed = false }: { policy: Policy; detailed?: boolean }) {
  const { limits, duration_rule: d, missing_data_rule: m } = policy;
  const items: { label: string; value: ReactNode }[] = [
    { label: 'Product', value: `${policy.product_name} (${policy.product_id})` },
    { label: 'Acceptable range', value: `${formatTempC(limits.min_temp_c)} – ${formatTempC(limits.max_temp_c)}` },
    {
      label: 'High excursion',
      value: `Above ${formatTempC(limits.max_temp_c)} for at least ${d.high_excursion_min_duration_min} min`,
    },
    {
      label: 'Low excursion',
      value: `Below ${formatTempC(limits.min_temp_c)} for at least ${d.low_excursion_min_duration_min} min`,
    },
    { label: 'Missing data', value: `Gap longer than ${m.gap_unknown_after_min} min is UNKNOWN (never treated as safe)` },
    { label: 'Quality review', value: `Required for a gap of at least ${m.gap_review_at_min} min` },
    { label: 'Release authority', value: `${policy.release_authority_role} role only` },
  ];
  if (detailed) {
    items.push(
      { label: 'Procedure version', value: policy.procedure_version },
      { label: 'Effective from', value: formatUtc(policy.effective_from) },
      { label: 'Source file', value: <code className="font-mono text-xs">{policy.source_file}</code> },
      { label: 'Content SHA-256', value: <code className="font-mono text-xs break-all">{policy.content_sha256}</code> },
      { label: 'Approval', value: policy.approval_reference },
    );
  }
  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span className="text-sm font-semibold text-slate-900">
          {policy.policy_code} v{policy.policy_version}
        </span>
        <Badge tone={policy.status === 'ACTIVE' ? 'success' : 'muted'}>{policy.status}</Badge>
        {policy.is_teaching_policy && <Badge tone="warning">Teaching policy</Badge>}
      </div>
      <KeyValueList items={items} />
      <p className="mt-3 rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-800">{policy.disclaimer}</p>
    </div>
  );
}
