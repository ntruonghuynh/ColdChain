import { FlaskConical, Menu } from 'lucide-react';
import { ConnectivityIndicator } from '../ConnectivityIndicator';

export function Header({ title, onMenu }: { title: string; onMenu: () => void }) {
  return (
    <header className="sticky top-0 z-20 flex h-16 items-center gap-3 border-b border-slate-200 bg-white/90 px-4 backdrop-blur sm:px-6">
      <button
        type="button"
        className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100 lg:hidden"
        onClick={onMenu}
      >
        <Menu className="h-5 w-5" aria-hidden="true" />
        <span className="sr-only">Open navigation</span>
      </button>
      <p className="min-w-0 flex-1 truncate text-sm font-medium text-slate-600">{title}</p>
      <span
        className="inline-flex shrink-0 items-center gap-1.5 rounded-full bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-800 ring-1 ring-amber-200"
        title="All data in this prototype is simulated. Policies are teaching rules, not regulatory standards."
      >
        <FlaskConical className="h-3.5 w-3.5" aria-hidden="true" />
        <span className="hidden sm:inline">Simulated data · Teaching policy</span>
        <span className="sm:hidden">Simulated</span>
      </span>
      <ConnectivityIndicator />
    </header>
  );
}
