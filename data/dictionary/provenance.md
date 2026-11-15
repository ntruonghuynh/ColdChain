# Provenance record — `coldchain-sim` synthetic dataset

| Item | Value |
|---|---|
| Data source | **Independently generated synthetic data** (decision D-02, approved in the Milestone 2 instructions, 2026-11-14). No public dataset, partner data or personal data is used, so no external licence or permission is needed. |
| Producer | Project team, using the generator in this repository (`data/generator/coldchain_sim`) |
| Generator version | `coldchain_sim` 1.0.0 (`data/generator/coldchain_sim/__init__.py`) |
| Configuration | `data/generator/config/coldchain-sim-v1.yaml`, `config_version` 1.0.0, SHA-256 `78c4d02b88324ffbf93e22a2f485f3d5438a1f8836c859677231d2e740fae7da` |
| Policy used for labels | `POL-CHILL-01` v1.0 (`backend/app/seed/data/policies/POL-CHILL-01_v1.0.json`), canonical SHA-256 `73f757e24319791dd6cb8200cf1863aac362d97d6ef32fe01bfa89566b5e0a96`, approved 2026-11-14 (requirements analysis §13.1) |
| Canonical seed | 11 |
| Canonical dataset | `data/release/coldchain-sim-v1.0.0-seed11/` |
| Dataset fingerprint | `80c4aec06daf3554ba0eecea7ff63d3d14cd5545df43cc7b94601b1fe8a9970d` (SHA-256 over every file's path and uncompressed-content SHA-256; see `manifest.json`) |
| Seed roles (A-13, 2026-11-15) | **11** = canonical development dataset (committed in full, unchanged). **22, 33, 44, 55, 66** = reserved for operational simulation evaluation; manifests in `data/release/seed-manifests/`. The tests regenerate all six seeds and compare each fingerprint with the committed one |
| Runtime used | Docker image `coldchain-backend:local` (Python 3.12, linux/arm64), via `docker compose --profile tools run --rm data-tools` |
| Generation run output | `docs/milestones/m2/raw/01-generate-canonical.txt`, `02-generate-evaluation-seeds.txt` (22–55), `10-generate-seed66.txt` (66) |
| Verification run output | `docs/milestones/m2/raw/05-verify-and-import.txt` (checksums and regeneration), `09-cross-architecture-regeneration.txt` (x86_64) |
| Licence of the data | Same terms as the repository; synthetic and free of personal data |
| Intended use | Teaching prototype: ingestion, detection, ML training and evaluation, demonstrations. **Not** for claims about real cold-chain performance or product safety |

## Approved simulation assumptions (Milestone 2 instructions, 2026-11-14)

One product category; one versioned temperature policy; normal range 2–8 °C; high excursion above 8 °C for at least 30 min; low excursion below 2 °C for at least 15 min; a missing-data gap over 15 min is UNKNOWN; a gap of 30 min or more requires quality review; nominal sampling interval 5 min; journey durations 24–72 h with 48 h default. The sampling interval and durations are **project simulation assumptions, not regulatory requirements**. All other parameters in the configuration file are the team's modelling choices and are documented in the data dictionary (§4).

## How to reproduce

```bash
# canonical dataset (writes to the git-ignored scratch folder)
docker compose --profile tools run --rm data-tools \
  python -m coldchain_sim generate --config data/generator/config/coldchain-sim-v1.yaml --seed 11 --out data/generated/seed11

# check the committed release against its manifest and by regenerating it
docker compose --profile tools run --rm data-tools \
  python -m coldchain_sim verify data/release/coldchain-sim-v1.0.0-seed11 --regenerate

# the five reserved evaluation seeds
docker compose --profile tools run --rm data-tools \
  python -m coldchain_sim seeds --config data/generator/config/coldchain-sim-v1.yaml --seeds 22,33,44,55,66 --out-root data/generated/seeds
```

Same seed + same configuration + same generator version → identical file content (same `content_sha256` per file and same `dataset_fingerprint`). Gzip file bytes are identical with the same zlib build.

## Change log

| Date | Dataset version | Change |
|---|---|---|
| 2026-11-14 | 1.0.0 | First release (Milestone 2). |
| 2026-11-15 | 1.0.0 | Seed roles decided (A-13). Manifest for reserved evaluation seed 66 added. No change to the generator, the configuration or the canonical seed-11 files. |

A changed configuration, generator or policy requires a new dataset version and a new release folder. Committed releases are not edited in place, and the importer refuses different content under an existing dataset ID.
