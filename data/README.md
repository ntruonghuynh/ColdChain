# data/

**Status: Milestone 2 implemented** (synthetic dataset, data dictionary, provenance, import). All data here is **synthetic**.

| Path | Purpose | Tracked in Git |
|---|---|---|
| `generator/` | Seeded journey simulator `coldchain_sim` (Python package + CLI), its configuration (`config/coldchain-sim-v1.yaml`) and tests | yes |
| `dictionary/data-dictionary.md` | Every field, type, unit, timezone, missing-value meaning, label rule, method and limitation | yes |
| `dictionary/provenance.md` | Source, versions, seeds, hashes, reproduction commands | yes |
| `release/coldchain-sim-v1.0.0-seed11/` | **Canonical dataset** (seed 11, 200 journeys, about 3.5 MB), committed so no regeneration is needed on first start (decision D-05) | yes |
| `release/seed-manifests/` | Manifests (checksums only) of the reserved evaluation seeds 22, 33, 44, 55, 66 (seed 11 is the development dataset) | yes |
| `generated/` | Scratch output of local runs | no (git-ignored) |

Ground-truth labels are kept apart from observations: `observed/` vs `ground_truth/` in the files, and the `ground_truth` PostgreSQL schema in the database (DATA-09).

## Commands (run from the repository root; Docker only)

| Task | Command |
|---|---|
| Generate a dataset | `docker compose --profile tools run --rm data-tools python -m coldchain_sim generate --config data/generator/config/coldchain-sim-v1.yaml --seed 11 --out data/generated/seed11` |
| Generate several seeds | `docker compose --profile tools run --rm data-tools python -m coldchain_sim seeds --config data/generator/config/coldchain-sim-v1.yaml --seeds 22,33,44,55,66 --out-root data/generated/seeds` |
| Verify the release (checksums + regeneration) | `docker compose --profile tools run --rm data-tools python -m coldchain_sim verify data/release/coldchain-sim-v1.0.0-seed11 --regenerate` |
| Import into PostgreSQL (idempotent) | `docker compose --profile tools run --rm data-tools python -m app.dataset import data/release/coldchain-sim-v1.0.0-seed11` |
| Show imported datasets | `docker compose --profile tools run --rm data-tools python -m app.dataset status` |
| Tests (generator + backend) | `docker compose --profile test run --rm --build backend-tests` |

The stack (`db`) must be running for the import (`docker compose up -d --wait`). For now the import is a manual command. A configurable, idempotent first-run import for the final Docker demo release is approved (D-10, 2026-11-15) and will be built with the release work in Milestone 10.

Main requirements: SC-02, DATA-01 to DATA-09, NFR-03, NFR-05, NFR-06, EVAL-10, SUB-02.
