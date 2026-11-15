# backend/

FastAPI service. **Milestone 1:** application skeleton, database schema and migrations, reference data, health checks and read-only endpoints. **Milestone 2:** migration `0002` (dataset provenance, `ground_truth` schema) and the synthetic dataset importer `app/dataset/` (`python -m app.dataset verify|import|status`; see `data/README.md`). **Milestone 3:** migration `0003`; pure rules in `app/domain/` (validation, detector, reconciliation, causal replay); services in `app/services/` (ingestion, detection persistence, read models, ocean demo); monitoring API (`app/api/ingest.py`, `app/api/monitoring.py`); operator commands `python -m app.monitoring replay|demo-ocean|summary`; isolated offline evaluation `python -m app.evaluation baseline`. Dispositions, release gate and chain integration arrive in Milestones 5 and 6.

| Path | Purpose |
|---|---|
| `app/main.py` | Application factory; all routes under `/api`; request-ID middleware; OpenAPI at `/api/docs` |
| `app/core/config.py` | Centralized settings from environment variables (pydantic-settings) |
| `app/core/errors.py` | Error envelope `{"error": {code, message, details, request_id}}` and exception handlers |
| `app/api/` | Routes: `health` (live/ready), `system` (info + truthful feature status), `reference` (policies, organizations), `shipments` (read-only) |
| `app/db/` | SQLAlchemy base and naming conventions, `UTCDateTime` type (rejects naive timestamps), session management, models |
| `app/db/models/` | 20 tables: reference, shipment, telemetry, workflow, ledger (see `docs/architecture.md` §5) |
| `app/seed/` | Idempotent reference-data loader (`python -m app.seed`) and its JSON data, including the approved teaching policy |
| `migrations/` | Alembic environment and revisions (`0001_initial_schema.py`) |
| `tests/` | pytest suite (45 tests): config, types, health, errors, API, migrations, seed, database constraints |
| `requirements.txt`, `requirements-dev.txt` | Pinned dependencies compiled from `pyproject.toml` with `uv pip compile` |

Planned layers (later milestones): `app/domain/` (pure business rules), `app/services/`, `app/integrations/`, `app/worker/`.

Run the tests: `docker compose --profile test run --rm --build backend-tests` (from the repository root).
