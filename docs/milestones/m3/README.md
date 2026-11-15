# Milestone 3 report — sensor ingestion, telemetry monitoring, threshold baseline, excursion queue

| Item | Value |
|---|---|
| Status | Final acceptance review completed 2026-11-15 on branch `feat/m3-monitoring-baseline`; **awaiting the owner's acceptance**. Not committed |
| Specification | [M3 detector contract](../../design/m3-baseline-detector-contract.md) (BR-05, C-01 to C-10, BR-06 to BR-09, U-01 to U-08) |
| Requirements addressed | FR-01, FR-02, FR-03, FR-04, FR-05, FR-10, FR-11, FR-12 (baseline side), FR-20, FR-30/FR-31 (M3 part), EVAL-01, EVAL-04/EVAL-05 (development measurement), EVAL-13, DATA-09, BR-02 to BR-09 (BR-09 amended by U-01), BR-13; traceability in requirements analysis §16.1 |
| Unchanged | Policy `POL-CHILL-01` v1.0 (file and version), canonical dataset `coldchain-sim-v1.0.0-seed11` (checksums verified, `raw/08`), ground-truth labels |

Every number below comes from the files in `raw/`, the saved screenshots, or the evaluation outputs. Files ending in `-codex.txt` are unfiltered command output from this acceptance rerun.

| File | Command(s) |
|---|---|
| `raw/01-replay-canonical.txt` | `python -m app.monitoring replay` (all 200 imported shipments), then again (idempotency) |
| `raw/02-ocean-demo.txt` | `python -m app.monitoring demo-ocean` (causal ocean coverage demonstration) |
| `raw/03-dev-baseline-evaluation.txt` | `python -m app.evaluation baseline ... --out docs/evaluation/dev/m3-baseline-seed11` |
| `raw/04-backend-and-generator-tests.txt` | `docker compose --profile test run --rm --build backend-tests` (final run) |
| `raw/05-smoke-test.txt` | `python3 scripts/smoke_test.py --keep-running` |
| `raw/06-api-via-proxy.txt` | M3 endpoints and SPA routes through the frontend proxy on port 3000 |
| `raw/07-frontend-tests-build.txt` | `npm test`, `npm run typecheck`, `npm run build` |
| `raw/08-canonical-data-and-policy-unchanged.txt` | `git status`/`git diff` of the release and policy folders, `coldchain_sim verify` |
| `raw/09-backend-and-generator-tests-codex.txt` | Current Docker backend + generator suite, including M3 acceptance boundaries |
| `raw/10-frontend-tests-build-codex.txt` | Current frontend tests, typecheck and production build after the incident-header fix |
| `raw/11-dev-baseline-evaluation-codex.txt` and `evaluation-rerun/` | Repeated seed-11 development evaluation with matching run metadata and raw outputs |
| `raw/12-replay-canonical-codex.txt` | Idempotent canonical replay rerun |
| `raw/13-ocean-demo-codex.txt` | Idempotent ocean demonstration rerun and causal checkpoints |
| `raw/14-smoke-test-codex.txt` | Current full-stack smoke test after the frontend rebuild |
| `e2e/interactive_asof.mjs` and `raw/15-interactive-asof-e2e.txt` | Interactive Playwright/Chrome causal as-of test at desktop and mobile viewports |
| `e2e/incident-count-reconciliation.sql` and `raw/16-incident-count-reconciliation.txt` | Read-only database count queries and matching causal API snapshots |
| `raw/17-canonical-integrity-rerun.txt` | Canonical seed-11 checksum and regeneration verification after E2E |
| `screenshots/*.png` | Headless Chromium captures at desktop and mobile viewport sizes; visually inspected |

## 1. Decisions and BR-10 to BR-15 review

- **Decision record:** requirements analysis §13.1 (row "Milestone 3 start").
- **BR-09:** amended explicitly by U-01; the original wording is kept (§13.2, §13.4).
- **BR-10 to BR-15:** reviewed in §13.5. No conflict blocks M3; BR-13 is applied to batch and incident references.

## 2. Implemented functionality

- **Ingestion**
  - `POST /api/ingest/batches`: exact-decimal parsing, per-record validation with stored reasons and raw payloads, sensor/shipment/monitoring-window checks (U-03).
  - BR-07 duplicates and conflicts for readings and context records (U-05).
  - BR-13 batch idempotency, one transaction per batch, a per-shipment advisory lock.
  - Server-set `received_at`. Trusted replay is available only through internal commands.
- **Monitoring:** causal CURRENT / STALE / UNKNOWN / NOT_STARTED / ENDED states, kept separate from confirmed gaps and from persistent `DATA_GAP` incidents.
  - Gaps: confirmed gaps with bracketing span versus estimated missing samples, boundary gaps from documented monitoring windows, 7 min 30 s continuity.
  - Delayed data: delayed and backfilled readings reconciled by deterministic full-journey recalculation.
- **Baseline:** policy values read from PostgreSQL (the shipment's own policy version), exact thresholds, runs broken by confirmed gaps, BR-05 adjacency flags and warnings.
- **Incidents:**
  - Idempotent creation with deterministic references.
  - Append-only revisions, supersession and merge without deletion.
  - Evidence, policy and detector-version references.
  - U-04 decision reassessment flags.
  - No code path closes an incident or releases goods.
- **API:** 12 new endpoints ([docs/api/monitoring-api.md](../../api/monitoring-api.md)).
- **Frontend:**
  - Temperature Monitoring: SVG timeline, hatched missing-data intervals, not-yet-received tail, state badge, causal "view as of".
  - Excursion Queue.
  - Incident detail: revisions, evidence, versions, "pending human quality review".
  - SIMULATED labels and loading, error and empty states throughout.
- **Ocean demonstration:** `python -m app.monitoring demo-ocean` (§7 below).
- **Offline evaluation:** `python -m app.evaluation baseline`, isolated (no database, refuses seeds 22–66 and the seed-11 test partition).

## 3. Database migration `0003` (additive)

New tables:

- `detector_config`
- `detector_evaluation`
- `data_gap`
- `detection`
- `data_quality_warning`
- `incident_revision`
- `decision_reassessment`

New columns:

- `incident`: `sensor_id`, `detector_config_id`, `opened_by_evaluation_id`.
- `ingest_batch`: `duplicate_count`, `ingest_mode`. Existing rows get `IMPORT`, and the counts check includes duplicates.

The downgrade to `0002` restores the M2 schema exactly (test `test_0003_is_additive_and_downgrades_to_the_milestone_2_schema`). Seed: detector configuration `DET-BASELINE` v1.0.0 (immutable, hashed like the policy).

## 4. Detector edge-case semantics (summary)

| Case | Behaviour |
|---|---|
| Reading at exactly 8.0 / 2.0 °C | In range; no tolerance |
| Run duration | Last minus first `event_at`, exact. 7 readings = 30 min, 4 = 15 min |
| Readings 7 min 30 s apart / 7 min 30.001 s apart | Continuous / `SHORT_GAP` that breaks the run |
| Gap thresholds | On the bracketing span: ≤ 15 min `SHORT_GAP`, > 15 min `UNKNOWN`, ≥ 30 min `UNKNOWN_REVIEW_REQUIRED` and a `DATA_GAP` incident |
| Silence before data arrives | Monitoring state only (never an incident, never in range) |
| Out-of-range run next to any confirmed gap | Qualifying: incident with `gap_continuity_warning`. Otherwise: `GAP_ADJACENT_OUT_OF_RANGE` evidence warning |
| Delayed or out-of-order batch | Full-journey recalculation; superseded revisions kept; incidents never closed (basis `SUPERSEDED_BY_DATA` / `MERGED_INTO`) |
| Late evidence after a disposition | Revision appended; status, disposition and release unchanged; `decision_reassessment` row |
| Monitoring end not documented | No trailing gap is ever confirmed; state stays UNKNOWN |
| Replay | Only readings with `received_at ≤ as_of` and boundaries reached by `as_of` |
| Rejected or ignored records | Not readings; their slots count as missing |

## 5. Results on the canonical data

| Run | Result |
|---|---|
| Causal replay of 200 imported shipments (`raw/01`) | 37,536 evaluations, 146 incidents opened, 1,007 incident revisions, 12.6 s. Second run: 0 written ("already evaluated: 200") |
| Ocean demo (`raw/02`), source chosen from observed data only: `SIM-S11-J0154`, 14.13 h without batches | CURRENT → STALE (7.52 min) → UNKNOWN (15.02 min, 45 min, mid-outage, 1 s before restore), with no incident. The restore batch (169 readings, original `event_at`) gives a `TEMPERATURE_EXCURSION` 15:02 → 17:42, raised at the restore receipt time 23:01:02, status OPEN. Causal re-check of all checkpoints: IDENTICAL |
| Monitoring summary as of 2026-11-15 (`raw/06`, 201 shipments including the demo) | 106 open `TEMPERATURE_EXCURSION` and 41 open `DATA_GAP` incidents; 2 with evidence superseded; 0 `SENSOR_FAULT_SUSPECTED` |

Development evaluation (seed 11 train + validation, 170 journeys; [details](../../evaluation/dev/m3-baseline-seed11/README.md); **not** the final M9 result):

- **Detection:** precision 0.7979, recall 0.9259 (75 of 81 reference excursions matched, 94 detections), 0.1118 false alarms per journey.
- **Delay:**
  - median event-time delay 32.0 min;
  - median emission delay 39.117 min (causal `raised_at`, maximum 619.3 min, driven by delayed delivery).
- **Missing readings:**
  - recall with missing readings 12/15, without 63/66;
  - all 355 reference missing-data intervals found as confirmed gaps with identical bounds and status.

## 6. Automated tests

| Suite | Result |
|---|---|
| Backend + generator (`raw/09`) | **278 passed, 0 failed**: 202 backend and 76 generator. One Starlette/httpx deprecation warning |
| Frontend (`raw/10`) | **24 passed**; `tsc --noEmit` clean; production build OK |
| Smoke test (`raw/14`) | **18 passed, 0 failed** (migration head 0003, outage, restart, persistence) |
| Interactive as-of E2E (`raw/15`) | **PASS** on Chrome 153.0.8010.12 at 1440×1000 desktop and 390×844 mobile; no console errors, page errors, failed requests, HTTP errors, or horizontal overflow |
| Canonical replay (`raw/12`) | **0 writes**, 200 shipments already evaluated |
| Ocean demo (`raw/13`) | Existing demo reused; checkpoints reproduced and idempotency held |

Boundary cases of contract §7 (test files under `backend/tests/`):

| Cases | Test(s) |
|---|---|
| B01–B12, B41–B43 (thresholds, durations) | `test_m3_detector_rules.py::test_b01_b04_*` (B01–B04, parametrized), `test_b02_*`, `test_b05_*` … `test_b12_*`, `test_b41_*`, `test_b42_*`, `test_b43_*` |
| B13, B14, B16, B44, B76 (jitter, continuity) | `test_m3_detector_rules.py::test_b13_*`, `test_b14_*`, `test_b16_*`, `test_b44_*`, `test_b76_*` |
| B15, B17–B20, B45–B47 (gap span, estimates) | `test_m3_detector_rules.py::test_b15_*`, `test_b17_b20_*` (parametrized B17, B18, B19, B20), `test_b45_*`, `test_b46_*`, `test_b47_*` |
| B21–B26 (BR-05 adjacency) | `test_m3_detector_rules.py::test_b21_*` … `test_b26_*` |
| B27, B48, B49, B50 (STALE versus confirmed gap) | `test_m3_detector_rules.py::test_b27_b48_*`, `test_b48_*`; `test_m3_detection_service.py::test_b49_*`, `test_b50_*` |
| B28, B51 (ocean outage) | `test_m3_reconcile_replay.py::test_b28_*`, `test_b51_*`; `test_m3_detection_service.py::test_b28_*` |
| B29–B31, B33, B52, B53 (out of order, recalculation) | `test_m3_reconcile_replay.py::test_b29_*`, `test_b30_*`, `test_b31_*`, `test_b33_*`, `test_b52_*`, `test_b53_*` |
| B32, B34, B54–B57 (duplicates, conflicts) | `test_m3_ingestion.py::test_b32_*`, `test_b34_b54_*`, `test_b55_*`, `test_b56_*`, `test_b57_*`, BR-13 conflict tests |
| B35, B39, B58–B60 (validation) | `test_m3_detection_service.py::test_b35_*`; `test_m3_ingestion.py::test_b39_*`, `test_b58_*`, `test_b59_*`, `test_b60_*` |
| B61–B64 (incident history) | `test_m3_reconcile_replay.py::test_b61_*`; `test_m3_detection_service.py::test_b62_*`, `test_b63_*` (two tests); `test_m3_evaluation.py::test_b64_*` |
| B65–B69 (replay causality) | `test_m3_reconcile_replay.py::test_b65_*`, `test_b67_*`, `test_b69_*`; `test_m3_detection_service.py::test_b65_*`, `test_b66_b68_*` |
| B37, B70–B75 (monitoring boundaries) | `test_m3_detector_rules.py::test_b37_*`, `test_b70_*`, `test_b71_*`, `test_b72_b74_*`, `test_b73_*`; `test_m3_ingestion.py::test_b75_*` |
| B36, B38, B77, B78 (versions, ground-truth isolation) | `test_m3_detection_service.py::test_b36_*`, `test_b77_*`; `test_ground_truth_boundary.py::test_d12_operational_api_exposes_no_ground_truth` (B38, now covering the M3 routes), `test_b78_*`, `test_operational_code_never_imports_the_evaluation_package` |
| B40, B79, B80 (delay fields, metrics) | `test_m3_detection_service.py::test_b40_*`; `test_m3_evaluation.py::test_b79_b80_*` and the `test_u06_*` matching and tie-break tests |

## 7. Deferred tests and known limitations

No boundary case is deferred to a later milestone. Partial or indirect coverage, stated honestly:

- **B33** excludes BR-07 conflicts and receipt-time fields (`raised_at`, `evidence_received_at`) by design (contract §5.10).
- **B62 and the U-04 tests** compare decision, incident, revision and release rows field by field after late evidence, using a test stand-in for the M5 quality workflow (direct database writes). The real disposition service is M5.
- **B64** has both a static no-database-import check and a before/after live-table row-count check during offline reprocessing under another configuration.
- **B66** directly compares incremental state with a fresh causal calculation at every replay step and compares persisted as-of history with those fresh results.
- **B79** uses a run on the real validation partition with invariant checks, plus hand-made matching fixtures, instead of one combined synthetic fixture.

Direct target-case coverage is present in `test_m3_acceptance_boundaries.py`: B33 (360 arrival orders), B62 (late evidence leaves decision records unchanged), B64 (offline reprocessing leaves live tables unchanged), B66 (each step and persisted as-of history), and B79 (hand-made metric fixture plus validation-partition invariants). B33 deliberately excludes conflicting duplicates and receipt-time/history fields under the documented BR-07/contract §5.10 exception. B62 uses a test-only M5 disposition stand-in; the operational M3 path still cannot record dispositions.

Known limitations:

- **Monitoring display with 15-minute uploads.** The state briefly shows UNKNOWN before almost every on-schedule upload: 161 of 164 demo batches arrived in that state (`raw/06`). The approved thresholds were kept and the deliveries API reports `late_backfill` instead (contract §9 O-1, owner decision).
- **No shipment or sensor-assignment registration API** (M5). Live ingestion accepts readings only inside a documented window, so today it works for imported or demo shipments.
- **No authentication** (M5/M7). The ingestion endpoint is open on 127.0.0.1:3000, and live batches are attributed to the shipment's carrier.
- **No chain anchoring** of batches, incidents or revisions (U-07, M5).
- **Transient end-boundary gaps.** Development run: 116 raised, 2 remaining. Two `DATA_GAP` incidents ended "superseded by data" and stay open until quality closes them (contract §8).
- **Development numbers only.** They come from one seed and are not the M9 result. The canonical replay also ran over the seed-11 test journeys as operational detection, but no metric was computed on them.
- **Verification artefacts in the local database.** The demo shipment `DEMO-OCEAN-SIM-S11-J0154` and one live verification batch `PROXY-CHECK-1` (its single reading rejected, `OUTSIDE_MONITORING_WINDOW`) exist in the local development database. They are not in the repository.
- **Linting.** The new Python files were formatted with `ruff format` (line length 120). The remaining lint findings are FastAPI's standard `Depends`/`Query` defaults (B008), the same idiom as the existing routes. The repository has no lint configuration.
- **Playwright remains an isolated acceptance-test dependency.** It was installed under `/private/tmp` only; no package manifest or production dependency changed. The browser E2E passed at desktop and mobile sizes. The headless browser emitted no console, page, request, or HTTP errors.

## 8. Interactive as-of E2E

The acceptance rerun installed Playwright 1.65.1 into the isolated temporary prefix `/private/tmp/coldchain-m3-playwright` and drove the already-installed Chrome 153 binary. No project package manifest or production dependency changed. The runnable scenario and exact browser output are saved in `e2e/interactive_asof.mjs` and `raw/15-interactive-asof-e2e.txt`.

The test selects delayed-data shipment `SIM-S11-J0154`, applies both times through the visible UTC as-of control, and checks the rendered status, communication panel, chart count, incident count, and API payload causality:

| View | As-of | Visible readings | Latest event / receipt | Monitoring / communication | Incidents visible |
|---|---|---:|---|---|---|
| Before restoration | 2026-10-19 15:57:03 UTC | 315 | 08:52 / 08:53:05 UTC | UNKNOWN / LONGER_THAN_RECENT_UPLOAD_INTERVALS | 0 temperature, 0 gap |
| After restoration | 2026-10-19 23:02:00 UTC | 484 | 22:57 / 23:01:02 UTC | CURRENT / WITHIN_RECENT_UPLOAD_INTERVALS | 1 temperature, 0 gap |

For both timestamps and both viewport sizes, every displayed reading's `received_at` and every run's `raised_at` is no later than the selected cutoff. The pre-restore panel says the current temperature is not known, warns of a possible communication delay/outage, and says missing data is never treated as safe. The post-restore panel updates to CURRENT, shows the delayed readings, and lists the excursion only after its receipt. Browser console, page, network, and HTTP error collections were empty.

Screenshots: `screenshots/e2e-asof-before-desktop.png`, `e2e-asof-after-desktop.png`, `e2e-asof-before-mobile.png`, and `e2e-asof-after-mobile.png`. Both layouts fit their viewport widths (1440 px and 390 px).

## 9. Incident count reconciliation

The reported **146** and the dashboard's **147** count different shipment scopes. Canonical replay covers the 200 seed-11 shipments and has **146 distinct open incident rows**: 105 `TEMPERATURE_EXCURSION` plus 41 `DATA_GAP`. The current dashboard includes the separate `DEMO-OCEAN-SIM-S11-J0154` ocean-demo shipment, which contributes one additional open `TEMPERATURE_EXCURSION`, producing **106 + 41 = 147**. The reconciliation SQL, DB results, and two causal API snapshots are in `e2e/incident-count-reconciliation.sql` and `raw/16-incident-count-reconciliation.txt`.

This is not a revision count: canonical incidents have 1,007 append-only revisions and the demo incident has one. It is not a timestamp discrepancy: the current DB query groups the same OPEN rows by shipment scope, and the historical as-of E2E shows that the demo incident is absent before its restoration receipt and appears after it. No incident history was changed to reconcile the totals.

The canonical policy and dataset were checked again after E2E: `raw/17-canonical-integrity-rerun.txt` reports checksums OK and regeneration with identical content.

## 10. Final acceptance review

- **Communication status:** the communication API and `TelemetryStatusPanel` remain informational. The UI presents upload timing separately from sensor temperature and explicitly states that missing data is not safe. No policy threshold, detector rule, or approved CURRENT / STALE / UNKNOWN semantics changed.
- **Browser visuals:** inspected Overview, Shipments, Temperature Monitoring, Excursion Queue and Incident Details at 1440 px desktop; Temperature Monitoring was also inspected at 390 px mobile. Screenshots are in [`screenshots/`](screenshots/): Overview reports API/database connected; queue shows 106 temperature and 41 data-gap incidents; incident detail shows pending Quality review; temperature detail shows six confirmed intervals and hatching outside observed readings. Screenshots for the temperature page include the visible causal as-of control. No visual issue was found beyond the incident header title, which was fixed and covered by a frontend regression assertion.
- **Browser routes and API:** the local app returned HTTP 200 for `/api/health` (database ready, revision `0003`), shipments, incidents, summary and incident detail. SPA route responses and full-stack smoke results are recorded in `raw/06` and `raw/14`. The interactive as-of workflow and console/network inspection passed in `raw/15`.
- **Evaluation consistency:** rerun output under [`evaluation-rerun/`](evaluation-rerun/) has byte-identical `summary.json`, `run_config.json`, `detections.csv`, `matches.csv` and `missing_data_intervals.csv` to the recorded development evaluation. Metrics are unchanged: 170 journeys, 31,594 evaluations, precision 0.7979, recall 0.9259, 75/81 matched, 355/355 missing intervals. The run used seed 11 train and validation only; no final evaluation seeds were opened.
- **Integrity boundaries:** the 278-test backend/generator run passed seed regeneration/checksum, policy immutability, ground-truth isolation, append-only incident/revision, and causal replay assertions. The approved policy and canonical seed-11 dataset have no working-tree changes. The live service is healthy at migration `0003`; the smoke rerun confirmed persistence after restart.
- **Communication / risk language:** no missing-data state is represented as product-safe. No incident is automatically closed, and the detail page states that no release action is available.

## 11. Suggested commit breakdown (not committed)

1. `feat(backend): add M3 detector domain rules and migration 0003`: `app/domain/`, `app/db/models/{monitoring,enums,telemetry,workflow,__init__}.py`, migration `0003`, detector configuration seed and loader.
2. `feat(backend): add validated ingestion, causal detection and monitoring API`: `app/services/`, `app/api/{ingest,monitoring,monitoring_schemas,system,shipments}.py`, `app/main.py`, `app/core/config.py`, `app/monitoring/`.
3. `test(backend): add M3 boundary, ingestion, replay and API tests`: `tests/test_m3_*.py`, `tests/m3_helpers.py`, updated M1/M2 tests.
4. `feat(evaluation): add isolated development evaluation of the baseline`: `app/evaluation/`, `docs/evaluation/dev/m3-baseline-seed11/`.
5. `feat(frontend): add temperature monitoring, excursion queue and incident detail`: `frontend/src/**`.
6. `docs: record M3 decisions, contract, API reference and milestone report`: `docs/**`, `README.md`, `CLAUDE.md`, `backend/README.md`, `frontend/README.md`, `data/dictionary/data-dictionary.md`.
