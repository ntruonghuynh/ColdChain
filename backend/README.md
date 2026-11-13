# backend/

**Status: not implemented.** Scheduled from Milestone 1 (skeleton, schema), then M3 (ingestion, gaps, threshold baseline), M5 (dispositions, release gate, outbox worker, chain gateway, signed audit log) and M6 (LLM adapter, evidence package).

Planned layout (see `docs/architecture.md` §3.2):

| Path | Purpose |
|---|---|
| `app/api/` | FastAPI routes and Pydantic schemas, no business logic |
| `app/domain/` | Pure business rules (BR-02 to BR-15) |
| `app/services/` | Use cases combining rules and storage |
| `app/db/` | SQLAlchemy models, repositories |
| `app/integrations/` | ML, LLM, chain and audit-log adapters |
| `app/worker/` | Outbox relay, retries, reconciliation jobs |
| `migrations/` | Alembic migrations |
| `tests/` | pytest unit, integration and e2e tests |

Main requirements: FR-01 to FR-26, BC-09, BC-10, NFR-04, NFR-07.
