# frontend/

React 19 + TypeScript (strict) + Vite 7 + Tailwind CSS 4. Built in Docker and served by nginx, which also reverse-proxies `/api` to the backend.

**Milestone 1:** application shell. Overview, Shipments and System Settings show live API data (health, active teaching policy, shipment list, organizations, feature status). Temperature Monitoring, Excursion Queue, Quality Review and Audit History say "Not implemented yet" and show no data.

| Path | Purpose |
|---|---|
| `src/api/` | Typed API client (`client.ts`: envelope parsing, `ApiError`, timeouts) and response types |
| `src/hooks/` | `useApi` (loading / success / error with retry), `connectivity.tsx` (health polling every 15 s) |
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
