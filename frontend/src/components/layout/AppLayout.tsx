import { useState } from 'react';
import { Outlet, useLocation } from 'react-router';
import { NAV_ITEMS } from '../../navigation';
import { Header } from './Header';
import { Sidebar } from './Sidebar';

export function AppLayout() {
  const [navOpen, setNavOpen] = useState(false);
  const { pathname } = useLocation();
  const current = NAV_ITEMS.find((item) => (item.path === '/' ? pathname === '/' : pathname.startsWith(item.path)));
  const title = pathname.startsWith('/incidents/') ? 'Incident Details' : current?.label ?? 'Page not found';

  return (
    <div className="flex h-full">
      <Sidebar open={navOpen} onClose={() => setNavOpen(false)} />
      <div className="flex min-w-0 flex-1 flex-col">
        <Header title={title} onMenu={() => setNavOpen(true)} />
        <main className="flex-1 overflow-y-auto">
          <div className="mx-auto max-w-6xl px-4 py-6 sm:px-6 lg:px-8">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
