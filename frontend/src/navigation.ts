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
  /** Milestone in which the view becomes functional; undefined = available now. */
  plannedMilestone?: string;
}

export const NAV_ITEMS: NavItem[] = [
  { path: '/', label: 'Overview', icon: LayoutDashboard },
  { path: '/shipments', label: 'Shipments', icon: Package },
  { path: '/temperature', label: 'Temperature Monitoring', icon: Thermometer, plannedMilestone: 'M3/M7' },
  { path: '/excursions', label: 'Excursion Queue', icon: ListChecks, plannedMilestone: 'M3/M7' },
  { path: '/quality-review', label: 'Quality Review', icon: ClipboardCheck, plannedMilestone: 'M5–M7' },
  { path: '/audit', label: 'Audit History', icon: History, plannedMilestone: 'M5' },
  { path: '/settings', label: 'System Settings', icon: Settings },
];
