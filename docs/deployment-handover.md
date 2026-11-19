# ColdChain fresh-clone deployment handover

This guide starts a new local demo with its own Compose project, Docker image tags, network, PostgreSQL volume, and chain-deployment volume. Do not copy `.env`, database files, blockchain state, or evaluation evidence from another installation.

## Prerequisites

- Docker Desktop with Docker Compose v2 on Windows 10/11 or macOS, or Docker Engine and Compose v2 on Linux.
- 4 GB or more available memory for Docker; additional disk space is needed for images and the dataset.
- Git and internet access for the first clone and image/package downloads.
- Windows: built-in Windows PowerShell. macOS/Linux: Python 3 and a POSIX shell for the setup helper.

The Windows scripts have not been exercised on a Windows host in this handover. Follow the PowerShell instructions below and treat them as documented, not Windows-verified.

## Clone and configure

```text
git clone https://github.com/ntruonghuynh/ColdChain.git
cd ColdChain
```

Do not reuse a working directory that contains another installation's `.env`. The start scripts copy `.env.example` on first run and call a helper that generates local credentials plus a unique Compose project and unique image tags. The helper does not print secrets. `.env` is ignored by Git.

### Windows PowerShell

```powershell
Copy-Item .env.example .env
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup_local_env.ps1
docker compose config --quiet
```

Then run `start.bat`, or start manually with `docker compose up -d --build --wait --wait-timeout 600`. Before a manual start, make sure `FRONTEND_PORT` and `CHAIN_PORT` in `.env` are free. `start.bat` checks both ports before starting.

### macOS / Linux shell

```bash
cp .env.example .env
python3 scripts/setup_local_env.py
docker compose config --quiet
```

On macOS, run `./start.command` (or double-click it). On Linux, start with `docker compose up -d --build --wait --wait-timeout 600` after checking that both configured host ports are free. The web UI and local Hardhat RPC bind to `127.0.0.1` by default.

If a port is occupied, change `FRONTEND_PORT` or `CHAIN_PORT` in `.env`. Do not change `COMPOSE_PROJECT_NAME` or image tags to a name used by another project. The generated names are recorded in `.env`; rerunning setup preserves them.

The Compose file requires `COMPOSE_PROJECT_NAME` and project-scoped image tags from `.env`. It has no fixed `container_name`. New deployments receive their own network and named volumes. Backend and database ports are not published to the host.

## First startup and migrations

```bash
docker compose config --quiet
docker compose up -d --build --wait --wait-timeout 600
docker compose ps
```

Compose builds the backend runtime image whose command starts Uvicorn, and the frontend image whose Nginx config serves the React SPA and proxies `/api` to `backend:8000`. Startup waits for PostgreSQL, the one-shot migration/reference-data service, the local Hardhat node and contract deployment, the backend, then the frontend.

Check the same-origin readiness endpoint (replace `3000` with `FRONTEND_PORT` if changed):

```text
http://127.0.0.1:3000/api/health
http://127.0.0.1:3000/api/health/ledger
http://127.0.0.1:3000/api/llm/readiness
http://127.0.0.1:3000/api/docs
```

The database readiness response reports the applied migration revision and expected head; both should be `0006_m6_llm_explanations`. LLM retrieval should be ready and `provider_status` should be `not_configured`. The sample `.env` disables the provider and has no API key. Do not add a paid provider key for the browser demo.

## Initialize the canonical demo data

Migrations load the policy, organizations, and demo identities but do not import journeys automatically. Seed 11 is the tracked canonical development dataset with 200 simulated journeys. Reserved evaluation seeds 22, 33, 44, 55, and 66 are not used here.

Run these from the repository root after startup:

```bash
docker compose --profile tools run --rm data-tools python -m app.dataset verify data/release/coldchain-sim-v1.0.0-seed11
docker compose --profile tools run --rm data-tools python -m app.dataset import data/release/coldchain-sim-v1.0.0-seed11
docker compose --profile tools run --rm data-tools python -m app.dataset status
docker compose --profile tools run --rm data-tools python -m app.monitoring replay
docker compose --profile tools run --rm data-tools python -m app.monitoring demo-ocean
docker compose --profile tools run --rm data-tools python -m app.monitoring summary
```

The import is idempotent and reports 200 journeys. Replay uses the recorded `event_at` and `received_at` values to construct causal incident history; it does not collapse event time into receipt time. The ocean demo creates an additional simulated shipment to show outage, UNKNOWN, delayed backfill, and revised evidence. Its stable `DEMO-OCEAN-...` identifier makes reruns idempotent. These commands write only to the current `.env` project's new database volume.

## Login and read-only smoke checks

The local seed configures `shipper.demo`, `carrier.demo`, `quality.demo`, `warehouse.demo`, and `platform.admin`. Their passwords are generated in `.env` as `SHIPPER_DEMO_PASSWORD`, `CARRIER_DEMO_PASSWORD`, `QUALITY_DEMO_PASSWORD`, `WAREHOUSE_DEMO_PASSWORD`, and `ADMIN_DEMO_PASSWORD`. Enter them into the browser login form; do not paste them into shared docs, terminal commands, or screenshots. `platform.admin` is the seeded ADMIN identity. These are local teaching accounts, not production identities.

After data initialization, run:

```bash
python3 scripts/deployment_smoke.py
```

The script uses the configured `QUALITY_DEMO_PASSWORD` in memory. It checks SPA routes, readiness and migration 0006, active teaching policy, the 200 imported journeys, HIGH/LOW and DATA_GAP incidents, incident revision/evidence GETs, chain readiness, M4 model readiness, M6 offline retrieval readiness, authenticated ledger/history GETs, and role-based 401/403 responses. It makes one POST only: local demo login. It does not call ingestion, disposition, release, prediction scoring, explanation creation, or an external provider. An empty stored-explanation history or empty chain history is a valid fresh-demo state.

## Browser demonstration scope

- **M1–M3:** overview, shipments, policy limits, temperature timeline, excursion queue, incident evidence/revisions, confirmed data gaps, and the ocean outage/backfill scenario. Missing data stays UNKNOWN.
- **M4:** model readiness is read-only in the frontend. No prediction is scored automatically. The scoring API is POST-only and prediction history has no GET endpoint.
- **M5:** login, `/auth/me`, role-aware Quality Review, explicit disposition confirmation, separate WAREHOUSE release gate, ledger and signed-audit reads. Do not submit a disposition or release during read-only acceptance. A fresh import has no ledger events; M3 replay emits `INCIDENT_OPENED` business events into the outbox. Without a confirmed M5 shipment registration, those events remain pending and have no chain transaction. The disposable smoke run confirmed this state.
- **M6:** readiness, stored explanation history/detail and SOP citations are read-only. A fresh database has no stored explanations; the empty state is expected. Opening an incident does not invoke inference. No provider call is part of setup or smoke testing.

Use the browser for the available pages and read-only history. The causal replay, ocean-demo setup, and seed import are internal CLI operations. A populated M5 chain-history or M6 stored-citation demonstration requires prepared data in a separate disposable project; do not create those records in a protected environment.

## Stop, restart, and remove only this demo

To stop and later start this specific installation without deleting PostgreSQL data:

```bash
docker compose stop
docker compose start
```

To remove only its containers and network while retaining named volumes:

```bash
docker compose down
```

Hardhat's chain state is in memory and is lost when its container is removed. PostgreSQL remains in its named volume.

To permanently remove this **disposable** installation and its named volumes, first verify the generated project name and the resources Compose resolves:

```bash
grep '^COMPOSE_PROJECT_NAME=' .env       # PowerShell: Select-String '^COMPOSE_PROJECT_NAME=' .env
docker compose config --format json
docker compose ps -a
```

Only if the project name is the intended disposable demo, run:

```bash
docker compose down --volumes
```

This deletes that project's PostgreSQL and chain-deployment volumes. Never run Docker-wide prune commands to clean up ColdChain; other projects may contain protected data.

## Troubleshooting

- **`docker compose config` asks for a project name:** copy `.env.example` and run the platform's setup helper.
- **Port bind error:** choose free `FRONTEND_PORT` and `CHAIN_PORT` values in `.env`; rerun `docker compose config --quiet` before starting.
- **Migration is behind 0006:** inspect `docker compose logs migrate db`; do not bypass the migration service or manually edit `alembic_version`.
- **Backend readiness fails:** inspect `docker compose ps -a` and `docker compose logs backend migrate db chain chain-deploy`.
- **Frontend opens but `/api` is unavailable:** inspect `docker compose logs frontend backend`; Nginx uses the Compose service name `backend:8000` on the project network.
- **Login fails:** confirm `.env` contains generated nonempty secrets and restart/re-run the idempotent migration service. Existing user passwords are not rotated if a user already has a password hash.
- **M6 provider shows not configured:** expected for this no-cost demo. Stored explanation GETs still work when stored records exist.
- **Disk space is low:** inspect project resources first and remove only resources you can identify as disposable. Do not use global Docker Clean/Purge while other projects are running.

## Verification record

### Local verification on 2026-11-19

- A clean local archive of committed `main` was created; the tracked startup scripts, `.env.example`, migration `0006`, and seed-11 fixture were present. The handover changes were overlaid into that clean temp checkout for testing. Remote GitHub clone was unavailable because this environment could not resolve `github.com`.
- macOS startup script completed in that checkout with project `coldchain-demo-7c6f5608`, unique image tags, new volumes/network, frontend port 3287 and chain port 18551. Migration and reference-data services completed; backend, worker, database, chain, and frontend became healthy.
- Canonical seed-11 verified/imported: 200 journeys, 114,969 readings, with both `event_at` and `received_at` stored as `timestamp with time zone`; 115,643 readings had a later receipt timestamp. Replay processed 200 shipments and produced 146 incidents. The ocean demo showed STALE → UNKNOWN → CURRENT after delayed backfill.
- Backend/generator test container: 331 passed, 11 deselected, 0 failed. Frontend: 30 passed; typecheck and production build passed. React tests emit existing `act(...)` warnings; backend tests emit dependency deprecation warnings.
- Deployment HTTP/auth smoke: 23 passed, 0 failed, 1 skipped (stored explanation detail, because the fresh demo has no stored explanations). Login and `/auth/me` returned 200; logged-out protected GET returned 401; QUALITY received 403 from ADMIN-only audit verification. Ledger/audit GETs returned 200. M4 model and offline M6 retrieval were ready; provider status was `not_configured`.
- M3 replay left 147 `INCIDENT_OPENED` outbox events pending and 0 chain transactions because no M5 shipment-registration event was submitted. No disposition, warehouse release, prediction scoring, explanation generation, or paid provider call was made. Contract deployment used only the newly created local Hardhat chain.
- macOS local deployment was tested. Windows and Linux execution were not tested. The remaining 35-case M6 evaluation was not run.
