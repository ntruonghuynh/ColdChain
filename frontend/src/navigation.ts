import {
  ClipboardCheck,
  History,
  LayoutDashboard,
  ListChecks,
  Package,
  Settings,
  Thermometer,
  type LucideIcon,
} from 'lucide-react';

export interface NavItem {
  path: string;
  label: string;
  icon: LucideIcon;
}

export const NAV_ITEMS: NavItem[] = [
  { path: '/', label: 'Overview', icon: LayoutDashboard },
  { path: '/shipments', label: 'Shipments', icon: Package },
  { path: '/temperature', label: 'Temperature Monitoring', icon: Thermometer },
  { path: '/excursions', label: 'Excursion Queue', icon: ListChecks },
  { path: '/quality-review', label: 'Quality Review', icon: ClipboardCheck },
  { path: '/audit', label: 'Audit History', icon: History },
  { path: '/settings', label: 'System Settings', icon: Settings },
];
