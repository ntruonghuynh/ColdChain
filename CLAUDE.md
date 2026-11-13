# CLAUDE.md — Rules for Claude Code in this repository

Project: **Cold Chain Monitoring and Excursion Response** (IT in Logistics, Final project 03).
Academic full-stack prototype: monitoring + ML + LLM/RAG + blockchain + web dashboard, shipped with Docker Compose.

## Current status

- Milestone 0 accepted. **Milestone 1** (Docker, PostgreSQL schema + migrations, FastAPI skeleton, React shell) is implemented and awaiting the owner's acceptance.
- Not implemented: ingestion, gap/excursion detection, ML, LLM, blockchain, authentication. Their UI pages must keep saying "Not implemented yet" until the owning milestone delivers them, and `backend/app/api/system.py` `FEATURES` must stay truthful.
- Approved teaching policy (2026-11-14) lives in `backend/app/seed/data/policies/POL-CHILL-01_v1.0.json`. Policy versions are immutable; never edit that file's values — publish a new version file after owner approval.

## Read before you change anything

1. `docs/requirements-analysis.md` — requirement IDs (FR, NFR, DATA, ML, LLM, BC, EVAL, DEMO, SUB), proposed business rules (BR-xx), interpretations (A-xx), open decisions (D-xx).
2. `docs/architecture.md` — module boundaries, data model, flows, state machine, contract roles.
3. `docs/implementation-plan.md` — milestones, acceptance criteria, required tests.
4. The brief itself: `docs/requirements/03_cold_chain_monitoring_and_excursion_response.pdf`.

## Mandatory rules

1. **Read the requirements analysis and architecture before implementing anything.** Name the requirement IDs your change serves.
2. **Work on one milestone at a time.** Do not start the next milestone without explicit approval from the project owner. Do not build features that belong to a later milestone.
3. **Do not silently change business rules.** BR-xx rules, policy values (limits, durations, gap thresholds), role permissions and state transitions change only after the owner approves; record the change and its reason in `docs/requirements-analysis.md` and update the tests in the same change. If a rule looks wrong, stop and ask.
4. **Never fabricate data, experimental metrics or test results.** Every number in docs or reports must come from a run whose raw output is saved in the repository. If something was not run, write "not run". Never invent example values for the UI; show real data or a clearly labelled simulated value.
5. **Keep ML predictions separate from human quality authorization.** ML scores and LLM drafts are advisory. No code path may let them record a disposition, close an incident or release goods. Only the QUALITY role records dispositions (BR-10, BR-15).
6. **Treat missing sensor readings as unknown, never as safe.** No forward-filling across gaps, no default "normal" value, no counting UNKNOWN time as in-range time (BR-03, BR-04).
7. **Preserve both sensor event time and received time.** Keep `event_at` and `received_at` unchanged from ingestion to storage to evaluation. Store timestamps as timezone-aware UTC.
8. **Use reproducible data generation and evaluation.** Every generator, training and evaluation entry point takes a seed and a config file and writes both next to its output. Split by journey. Tune on validation data only; use the test set once, after freezing.
9. **Never commit secrets, API keys or credentials.** Use `.env` (git-ignored). `.env.example` contains placeholders only. Hardhat dev keys are used only on the local chain and are never written into tracked files.
10. **Design for Docker-based distribution.** Everything must run via Docker Compose on Docker Desktop (macOS and Windows). No host-only dependencies, no absolute local paths, LF line endings for shell scripts.
11. **Add tests for every implemented business rule.** Put the rule ID (for example `BR-07`) in the test name or docstring. Test boundaries (exact limit values, exact durations).
12. **Never run destructive Git commands.** Forbidden: `git reset --hard`, `git clean -f`, `git push --force`, `git checkout -- <path>` or `git restore` on uncommitted work, `git branch -D`, `git rebase` on shared branches, rewriting history. Do not delete files you did not create in the current task without asking.
13. **Do not commit, push, merge or create pull requests without explicit approval** from the project owner for that specific action. Staging for review is fine only when asked.
14. **Report at the end of every task:** all modified/created/deleted files, every command executed, test results (with the real output summary, including failures), and unresolved issues or open decisions.

## Engineering conventions

- **Boundaries:** business rules live in `backend/app/domain/` as pure functions; API routes contain no business logic; the frontend contains no business logic.
- **Defense in depth:** role and state-transition checks exist in the backend **and** in the smart contract.
- **Append-only records:** readings, business events, dispositions and audit entries are never updated in place; corrections are new rows that reference the old one.
- **Idempotency:** every write that can be retried carries a unique business reference (BR-13).
- **Versions everywhere:** store policy, procedure, feature-spec, model, prompt and contract versions with each result.
- **Ground truth is separate:** simulator labels live in their own schema/files and must never be read by detection code.
- **Honest unavailable states:** if the LLM provider is not configured or the chain is unreachable, return an explicit status; never return a placeholder that looks real.
- **Test doubles** (for example a recorded LLM response) are allowed only in tests and must be named as such; they must never be wired into the running application.
- **Python:** 3.12, type hints, Pydantic for all API and LLM schemas, pytest. **TypeScript:** strict mode. **Solidity:** OpenZeppelin `AccessControl`, Hardhat tests for every function × role.
- **Units and names:** `_c` for °C, `_pct` for percent, `_min` for minutes; timestamps end in `_at`.

## Commands

Run from the repository root unless noted. `.env` must exist (`cp .env.example .env`).

| Task | Command |
|---|---|
| Start stack and wait until healthy | `docker compose up -d --build --wait` |
| Stop (keeps data) | `docker compose down` — never add `-v` without explicit owner approval (deletes all data) |
| Backend tests (in Docker, uses `*_test` databases) | `docker compose --profile test run --rm --build backend-tests` |
| Frontend tests / type-check / build | `cd frontend && npm test && npm run typecheck && npm run build` |
| Full-stack smoke test (startup, proxy, outage, shutdown, persistence) | `python3 scripts/smoke_test.py` |
| Migration status | `docker compose run --rm migrate alembic current` |
| New migration | edit `backend/app/db/models/`, then `docker compose run --rm -v "$PWD/backend/migrations:/app/migrations" --user root migrate alembic revision --autogenerate -m "..."`; review the file by hand; tests fail if models and migrations differ |
| Recompile pinned Python deps | `cd backend && uv pip compile pyproject.toml --python-version 3.12 --python-platform linux -o requirements.txt` (and `--extra dev -o requirements-dev.txt`) |

App: http://localhost:3000 · API docs: http://localhost:3000/api/docs · Only port 3000 is published; backend and database are internal to the Docker network.

User-facing start/stop scripts: `start.command` / `stop.command` (macOS, LF, executable) and `start.bat` / `stop.bat` (Windows, CRLF). They must never delete data.

## Milestone report template

```
## Milestone N report
Requirements addressed: <IDs>
Files created / modified / deleted: <list>
Commands executed: <list>
Test results: <command + pass/fail counts + failures verbatim>
Acceptance criteria: <each criterion: met / not met + evidence>
Unresolved issues and open decisions: <list>
Suggested commit message: <text>   (do not commit without approval)
```
