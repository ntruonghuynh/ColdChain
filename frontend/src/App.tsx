import { Route, Routes } from 'react-router';
import { AppLayout } from './components/layout/AppLayout';
import { ConnectivityProvider } from './hooks/connectivity';
import { NotFoundPage } from './pages/NotFoundPage';
import { OverviewPage } from './pages/OverviewPage';
import {
  AuditHistoryPage,
  ExcursionQueuePage,
  QualityReviewPage,
  TemperatureMonitoringPage,
} from './pages/PlannedPages';
import { SettingsPage } from './pages/SettingsPage';
import { ShipmentsPage } from './pages/ShipmentsPage';

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<OverviewPage />} />
        <Route path="shipments" element={<ShipmentsPage />} />
        <Route path="temperature" element={<TemperatureMonitoringPage />} />
        <Route path="excursions" element={<ExcursionQueuePage />} />
        <Route path="quality-review" element={<QualityReviewPage />} />
        <Route path="audit" element={<AuditHistoryPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}

export function App() {
  return (
    <ConnectivityProvider>
      <AppRoutes />
    </ConnectivityProvider>
  );
}
