import { AlertTriangle, Inbox, Loader2, RefreshCw } from 'lucide-react';
import type { ReactNode } from 'react';
import type { ApiError } from '../../api/client';
import { Button } from './Button';

export function LoadingState({ label = 'Loading…' }: { label?: string }) {
  return (
    <div role="status" aria-live="polite" className="flex items-center gap-2 py-6 text-sm text-slate-500">
      <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
      {label}
    </div>
  );
}

export function EmptyState({
  title,
  description,
  icon,
}: {
  title: string;
  description?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-4 py-10 text-center">
      <div className="rounded-full bg-slate-100 p-3 text-slate-400">{icon ?? <Inbox className="h-6 w-6" />}</div>
      <p className="text-sm font-medium text-slate-700">{title}</p>
      {description && <p className="max-w-md text-sm text-slate-500">{description}</p>}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: ApiError; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex flex-col gap-3 rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm">
      <div className="flex items-start gap-2 text-rose-800">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
        <div>
          <p className="font-medium">{error.message}</p>
          <p className="mt-0.5 text-xs text-rose-700">
            Code: {error.code}
            {error.status !== null && ` · HTTP ${error.status}`}
            {error.requestId && ` · Request ${error.requestId}`}
          </p>
        </div>
      </div>
      {onRetry && (
        <div>
          <Button onClick={onRetry}>
            <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" /> Try again
          </Button>
        </div>
      )}
    </div>
  );
}
