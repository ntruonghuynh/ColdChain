# Cold Chain Monitoring and Excursion Response

Academic prototype for **IT in Logistics — Final project 03**. It monitors refrigerated shipments, tells real temperature excursions apart from missing or faulty sensor data, drafts a procedure-based response, and records custody and quality decisions on a local blockchain. A human quality officer always makes the release or quarantine decision.

> **Status: Milestone 0 — planning only.** The repository has requirements, architecture, the implementation plan and an empty folder structure. **Nothing runs yet.** The quick start below describes the target and will work from Milestone 1 onward.

> **Teaching boundary.** All data is simulated. Temperature limits and procedures are teaching policies, not clinical or regulatory guidance. No ML output establishes product safety.

## What the finished system will do

| Area | Function |
|---|---|
| Monitoring | Ingest readings with sensor time and received time, detect data gaps (shown as UNKNOWN, never safe), apply the policy threshold rule |
| Machine learning | Window features + classifier to detect excursions and separate gradual warming from sensor spikes; compared with the threshold baseline |
| LLM / RAG | Retrieve the approved handling procedure, explain the alert, list required evidence, cite policy version and sensor interval, abstain when evidence is insufficient |
| Blockchain | Anchor sensor-batch hashes; record custody acceptance, incident opening and quality disposition; only the quality role can authorize release |
| Dashboard | Temperature timeline, missing-data indicator, excursion queue, response draft, quality decision history, reconciliation view |

## Technology

React + TypeScript + Vite + Tailwind CSS · Python + FastAPI · PostgreSQL · scikit-learn · provider-based LLM with retrieval · Solidity + Hardhat · Docker Compose

## Repository layout

| Path | Contents | Milestone |
|---|---|---|
| `docs/` | Requirements analysis, architecture, implementation plan, assignment brief | M0 |
| `backend/` | FastAPI service: ingestion, policy engine, incidents, dispositions, release gate, outbox worker | M1, M3, M5 |
| `frontend/` | React dashboard | M1, M7 |
| `data/` | Seeded journey simulator, data dictionary, provenance | M2 |
| `ml/` | Features, training, frozen model registry | M4 |
| `blockchain/` | Solidity contract, Hardhat tests and deployment | M5 |
| `llm/` | Retrieval, prompts, provider adapters, evaluation cases | M6 |
| `scripts/` | Start/stop helpers, demo scenarios, evaluation runners, packaging | M1, M8–M10 |

## Documentation

- [Requirements analysis](docs/requirements-analysis.md)
- [Architecture](docs/architecture.md)
- [Implementation plan](docs/implementation-plan.md)
- [Rules for Claude Code](CLAUDE.md)

## Quick start (target — not available yet)

Requirements: Docker Desktop.

```bash
cp .env.example .env
docker compose up --build
# then open http://localhost:8080
```

The LLM features need an API key in `.env`. Without one, the rest of the system still works and the LLM panel says it is not configured.

## Contributing

- Work follows the milestones in `docs/implementation-plan.md`, one at a time.
- Never commit `.env` or any key.
- Every business rule needs a test.
