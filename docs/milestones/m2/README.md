# Milestone 2 — raw run output

Unedited output of the commands run for Milestone 2 on 2026-11-14 (macOS, Docker Desktop, Apple Silicon; project image `coldchain-backend:local`, linux/arm64). Every number in the M2 documentation and report comes from these files or from `data/release/coldchain-sim-v1.0.0-seed11/statistics.json`.

| File | Command(s) |
|---|---|
| `raw/01-generate-canonical.txt` | Generate the canonical dataset (seed 11) into `data/release/` |
| `raw/02-generate-evaluation-seeds.txt` | Generate seeds 22, 33, 44, 55 into `data/generated/eval-seeds/` (git-ignored); their manifests were copied to `data/release/seed-manifests/` |
| `raw/03-backend-and-generator-tests.txt` | `docker compose --profile test run --rm --build backend-tests` (backend + generator tests) |
| `raw/04-stack-upgrade-and-migration.txt` | `docker compose up -d --build --wait`; migrate log (0001 → 0002); `alembic current` |
| `raw/05-verify-and-import.txt` | Verify release (checksums + regeneration), import twice (idempotency), status |
| `raw/06-api-and-sql-spot-check.txt` | Shipments API through the proxy, system info, SQL check of preserved `event_at`/`received_at` |
| `raw/07-frontend-checks.txt` | `npm test`, `npm run typecheck`, `npm run build` |
| `raw/08-smoke-test.txt` | `python3 scripts/smoke_test.py --keep-running`, then `app.dataset status` after the restart |
| `raw/09-cross-architecture-regeneration.txt` | Regeneration of the canonical release on linux/amd64 (`python:3.12-slim`, emulated) |
| `raw/10-generate-seed66.txt` | 2026-11-15 review: generate and verify reserved evaluation seed 66; its manifest copied to `data/release/seed-manifests/` |
| `raw/11-seed11-unchanged.txt` | 2026-11-15 review: SHA-256 of every seed-11 release file before and after the review changes (identical), and `verify --regenerate` |
| `raw/12-backend-and-generator-tests.txt` | 2026-11-15 review: full backend + generator test run after the changes (supersedes `03`) |
| `raw/13-compose-config-check.txt` | 2026-11-15 review: Compose configuration validated with the edited `.env.example`; frontend and smoke tests not re-run (no file they depend on changed) |
| `raw/14-backend-and-generator-tests.txt` | 2026-11-15 final decisions (D-12, D-13): full test run including the API, frontend, policy and seed guards (supersedes `12`) |
| `raw/15-boundary-negative-control.txt` | 2026-11-15: the frontend ground-truth guard fails on a planted `ground_truth` reference in a throwaway tree (shows the check can fail) |

Docker progress lines (`Container ... Started`, build steps) were filtered out of the logs; nothing else was removed.
