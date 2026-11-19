# frontend/

React 19 + TypeScript (strict) + Vite 7 + Tailwind CSS 4. Built in Docker and served by nginx, which also reverse-proxies `/api` to the backend.

**M1–M3:** Overview, Shipments, System Settings, Temperature Monitoring, Excursion Queue and Incident Details use live backend data. Monitoring is causal by "view as of"; missing intervals are never shown as in range.

**M4–M6 frontend integrations:** sign-in uses in-memory bearer tokens; Quality Review exposes an explicitly confirmed QUALITY disposition; incident details read stored explanation history and citations without generating explanations; the Audit History page reads ledger, verification and signed-audit APIs. Reconciliation and signed-audit verification controls are ADMIN-only. Temperature Monitoring shows ML model readiness only. The backend currently has no prediction-history GET and its append-only scoring POST is unauthenticated, so the frontend does not invoke it.

Warehouse release is a separate WAREHOUSE action and is shown on an incident only after the related QUALITY RELEASE verifies on chain. Viewing an incident never creates an explanation or prediction. Credentials are entered by the user and are not stored; the bearer token remains in memory and is cleared on reload or HTTP 401.

| Path | Purpose |
|---|---|
| `src/api/` | Typed API client (`client.ts`: envelope parsing, `ApiError`, timeouts) and response types |
| `src/hooks/` | `useApi` (loading / success / error with retry), `connectivity.tsx` (health polling every 15 s) |
| `src/auth/` | In-memory sign-in state, `/auth/me`, bearer attachment and session invalidation |
| `src/components/layout/` | App layout, sidebar navigation, header |
| `src/components/ui/` | Card, Badge, Button, loading / empty / error states, Not-implemented panel, key-value list |
| `src/components/ConnectivityIndicator.tsx` | Header indicator: connected / degraded / unreachable |
| `src/pages/` | One component per navigation entry |
| `src/navigation.ts` | Navigation entries and the milestone that delivers each view |
| `nginx.conf` | SPA fallback, `/api` proxy, JSON `api_unreachable` error when the backend is down |

The frontend contains no business rules and no example data: every value comes from the API.

```bash
npm ci
npm test            # Vitest + Testing Library (19 tests)
npm run typecheck
npm run build
npm run dev         # http://localhost:5173, proxies /api to http://localhost:8000
```
