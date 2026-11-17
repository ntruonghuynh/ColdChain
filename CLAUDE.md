# CLAUDE.md — Rules for Claude Code in this repository

Project: **Cold Chain Monitoring and Excursion Response** (IT in Logistics, Final project 03).
Academic full-stack prototype: monitoring + ML + LLM/RAG + blockchain + web dashboard, shipped with Docker Compose.

## Current status

- Milestones 0–5 are complete and preserved. **Milestone 6 (LLM/RAG) is under final acceptance review** on `feat/m6-llm-rag`; do not start M7 without explicit approval.
- M6 is advisory only. Provider is disabled by default, corpus is teaching-only, evidence is causal, citations are verified, and no LLM output may write a M5 disposition or warehouse action. Keep `backend/app/api/system.py` `FEATURES` truthful.
- Approved teaching policy (2026-11-14) lives in `backend/app/seed/data/policies/POL-CHILL-01_v1.0.json`. Policy versions are immutable; never edit that file's values — publish a new version file after owner approval.
- Canonical **development** dataset `data/release/coldchain-sim-v1.0.0-seed11/` is committed and immutable: never edit it in place. Seeds 22, 33, 44, 55, 66 are reserved for operational simulation evaluation (only their manifests are committed); never tune or develop on them (A-13). A changed generator, configuration or policy needs a new dataset version (new folder) and a regenerated manifest.
- Ground truth (D-12): only the modules on the allow-list in `backend/tests/test_ground_truth_boundary.py` may read the `ground_truth` schema or the `ground_truth/` files. M4's only added label boundary is `ml/coldchain_ml/labels.py`; feature extraction, detection, inference, operational APIs and the frontend use observed data only. Never weaken or delete those regression tests to make code pass.
- Evaluation protocol (D-13): seed 11 is for development, training, validation and internal regression checks, and its `test` partition is never used for iterative tuning. Seeds 22, 33, 44, 55, 66 are final evaluation seeds: never use them for feature, model, preprocessing or threshold choices, and open them only after the model and preprocessing are frozen. Record the model version, seed assignments and protocol with every result.
- The approved nominal 5-minute sampling interval belongs in detector configuration, not in the policy (policy v1.0 is immutable). BR-05 is **approved** (2026-11-15, requirements analysis §13.1 and §13.3): gaps break runs, no exposure inferred across missing readings, duration = last − first `event_at`.
- M4 model `coldchain-rf-v1.0.0` is frozen in `ml/registry/`; inference verifies SHA-256 checksums and feature schema. The seed-11 test partition is post-freeze and one-shot; reserved seeds 22, 33, 44, 55, 66 are M9-only. ML outputs are advisory, prediction records are append-only, and unknown/missing telemetry never means safe.
- M3 detector contract `docs/design/m3-baseline-detector-contract.md` is **approved and implemented** (BR-05, C-01 to C-10, BR-06 to BR-09, U-01 to U-08). Key rules: readings ≤ 7 min 30 s apart are continuous; durations and the gap **bracketing span** use exact `event_at` differences against exact policy thresholds (estimated missing samples are information only); stale telemetry is STALE/UNKNOWN (never safe) and a `DATA_GAP` incident opens only for a confirmed gap ≥ 30 min; no grace periods; full-journey deterministic recalculation; live uses server receipt time, replay is causal on recorded `received_at`; results are append-only; the detector never writes `incident.status` (only a quality disposition closes, M5); late data never changes a disposition (U-04: `decision_reassessment`); sensor-fault suspicion is a persisted warning, `SENSOR_FAULT_SUSPECTED` is reserved (BR-09 amended by U-01). Clients can never supply `received_at` over HTTP.
- M5 authorization and decisions: only authenticated receiver QUALITY users create dispositions; warehouse release requires confirmed on-chain RELEASE; MONITOR is a non-login Receiver-owned service account (D-08). Workflow commands are transactionally enqueued and confirmation is explicit. Never treat ML/LLM output as authorization. See `docs/design/m5-blockchain-workflow.md` and `blockchain/ROLES.md`.
- Local chain keys and demo passwords are development-only. Never commit `.env`, role private keys, mnemonic overrides or customer secrets. Hardhat state is in-memory; restart recovery is reconciliation, not silent rewriting.
- Only `backend/app/evaluation/` (offline, no DB access) joins detector outputs with ground truth, and it refuses seeds 22–66 and the seed-11 `test` partition. Operational code must never import it (tested).

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

## M6 specific boundaries

- All M6 documentation, evaluation reports and saved results are written in Vietnamese. Standard API fields and code identifiers may remain English.
- Operational explanation code reads observed/system evidence only. Preserve `event_at`/`received_at` and exclude revisions, predictions and confirmations unavailable by the evidence cutoff. Never import the ground-truth schema or label files.
- SOPs authored for the prototype must be labelled as simulated teaching procedures, not official handling guidance. Policy values come only from the immutable approved policy.
- LLM output is advisory. Only M5 authorization can create Quality dispositions or warehouse release actions. Do not expose tools, signing keys or workflow credentials to the model.
- External inference is optional, bounded and absent from startup. Automated tests use mock provider responses; live inference is reported separately and only when configured.

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
| Development backend + generator tests (M9-marked tests excluded by default) | `docker compose --profile test run --rm --build backend-tests` |
| Seed-11 deterministic generator regression only | `docker compose --profile test run --rm backend-tests pytest -q -p no:cacheprovider -c pyproject.toml /workspace/data/generator/tests/test_sim_determinism.py::test_seed11_canonical_dataset_regenerates_to_identical_content` |
| M9 final evaluation suite | Separate, owner-authorized evaluation procedure only; never include it in development regression |
| Generate a dataset (scratch) | `docker compose --profile tools run --rm data-tools python -m coldchain_sim generate --config data/generator/config/coldchain-sim-v1.yaml --seed 11 --out data/generated/seed11` |
| Verify the canonical release (checksums + regeneration) | `docker compose --profile tools run --rm data-tools python -m coldchain_sim verify data/release/coldchain-sim-v1.0.0-seed11 --regenerate` |
| Import the canonical dataset (idempotent) / show status | `docker compose --profile tools run --rm data-tools python -m app.dataset import data/release/coldchain-sim-v1.0.0-seed11` / `... python -m app.dataset status` |
| Run the baseline detector over imported shipments (causal replay, once per sensor) | `docker compose --profile tools run --rm data-tools python -m app.monitoring replay` |
| Ocean coverage demo (new demo shipment, causal, idempotent) / monitoring summary | `docker compose --profile tools run --rm data-tools python -m app.monitoring demo-ocean` / `... python -m app.monitoring summary` |
| Development evaluation of the baseline (seed 11 train+validation only) | `docker compose --profile tools run --rm data-tools python -m app.evaluation baseline data/release/coldchain-sim-v1.0.0-seed11 --out docs/evaluation/dev/m3-baseline-seed11` |
| Train M4 on seed-11 train and select on validation; then run the one-shot internal test after freeze | `PYTHONPATH=ml:backend python -m coldchain_ml train` then `PYTHONPATH=ml:backend python -m coldchain_ml internal-test` (Python 3.12; see `ml/README.md`) |
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
