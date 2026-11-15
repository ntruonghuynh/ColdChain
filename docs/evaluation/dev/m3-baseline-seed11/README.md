# M3 policy baseline — development measurement (NOT a final result)

| Item | Value |
|---|---|
| Purpose | Development check of the Milestone 3 threshold baseline. Final results are produced in M9 on the reserved seeds 22, 33, 44, 55, 66 under the frozen protocol (D-13) |
| Data | Canonical dataset `coldchain-sim-v1.0.0-seed11`, partitions `train` + `validation` (170 journeys). The seed-11 `test` partition was **not** used. Seeds 22–66 are refused by the tool |
| Tuning | None: every value comes from policy `POL-CHILL-01` v1.0 and detector configuration `DET-BASELINE` v1.0.0 (see `run_config.json`) |
| Command | `docker compose --profile tools run --rm data-tools python -m app.evaluation baseline data/release/coldchain-sim-v1.0.0-seed11 --out docs/evaluation/dev/m3-baseline-seed11 --git-commit "74771cb+uncommitted-m3"` |
| Raw console output | `docs/milestones/m3/raw/03-dev-baseline-evaluation.txt` |
| Determinism | Re-running gives byte-identical `summary.json` and `matches.csv` (test `test_b79_b80_development_run_on_the_validation_partition`) |

Files: `run_config.json` (protocol, versions, seed, partitions), `summary.json` (metrics), `matches.csv` (one row per reference excursion: matched detection, `T0`, `E1`, `Ea`, `Te`, delays), `detections.csv` (every incident raised in the causal replay), `missing_data_intervals.csv` (reference missing-data intervals and the operational gap found for each).

Method (contract §6): each journey is replayed causally from the observed files only (batches at their recorded `received_at`, documented departure and arrival boundaries) with the same code as the operational detector. Reference events (`EXCURSION_HIGH`/`LOW`, `MISSING_DATA`) are read only here. Matching is deterministic one-to-one (U-06). Delays use the earliest raised incident revision that overlaps the reference event. Missed events and false alarms have no delay.

## Results (copied from `summary.json`)

| Metric | Value |
|---|---|
| Reference excursions / detections raised / matched | 81 / 94 / 75 |
| Event-level precision / recall | 0.7979 / 0.9259 |
| False alarms (per journey) | 19 (0.1118); none of them later superseded or merged |
| HIGH: reference / raised / matched | 61 / 66 / 55 |
| LOW: reference / raised / matched | 20 / 28 / 20 |
| Event-time delay `Ea − T0` (min), n = 75 | median 32.0, mean 35.507, p90 55.0, min 15.0, max 151.0 |
| Emission delay `Te − T0` (min, causal `raised_at`), n = 75 | median 39.117, mean 93.837, p90 279.45, min 17.25, max 619.3 |
| Components (median, min): first evidence `E1 − T0` / policy duration `Ea − E1` / transmission `Te − Ea` | 4.0 / 30.0 / 9.083 |
| Alerts raised before onset | 0 |
| Recall, reference excursions with missing readings / without | 12/15 (0.8) / 63/66 (0.9545) |
| Recall, reference excursions with delayed readings | 28/29 (0.9655) |
| Reference missing-data intervals found as confirmed gaps (identical bounds, same status) | 355 / 355 (355, 355) |
| `DATA_GAP` incidents raised / ending with basis superseded by data | 32 / 2 |
| End-boundary gap revisions raised / still present at the end | 116 / 2 |
| Gap time counted as in range | 0 by construction (no in-range-time measure exists) |

Limitations: one simulator, one seed, development partitions only, no uncertainty estimate (M9 adds per-seed values and intervals). The baseline is evaluated against labels produced by the same simulator; see the data dictionary §7.
