# Cold Chain Monitoring and Excursion Response

Academic prototype for **IT in Logistics — Final project 03**. It monitors refrigerated shipments, tells real temperature excursions apart from missing or faulty sensor data, drafts a procedure-based response, and records custody and quality decisions on a local blockchain. A human Quality Officer always makes the release or quarantine decision.

> **Status: Milestone 5 implementation, pending project-owner review.** The stack preserves M1–M4 and adds authenticated custody/quality workflow APIs, a local Hardhat registry, transactional outbox, reconciliation and signed audit verification. All journey data is **simulated**. ML is advisory; only a receiving Quality Officer may record a disposition, and warehouse release requires a confirmed RELEASE. See the [M5 report](docs/milestones/m5/README.md).

> **Teaching boundary.** All data is simulated. Temperature limits and procedures are teaching policies, not clinical or regulatory standards. No ML output establishes product safety.

---

## Quick start (for everyone)

**You need:** [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed (macOS or Windows), about 4 GB of free memory for Docker, and an internet connection the first time.

| | macOS | Windows |
|---|---|---|
| Start | Double-click **`start.command`** | Double-click **`start.bat`** |
| Stop | Double-click **`stop.command`** | Double-click **`stop.bat`** |

The start script checks that Docker is running (and tries to start it), creates the settings file `.env` if it is missing, starts everything, waits until it is healthy, and opens the app in your browser.

- Open the app: **http://localhost:3000**
- The first start downloads and builds everything and can take several minutes. Later starts take seconds.
- Stopping **keeps your data**. Nothing in these scripts deletes data.

> **macOS:** the first time, macOS may block a downloaded script. Right-click `start.command` → **Open** → **Open**. If it says "permission denied", run `chmod +x start.command stop.command` once in Terminal from this folder.

## What runs today (Milestones 1–4)

| Area | Status |
|---|---|
| PostgreSQL database with the schema (20 tables from Milestone 1; Milestone 2 adds `dataset_release` and a separate `ground_truth` schema; Milestone 3 adds 7 monitoring tables; M4 adds append-only ML predictions) and migrations | Available |
| Teaching policy, organizations and demo users loaded as configuration data | Available |
| Backend API: health checks, system info, policies, organizations, shipments; ingestion (`POST /api/ingest/batches`), telemetry, sensor status, missing and delayed data, detections, warnings, incidents, monitoring summary | Available |
| API documentation (OpenAPI / Swagger) | Available at http://localhost:3000/api/docs |
| Dashboard shell: navigation, header, API connectivity indicator, Overview, Shipments, System Settings | Available |
| Temperature monitoring (timeline, missing-data intervals, monitoring state, causal "view as of"), excursion queue, incident detail | Available (Milestone 3) |
| Quality review, audit history | Not implemented yet (pages show this) |
| Synthetic dataset (200 journeys, seed 11) with data dictionary, provenance and checksums | Available in `data/release/` (Milestone 2) |
| Idempotent import of the dataset into PostgreSQL (simulated shipments, readings, context; labels in a separate `ground_truth` schema) | Available as a manual command (Milestone 2) |
| Data ingestion API, gap detection, threshold baseline, incidents | Available (Milestone 3) |
| Frozen ML inference API (`POST /api/predictions`, model readiness at `GET /api/predictions/model`) | Available (Milestone 4; advisory only) |
| Authenticated custody, quality disposition and release gate APIs; local blockchain and audit log | Implemented (Milestone 5; review pending) |
| LLM drafts and full workflow dashboard | Milestones 6 and 7 |

After a fresh start there are no shipments. To load the 200 **simulated** shipments of the canonical dataset (takes about 15 seconds; running it again changes nothing):

```bash
docker compose --profile tools run --rm data-tools python -m app.dataset import data/release/coldchain-sim-v1.0.0-seed11
```

The Shipments page then lists them, labelled `SIMULATED`. To run the threshold baseline over them, replaying every journey along its recorded receipt times (about 15 seconds; running it again changes nothing):

```bash
docker compose --profile tools run --rm data-tools python -m app.monitoring replay
```

The Excursion Queue and Temperature Monitoring pages then show the results. The ocean coverage demonstration (connectivity loss, STALE/UNKNOWN, delayed backfill, excursion found afterwards, incident pending review) is `python -m app.monitoring demo-ocean` with the same prefix. Details: [data/README.md](data/README.md), [data dictionary](data/dictionary/data-dictionary.md), [M3 report](docs/milestones/m3/README.md).

### Approved teaching policy (configuration data)

Loaded from [`backend/app/seed/data/policies/POL-CHILL-01_v1.0.json`](backend/app/seed/data/policies/POL-CHILL-01_v1.0.json) into the `policy` table; the dashboard reads it from the API.

| Rule | Value |
|---|---|
| Acceptable range | 2 °C – 8 °C |
| High excursion | above 8 °C for at least 30 minutes |
| Low excursion | below 2 °C for at least 15 minutes |
| Missing data | gap longer than 15 minutes → UNKNOWN (never treated as safe) |
| Quality review | gap of at least 30 minutes |
| Release authority | Quality Officer (QUALITY role) only |

Detection logic that uses these values arrives in Milestone 3. A policy version is immutable: changing a value means publishing a new version file (the loader refuses silent edits).

---

## Access URLs

| What | URL |
|---|---|
| Dashboard | http://localhost:3000 |
| API (through the dashboard's web server) | http://localhost:3000/api |
| Health check | http://localhost:3000/api/health |
| API documentation (Swagger UI) | http://localhost:3000/api/docs |
| API documentation (ReDoc) | http://localhost:3000/api/redoc |

### Local M5 demonstration accounts

On first start, `start.command`/`start.bat` generates unique local secrets in
the ignored `.env` and never prints them. The seed loader creates these users:
`shipper.demo`, `carrier.demo`, `quality.demo`, `warehouse.demo`, and
`platform.admin`. Read each matching `*_DEMO_PASSWORD` value from your local
`.env` for `/api/auth/login`; do not share those values. `monitor.service` is a
non-login service identity. The setup procedure is also available as
`python3 scripts/setup_local_env.py`.

Only port 3000 is published, and only on this computer (`127.0.0.1`). The backend and database are reachable only inside the Docker network; the browser talks to the backend through the reverse proxy at `/api`.

## Architecture of the running stack

```
Browser ─► frontend (:3000) ─/api─► backend ─► PostgreSQL
                                      │
                                      ├─ worker ─► chain-deploy ─► Hardhat node
                                      └─ migrate (Alembic + reference data)
```

| Service | Purpose | Health check |
|---|---|---|
| `db` | PostgreSQL 16, data in the named volume `coldchain_pgdata` | `pg_isready` |
| `migrate` | One-shot job: `alembic upgrade head`, then load reference data; exits 0 on success | exit code |
| `chain` | Local in-memory Hardhat JSON-RPC node; no value-bearing network | JSON-RPC `eth_chainId` |
| `chain-deploy` | One-shot idempotent contract deployment and role metadata volume | exit code |
| `backend` | FastAPI app; starts after migration and chain deployment | `GET /api/health` (database + migration revision) |
| `worker` | Transactional outbox relay; retries and confirms blockchain writes | process/restart monitoring |
| `frontend` | React app through nginx reverse proxy | `/healthz` |
| `frontend` | nginx serving the built React app and proxying `/api` to `backend` | `GET /healthz` |

Startup order is enforced with `depends_on` conditions: `db` healthy → `migrate` completed successfully → `backend` healthy → `frontend`.

Full design: [docs/architecture.md](docs/architecture.md).

---

## Developer guide

### Prerequisites

- Docker Desktop with Docker Compose v2 (tested with Docker 29.8 / Compose 5.5 on macOS, Apple Silicon)
- Optional, for working outside Docker: Python 3.12, Node.js 20.19+ (tested with 24), npm

### Environment configuration

```bash
cp .env.example .env      # the start scripts do this automatically if .env is missing
```

| Variable | Default | Meaning |
|---|---|---|
| `COMPOSE_PROJECT_NAME` | `coldchain` | Prefix for containers and the data volume |
| `POSTGRES_DB` / `POSTGRES_USER` | `coldchain` | Database name and user |
| `POSTGRES_PASSWORD` | Generated locally by the setup helper | Database password (required; existing nonempty value is preserved) |
| `FRONTEND_PORT` | `3000` | Port of the dashboard on this computer |
| `FRONTEND_BIND_ADDRESS` | `127.0.0.1` | `0.0.0.0` makes the app reachable from other devices on your network |
| `APP_ENV` | `local` | Shown in System Settings |

The macOS and Windows start scripts generate missing `.env` secrets without displaying them; the Python and PowerShell helpers preserve existing nonempty values and replace the legacy weak JWT placeholder. `.env` is git-ignored; never commit it.

### Docker commands

```bash
docker compose up -d --build --wait     # build, start, and wait until all services are healthy
docker compose ps                       # status
docker compose logs -f backend          # follow backend logs
docker compose down                     # stop; PostgreSQL volume is kept, but in-memory Hardhat history is lost
docker compose down -v                  # stop AND DELETE ALL DATA (irreversible)
```

### Database migrations

Migrations live in [`backend/migrations/versions/`](backend/migrations/versions/) and run automatically on every start through the `migrate` service (`alembic upgrade head`, then the idempotent reference-data loader `python -m app.seed`).

```bash
docker compose run --rm migrate alembic current          # current revision
docker compose run --rm migrate alembic history          # list revisions
docker compose exec db psql -U coldchain coldchain       # SQL shell (\dt lists tables)
```

Creating a new migration (developers): change the models in `backend/app/db/models/`, then generate against a running database and **review the file by hand** before committing:

```bash
docker compose run --rm -v "$PWD/backend/migrations:/app/migrations" --user root \
  migrate alembic revision --autogenerate -m "describe change"
```

The test suite fails if models and migrations differ.

### Running tests

```bash
# Backend (190 tests) + dataset generator (76 tests) inside Docker,
# against separate *_test databases (main data untouched)
docker compose --profile test run --rm --build backend-tests

# Frontend unit/component tests (22 tests), type-check and production build
cd frontend && npm ci && npm test && npm run typecheck && npm run build

# End-to-end smoke test of the whole stack: startup, proxy, outage handling,
# shutdown and data persistence across restart (uses only the Python standard library)
python3 scripts/smoke_test.py            # add --keep-running to leave the stack up
```

### Synthetic dataset (Milestone 2)

```bash
# regenerate the canonical dataset into the git-ignored scratch folder
docker compose --profile tools run --rm data-tools python -m coldchain_sim generate \
  --config data/generator/config/coldchain-sim-v1.yaml --seed 11 --out data/generated/seed11
# verify the committed release (checksums + byte-for-byte content regeneration)
docker compose --profile tools run --rm data-tools python -m coldchain_sim verify \
  data/release/coldchain-sim-v1.0.0-seed11 --regenerate
# import (idempotent) and show what is imported
docker compose --profile tools run --rm data-tools python -m app.dataset import data/release/coldchain-sim-v1.0.0-seed11
docker compose --profile tools run --rm data-tools python -m app.dataset status
```

### Monitoring and baseline detection (Milestone 3)

```bash
# causal replay of the imported shipments through the baseline detector (once per sensor)
docker compose --profile tools run --rm data-tools python -m app.monitoring replay
# ocean coverage demonstration on a new demo shipment (causal; idempotent)
docker compose --profile tools run --rm data-tools python -m app.monitoring demo-ocean
docker compose --profile tools run --rm data-tools python -m app.monitoring summary
# development evaluation of the baseline (seed 11 train+validation only; writes files, no database)
docker compose --profile tools run --rm data-tools python -m app.evaluation baseline \
  data/release/coldchain-sim-v1.0.0-seed11 --out docs/evaluation/dev/m3-baseline-seed11
```

Live ingestion: `POST /api/ingest/batches` (see http://localhost:3000/api/docs). The assigned carrier must log in; the server sets receipt time, and a client can never send it. M5 workflow commands require bearer auth; API details: [OpenAPI](http://localhost:3000/api/docs), [M5 role/workflow design](docs/design/m5-blockchain-workflow.md), [M3 monitoring API](docs/api/monitoring-api.md).

### Working outside Docker (optional)

Backend (needs a reachable PostgreSQL; set `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_PASSWORD`):

```bash
cd backend
uv venv .venv --python 3.12 && uv pip install -r requirements-dev.txt   # or python -m venv + pip
.venv/bin/alembic upgrade head && .venv/bin/python -m app.seed
.venv/bin/uvicorn app.main:app --reload
```

Frontend dev server with hot reload (proxies `/api` to `http://localhost:8000`, override with `DEV_API_PROXY_TARGET`):

```bash
cd frontend && npm ci && npm run dev     # http://localhost:5173
```

Dependency versions are pinned in `backend/requirements*.txt` (compiled from `backend/pyproject.toml`) and `frontend/package-lock.json`.

---

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| "Docker Desktop is not installed / not running" | Install or open Docker Desktop and wait for "Engine running", then start again. |
| "Port 3000 is already used by another program" | Close the other program, or set `FRONTEND_PORT=3001` (any free port) in `.env` and start again. Then use that port in the URL. |
| Header shows **API unreachable** | The backend container is down. Run the start script again, or `docker compose ps` and `docker compose logs backend`. |
| Header shows **API degraded** | The backend runs but the database is not ready or not migrated. Check `docker compose logs migrate db`. |
| `migrate` fails with `password authentication failed` | You changed `POSTGRES_PASSWORD` after the first start; the existing data volume keeps the old password. Put the old password back in `.env`. Do not remove the database volume when preserving data. |
| `migrate` fails with `SEED FAILED ... immutable` | A policy file was edited for an existing version. Restore the file and publish a new `policy_version` instead. |
| First start is very slow or fails while downloading | Check the internet connection and run the start script again; downloads resume. |
| Build fails with "no space left on device" | Free Docker disk space in Docker Desktop → Troubleshoot → Clean / Purge data (this deletes unused images). |
| Windows: the script window closes before you can read it | Open a Command Prompt in this folder (type `cmd` in the File Explorer address bar) and run `start.bat` there; the messages stay visible. Administrator rights are not needed. |

## Known limitations

- Local demo authentication is not an external identity provider. Anyone with host access to `.env` can read demo passwords. The Hardhat mnemonic is public test material and must not be used on a public chain.
- Hardhat state is in memory. Recreating its container loses chain history; reconciliation detects the gap, but does not rewrite or restore historical evidence. PostgreSQL persistence is not a complete ledger backup. Reliable chain-state restoration is deferred to M10 release work.
- This is a simulated teaching prototype. A RELEASE disposition is not a regulatory or clinical guarantee of product safety.
- No user-facing API creates shipments or assigns sensors; the M5 registration command anchors an existing imported or simulated shipment. Live ingestion is accepted only inside a documented monitoring window.
- With 15-minute uploads the monitoring state briefly shows UNKNOWN before almost every upload (it truly has no data then); see the M3 report.
- The dataset is synthetic. Its physics, sensor faults and labels are simplified; see the limitations in the [data dictionary](data/dictionary/data-dictionary.md#7-known-limitations-of-the-synthetic-data).
- Importing the dataset is a manual command for now. A configurable first-run import is approved for the final release (D-10, Milestone 10). Imported shipments stay in status `CREATED` until the M5 custody workflow advances them.
- The nominal 5-minute sampling interval and the 7 min 30 s continuity limit live in the detector configuration `DET-BASELINE v1.0.0`, not in the immutable policy v1.0.
- Windows scripts (`start.bat`, `stop.bat`) were written for Windows 10/11 but have not been executed on Windows yet.
- Fully offline installation is not supported yet: the first start downloads Docker images and packages.

## Repository layout

| Path | Contents |
|---|---|
| `docs/` | Requirements analysis, architecture, implementation plan, assignment brief |
| `backend/` | FastAPI app (`app/`), Alembic migrations, tests, Dockerfile |
| `frontend/` | React + TypeScript + Vite + Tailwind app, nginx config, tests, Dockerfile |
| `scripts/` | `smoke_test.py`; later: demo scenarios, evaluation runners, packaging |
| `data/` | Synthetic data generator, configuration, data dictionary, provenance, canonical dataset release |
| `ml/`, `llm/`, `blockchain/` | Frozen advisory model, M6 LLM placeholder, and M5 Hardhat registry |
| `docker-compose.yml` | The local stack |
| `start.*` / `stop.*` | One-click start/stop for macOS (`.command`) and Windows (`.bat`) |

## Documentation

- [Requirements analysis](docs/requirements-analysis.md)
- [Architecture](docs/architecture.md)
- [Implementation plan](docs/implementation-plan.md)
- [M5 report](docs/milestones/m5/README.md) and [workflow design](docs/design/m5-blockchain-workflow.md)
- [M3 detector contract](docs/design/m3-baseline-detector-contract.md), [monitoring API](docs/api/monitoring-api.md), [M3 report](docs/milestones/m3/README.md)
- [Data dictionary](data/dictionary/data-dictionary.md) and [provenance](data/dictionary/provenance.md)
- [Rules for Claude Code](CLAUDE.md)

## Packaging for students

The project is designed to be shipped as a ZIP of this folder (without `.env`, `node_modules`, `.venv` or other git-ignored files). Students unzip it and double-click the start script. A packaging script and student guide are planned for Milestone 10.
