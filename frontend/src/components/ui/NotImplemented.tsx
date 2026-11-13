import { Construction } from 'lucide-react';
import { Badge } from './Badge';
import { Card } from './Card';

/** Placeholder for views that depend on future milestones. Shows no data on purpose. */
export function NotImplemented({ milestone, planned }: { milestone: string; planned: string[] }) {
  return (
    <Card>
      <div className="flex flex-col items-center gap-3 px-2 py-10 text-center">
        <div className="rounded-full bg-amber-50 p-3 text-amber-600 ring-1 ring-amber-200">
          <Construction className="h-6 w-6" aria-hidden="true" />
        </div>
        <h2 className="text-base font-semibold text-slate-900">Not implemented yet</h2>
        <Badge tone="warning">Planned for {milestone}</Badge>
        <p className="max-w-lg text-sm text-slate-500">
          This view has no data yet. It will become available when the milestone below is delivered.
        </p>
        <ul className="mt-2 max-w-lg space-y-1.5 text-left text-sm text-slate-600">
          {planned.map((item) => (
            <li key={item} className="flex gap-2">
              <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-slate-300" aria-hidden="true" />
              {item}
            </li>
          ))}
        </ul>
      </div>
    </Card>
  );
}
