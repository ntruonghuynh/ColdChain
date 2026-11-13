import { Snowflake, X } from 'lucide-react';
import { NavLink } from 'react-router';
import { NAV_ITEMS } from '../../navigation';

export function Sidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  return (
    <>
      {/* Mobile overlay */}
      <div
        className={`fixed inset-0 z-30 bg-slate-900/40 lg:hidden ${open ? 'block' : 'hidden'}`}
        onClick={onClose}
        aria-hidden="true"
      />
      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-64 flex-col bg-navy-900 text-slate-200 transition-transform lg:static lg:translate-x-0 ${
          open ? 'translate-x-0' : '-translate-x-full'
        }`}
        aria-label="Main navigation"
      >
        <div className="flex h-16 items-center justify-between gap-2 border-b border-white/10 px-5">
          <div className="flex items-center gap-2.5">
            <div className="rounded-lg bg-frost-500/15 p-1.5 text-frost-400">
              <Snowflake className="h-5 w-5" aria-hidden="true" />
            </div>
            <div className="leading-tight">
              <p className="text-sm font-semibold text-white">ColdChain Monitor</p>
              <p className="text-[11px] text-slate-400">Excursion response</p>
            </div>
          </div>
          <button type="button" className="rounded p-1 text-slate-400 hover:text-white lg:hidden" onClick={onClose}>
            <X className="h-5 w-5" aria-hidden="true" />
            <span className="sr-only">Close navigation</span>
          </button>
        </div>

        <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-4">
          {NAV_ITEMS.map(({ path, label, icon: Icon, plannedMilestone }) => (
            <NavLink
              key={path}
              to={path}
              end={path === '/'}
              onClick={onClose}
              className={({ isActive }) =>
                `group flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                  isActive ? 'bg-white/10 text-white' : 'text-slate-300 hover:bg-white/5 hover:text-white'
                }`
              }
            >
              <Icon className="h-4.5 w-4.5 shrink-0" aria-hidden="true" />
              <span className="flex-1 truncate">{label}</span>
              {plannedMilestone && (
                <span
                  className="rounded bg-white/5 px-1.5 py-0.5 text-[10px] font-medium text-slate-400"
                  title={`Not implemented yet — planned for ${plannedMilestone}`}
                >
                  {plannedMilestone}
                </span>
              )}
            </NavLink>
          ))}
        </nav>

        <div className="border-t border-white/10 px-5 py-4 text-[11px] leading-relaxed text-slate-400">
          Teaching prototype. All data is simulated; policies are not regulatory standards.
        </div>
      </aside>
    </>
  );
}
