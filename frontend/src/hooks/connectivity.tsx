import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { ApiError, getHealth } from '../api/client';
import type { HealthReport } from '../api/types';

/**
 * checking - first check in progress
 * online   - API and database ready
 * degraded - API answers but a dependency (database / migrations) is not ready
 * offline  - API not reachable
 */
export type ConnectivityStatus = 'checking' | 'online' | 'degraded' | 'offline';

export interface ConnectivityState {
  status: ConnectivityStatus;
  report: HealthReport | null;
  error: ApiError | null;
  lastChecked: Date | null;
  checkNow: () => void;
}

const ConnectivityContext = createContext<ConnectivityState | null>(null);

export const HEALTH_POLL_INTERVAL_MS = 15_000;

export function ConnectivityProvider({
  children,
  intervalMs = HEALTH_POLL_INTERVAL_MS,
}: {
  children: ReactNode;
  intervalMs?: number;
}) {
  const [state, setState] = useState<Omit<ConnectivityState, 'checkNow'>>({
    status: 'checking',
    report: null,
    error: null,
    lastChecked: null,
  });
  const inFlight = useRef<AbortController | null>(null);

  const check = useCallback(async () => {
    inFlight.current?.abort();
    const controller = new AbortController();
    inFlight.current = controller;
    try {
      const report = await getHealth({ signal: controller.signal });
      if (controller.signal.aborted) return;
      setState({
        status: report.status === 'ok' ? 'online' : 'degraded',
        report,
        error: null,
        lastChecked: new Date(),
      });
    } catch (err) {
      if (controller.signal.aborted) return;
      setState({
        status: 'offline',
        report: null,
        error: err instanceof ApiError ? err : new ApiError({ kind: 'network', message: String(err) }),
        lastChecked: new Date(),
      });
    }
  }, []);

  useEffect(() => {
    void check();
    const id = setInterval(() => void check(), intervalMs);
    return () => {
      clearInterval(id);
      inFlight.current?.abort();
    };
  }, [check, intervalMs]);

  return (
    <ConnectivityContext.Provider value={{ ...state, checkNow: () => void check() }}>
      {children}
    </ConnectivityContext.Provider>
  );
}

export function useConnectivity(): ConnectivityState {
  const ctx = useContext(ConnectivityContext);
  if (!ctx) throw new Error('useConnectivity must be used inside ConnectivityProvider');
  return ctx;
}
