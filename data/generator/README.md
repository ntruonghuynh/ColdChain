# coldchain_sim — seeded synthetic journey simulator

Generates **synthetic** cold-chain journeys for the teaching prototype: physical product temperature, logger observations, missing and delayed readings, ground-truth intervals and policy-derived labels. Field definitions and label rules are in [`../dictionary/data-dictionary.md`](../dictionary/data-dictionary.md).

## Modules

| Module | Responsibility |
|---|---|
| `config.py` | Load and validate `config/*.yaml`; sampling helpers; largest-remainder quotas |
| `policy.py` | Read the approved policy JSON; BR-02 run detection and BR-03/BR-04 gap classification used for labels |
| `rng.py` | SHA-256 seed derivation: one independent stream per journey and per concern (plan, physics, sensor, comms, ...) |
| `journey.py` | One journey: ambient, thermal physics (1 min), sensor (5 min), transmission, ground-truth events |
| `dataset.py` | Scenario/ambient allocation, file writing, statistics, manifest |
| `splits.py` | Journey-level train/validation/test assignment and leakage check |
| `fileio.py` | Deterministic CSV/gzip output and hashing |
| `verify.py` | Check a dataset against its manifest; regenerate and compare |
| `__main__.py` | CLI: `generate`, `seeds`, `verify` |

Dependencies: Python 3.12 standard library + PyYAML (pinned in `backend/requirements.txt`). It runs in the backend image via the `data-tools` Compose service; nothing is installed on the host.

## Reproducibility contract

- Inputs: configuration file, seed, optional journey count. All three are recorded in `manifest.json`, and the configuration is copied as `config.yaml`.
- No wall-clock time, host name or random UUID enters the output. Gzip headers use `mtime=0`.
- Each journey uses `derive_seed(dataset_name, seed, "journey", index)`. Its data depends only on that seed, its scenario, its ambient profile and the configuration.
- `dataset_fingerprint` (SHA-256 over every file's path and uncompressed-content SHA-256) identifies the content independently of the zlib build.

## Tests

`tests/` (no `__init__.py`; file names start with `test_sim_` so they can share one pytest run with `backend/tests`). They run inside `docker compose --profile test run --rm --build backend-tests`, which mounts the repository read-only and sets `PYTHONPATH`.
