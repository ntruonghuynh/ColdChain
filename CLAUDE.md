# CLAUDE.md — Rules for Claude Code in this repository

Project: **Cold Chain Monitoring and Excursion Response** (IT in Logistics, Final project 03).
Academic full-stack prototype: monitoring + ML + LLM/RAG + blockchain + web dashboard, shipped with Docker Compose.

## Current status

- Milestone 0 (requirements, architecture, plan, skeleton) is the latest completed milestone.
- **Nothing is implemented yet.** There are no build, run or test commands until Milestone 1 adds them. Add them to the "Commands" section below when they exist.

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

None yet. Milestone 1 will add start, stop, reset and test commands here.

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
