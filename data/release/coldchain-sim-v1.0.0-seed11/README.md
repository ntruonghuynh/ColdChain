# coldchain-sim-v1.0.0-seed11 — SYNTHETIC DATASET

**All data in this folder is simulated** by the `coldchain_sim` generator for a teaching
prototype. It does not describe real shipments, products, sensors or organizations.
Policy values are teaching values, not regulatory or clinical limits.

| Item | Value |
|---|---|
| Dataset ID | `coldchain-sim-v1.0.0-seed11` |
| Dataset version | 1.0.0 |
| Generator | coldchain_sim 1.0.0 |
| Configuration version | 1.0.0 |
| Seed | 11 |
| Journeys | 200 |
| Policy | POL-CHILL-01 v1.0 |
| Timezone | UTC (every timestamp ends in `Z`) |
| Units | °C, percent, minutes, seconds (see column names) |

Folders: `observed/` is what a monitoring system would receive; `ground_truth/` holds the
simulated physical truth and labels and must never be used as model input; `splits/` assigns
each journey to one partition.

Field definitions, label rules and limitations: `data/dictionary/data-dictionary.md`.
Checksums: `manifest.json`. Statistics: `statistics.json`.

Regenerate: `docker compose --profile tools run --rm data-tools python -m coldchain_sim generate --config data/generator/config/coldchain-sim-v1.yaml --seed 11 --out data/generated/<folder>`
