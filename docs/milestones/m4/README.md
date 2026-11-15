# Milestone 4 report — machine-learning feature engineering, training, freezing and inference

| Item | Value |
|---|---|
| Status | Implemented and verified on `feat/m4-machine-learning`; pending project-owner review |
| Requirements | FR-13, FR-14, FR-15 API side, FR-25, DATA-05, DATA-06, DATA-09, ML-01 to ML-10, NFR-03/04, SUB-03 |
| Model | `coldchain-rf-v1.0.0` (Random Forest, advisory only) |
| Training/evaluation protocol | `m4-dev-v1`; canonical seed 11 only; train and validation for selection; one internal test run after freeze; seeds 22/33/44/55/66 unopened |
| Policy/data integrity | Approved policy and canonical seed-11 release unchanged; evidence in [`raw/integrity.txt`](raw/integrity.txt) |

## Implemented

- Reproducible 60-minute sliding-window feature extraction, five-minute stride, filtering on both event and receipt timestamps, explicit missingness and fixed insufficient-evidence behavior. The exact 25-feature schema is in [`../../design/m4-feature-dictionary.md`](../../design/m4-feature-dictionary.md).
- One allow-listed offline label loader provides only the true policy-excursion target intervals. Operational features and inference use observed readings/context only. Journey IDs, sensor IDs, route/upload metadata, scenario names, labels and hidden physical temperatures are excluded from features.
- Journey-level seed-11 partitioning is checked at 140 train / 30 validation / 30 internal test journeys. Training reads train and validation only. Test results were evaluated once after freeze, with no subsequent tuning. Reserved evaluation seeds were not opened.
- Logistic regression and two small Random Forest candidates use a deterministic preprocessing/training pipeline. Validation selects the model, threshold and consecutive-window rule. Event matching reuses M3's deterministic one-to-one matcher.
- Frozen bundle, machine-readable manifest, ordered feature spec, training config, model card and SHA-256 file list. Backend inference verifies the frozen bundle, dependency versions, policy hash and feature schema; application startup does not train.
- `POST /api/predictions` returns a validated window-level score or `INSUFFICIENT_EVIDENCE`. Every request appends an immutable audit row with model and schema versions. It does not change readings, baseline detections, incidents, dispositions, releases or shipment status. `GET /api/predictions/model` checks model readiness.
- Migration `0004` is additive. The `ml_prediction` table has a database trigger that rejects UPDATE and DELETE.

## Target and features

The binary window target is “a policy-defined true excursion is active at this prediction timestamp.” It detects a current state; it does not forecast onset. Alert direction comes from observed temperature values. The model does not predict simulator cause classes.

The 25 frozen features are: temperature mean, minimum, maximum, standard deviation, last value, range, slope, largest step, observed above-limit sample-minutes, observed below-limit sample-minutes, longest observed out-of-range run, reading count, missing fraction, coverage ratio, longest observed gap, spike residual, ambient mean, product-minus-ambient mean, door-open fraction, battery minimum, battery slope, latest receipt age, ambient observation count, door observation count and battery observation count. Context summaries use only context received by the prediction time. Missing values are never interpolated; context absence is accompanied by an observation count.

Six eligible observations and 0.4 coverage are required to score. This is a fixed evidence-quality cutoff, not a policy threshold. A window below it has no probability score, and the API explicitly returns that temperature risk is unknown.

## Training, selection and frozen configuration

The verified canonical release has fingerprint `80c4aec06daf3554ba0eecea7ff63d3d14cd5545df43cc7b94601b1fe8a9970d`. Train produced 80,542 windows (2,396 active-risk targets) from 140 journeys. Validation contained 17,548 windows (932 active-risk targets) from 30 journeys; 16,827 windows met the evidence rule. Counts are saved in [`raw/dataset-sample-counts.txt`](raw/dataset-sample-counts.txt).

The configuration [`../../../ml/configs/training-v1.json`](../../../ml/configs/training-v1.json) compares logistic regression and Random Forests with 120 trees/depth 8/minimum leaf 5 and 180 trees/depth 12/minimum leaf 3. Random Forest uses `balanced_subsample` class weights. Preprocessing is median imputation with missing indicators; logistic regression additionally standardizes its inputs. Seed is 11, one job is used for deterministic Random Forest fitting, and dependency versions are locked.

The selected model is `rf_deeper`: 180 trees, maximum depth 12, minimum leaf size 3, `balanced_subsample`, random seed 11. Validation selected probability threshold 0.7 and three adjacent five-minute windows. The third positive sample activates an advisory segment; subsequent adjacent positive windows merge into it. An inactive or insufficient-evidence window ends the segment. Score is the maximum member-window score. This score is not calibrated to the probability of product harm. Reproduction instructions are in [`ml/README.md`](../../../ml/README.md).

## Validation results and M3 baseline comparison

Both systems use the same 30 seed-11 validation journeys, 16 reference events, observed inputs, causal time restrictions and one-to-one M3 event matcher. The M3 baseline was run with `--partitions validation`; its run configuration records that scope. Metrics are development measurements only.

| Event-level metric | M3 threshold baseline | Selected ML Random Forest |
|---|---:|---:|
| Journeys / reference events | 30 / 16 | 30 / 16 |
| Detections / matches | 14 / 14 | 14 / 13 |
| Precision | 1.000 | 0.929 |
| Recall | 0.875 | 0.813 |
| False alarms per journey | 0.000 | 0.033 |
| Median delay among matched events | 41.992 min (n=14) | 33.000 min (n=13) |

The Random Forest has higher precision than the logistic comparator (0.737) and fewer false alarms, but the comparison with M3 shows lower event recall and one false alarm. **M4 does not outperform the M3 baseline overall.** The shorter delay median has a different matched-event count and does not offset the recall loss.

Selected-model window metrics, shown separately from event metrics: precision 0.978, recall 0.910; confusion matrix `[[16014, 16], [72, 725]]` for label order `[0,1]` among 16,827 evidence-sufficient windows. M3 has no comparable window classifier metric.

Scenario strata are evaluation-only and were never inference features. On validation the selected model matched 2/4 gradual-warming events, 4/4 high, 4/4 low, 2/2 events in missing-reading journeys and 1/2 in ocean-coverage-gap journeys; it produced no detections among 7 normal, 3 sensor-bias/drift, or 2 sensor-spike primary-scenario journeys. The small denominators make these descriptive only.

Raw validation predictions, aggregated events, candidate metrics, training config and the same-scope M3 output are in [`ml/evaluation/dev/`](../../../ml/evaluation/dev/). See [`raw/baseline-validation.txt`](raw/baseline-validation.txt) and [`ml/evaluation/dev/baseline-validation/run_config.json`](../../../ml/evaluation/dev/baseline-validation/run_config.json).

## One-shot post-freeze internal test

After the frozen checksums passed, seed-11 test was evaluated once: 30 journeys, 18,579 windows (17,733 with sufficient evidence), 12 reference events and 12 event detections. Ten events matched: event precision 0.833, recall 0.833, false alarms/journey 0.067, median matched-event delay 23 minutes (n=10). Window precision was 0.887 and recall 0.906; confusion matrix `[[17520, 22], [18, 173]]`. No threshold, hyperparameter or feature was changed from this result, and the M3 baseline was not run on the test partition.

The test strata include two reference events in ocean-coverage-gap journeys, and the model detected neither. A post-freeze comparison against M3's unchanged baseline is now recorded below. This remains an internal holdout comparison, not model selection. `ml/evaluation/internal-test-seed11/holdout-use.json` records the one-shot ML evaluation and frozen model hash. No reserved seed was evaluated.

### Post-freeze internal holdout comparison

The unchanged M3 threshold baseline was replayed on exactly the same 30 seed-11 test journeys after the frozen Random Forest's existing one-shot evaluation. The wrapper invokes M3's existing causal `SensorEvaluator` replay, `summarize()` and one-to-one matcher; it bypasses only the ordinary development CLI's test-partition refusal. Policy, detector configuration, ML artifact, threshold, features, and matching rules were not changed. This result was not used for model selection.

| Event-level result | M3 threshold baseline | Frozen Random Forest |
|---|---:|---:|
| Journeys / reference events | 30 / 12 | 30 / 12 |
| Detected events | 11 | 12 |
| True positives / false positives | 11 / 0 | 10 / 2 |
| Precision | 1.000 | 0.833 |
| Recall | 0.917 | 0.833 |
| False alarms per journey | 0.000 | 0.067 |
| Median causal emission delay | 45.583 min (n=11) | 23.000 min (n=10) |

The delay medians cover different matched event sets, so they do not establish that ML is faster overall. The baseline matched both ocean-gap events; ML matched neither. On reference events with delayed readings, baseline recall was 3/3 and ML recall was 1/3. On the single reference event labeled with missing readings, both matched it (1/1 each). These groups overlap and have very small counts. The baseline also found all 63 reference missing-data intervals with exact bounds and matching gap status; its detector counts no unknown gap time as in-range. Details are in [`raw/internal-test-baseline/comparison-summary.json`](raw/internal-test-baseline/comparison-summary.json) and the event/match CSVs in that folder.

### Paired validation delay analysis

For the 30 validation journeys, the baseline and Random Forest matched the same 13 reference events. On this shared intersection, median baseline delay was 36.433 minutes and median ML delay was 33.000 minutes. The median of the 13 per-event differences (ML minus baseline) was **−4.067 minutes**; the difference between the two shared-set medians was −3.433 minutes. The baseline alone detected one additional reference event (`SIM-S11-J0134`, `EXCURSION_HIGH`, onset 2026-10-19 15:40 UTC); ML detected no event that the baseline missed. This post-hoc paired comparison uses the existing event matcher and does not change the validation selection. Thirteen paired events are too few for a stable general speed claim, and no uncertainty interval is estimated. The earlier 41.992-minute versus 33-minute medians used different matched sets and must not be interpreted as a paired speed advantage. See [`raw/internal-test-baseline/paired-validation-summary.json`](raw/internal-test-baseline/paired-validation-summary.json) and `paired-validation-delays.csv`.

### Ocean coverage-gap diagnostic

The two missed ML holdout references are `SIM-S11-J0083-E008` and `SIM-S11-J0191-E010`. In their reference excursion intervals, respectively, 45/45 and 26/26 prediction windows returned `INSUFFICIENT_EVIDENCE` in the frozen offline output. Each such window had zero readings received by its as-of time and 13 event-time readings still pending receipt. All 45 and 26 corresponding delayed readings were received at or after the end of their labeled excursion intervals. Consequently neither event had an operational ML score, neither had a threshold-positive window, and no three-positive-window run existed. **The aggregation rule did not suppress an otherwise eligible alert; the model abstained because the telemetry had not arrived.**

M3 matched both events after their delayed readings became available in causal replay. This difference is consistent with M3's replay of late-arriving observations and does not establish that the ML API can infer from data it has not received. The live API returns no probability for insufficient evidence, sets `temperature_safety_established=false`, and states that risk is unknown; a below-threshold score is explicitly not a safety finding. Missing telemetry is therefore represented as unknown, never safe. The diagnostic scripts, per-window causal availability trace, and event summary are in [`raw/internal-test-baseline/`](raw/internal-test-baseline/).

## API and Docker verification

Live inference and database evidence are in [`raw/inference-api-live.txt`](raw/inference-api-live.txt): a scored cutoff returned `SCORED` with 11 observations, 0.846 coverage, score 0.0021 and `temperature_safety_established=false`; a cutoff before the first reading receipt returned `INSUFFICIENT_EVIDENCE` with no score and “temperature risk is unknown.” A read-only SQL query confirmed both model-versioned rows persisted; the append-only trigger was enabled. The API regression test confirms no reading, incident, disposition, release or shipment-state writes.

The rebuilt Docker backend and frontend became healthy; `/api/health` reported migration `0004`; model readiness reported `coldchain-rf-v1.0.0`. The full-stack smoke test passed 18/18 checks including proxy outage/recovery, shutdown/restart without volume deletion, and database/policy persistence. After restart, the model remained ready and both inference rows remained in PostgreSQL.

## Verification results

| Check | Result | Evidence |
|---|---|---|
| Backend, ML, migration and simulator/generator tests | **290 passed**, 1 Starlette/httpx deprecation warning | [`raw/backend-generator-tests.txt`](raw/backend-generator-tests.txt) |
| Frontend tests | **24 passed** | [`raw/frontend-tests.txt`](raw/frontend-tests.txt) |
| TypeScript typecheck | Passed | [`raw/frontend-typecheck.txt`](raw/frontend-typecheck.txt) |
| Frontend production build | Passed | [`raw/frontend-build.txt`](raw/frontend-build.txt) |
| Docker build, startup and migration 0004 | Passed | [`raw/docker-compose-startup.txt`](raw/docker-compose-startup.txt) |
| Full-stack smoke | **18 passed, 0 failed** | [`raw/full-stack-smoke.txt`](raw/full-stack-smoke.txt) |
| Live inference and model readiness | Scored and insufficient-evidence branches passed | [`raw/inference-api-live.txt`](raw/inference-api-live.txt) |
| Frozen bundle checksum verification | All five listed artifacts `OK` | `ml/registry/coldchain-rf-v1.0.0/SHA256SUMS` |
| Policy/canonical integrity and ground-truth boundary | Passed | [`raw/integrity.txt`](raw/integrity.txt), backend test log |
| Frozen feature order | 25 feature names in `feature_spec.json` match inference code order; its SHA-256 matches the model manifest artifact entry | [`raw/internal-test-baseline/artifact-audit.json`](raw/internal-test-baseline/artifact-audit.json) |
| Operational leakage and authorization | Offline label reader is the only added ground-truth allow-list entry; inference imports observed-data adapter only; prediction is advisory and appends only an ML audit row | [`raw/integrity.txt`](raw/integrity.txt), `backend/tests/test_ground_truth_boundary.py`, `backend/tests/test_m4_prediction_api.py` |
| Current Docker socket health recheck | Not observable: Docker CLI received permission denied for the local socket. Prior captured startup and smoke evidence above remains the available evidence. | [`raw/docker-health-recheck.txt`](raw/docker-health-recheck.txt) |
| Focused audit test rerun | Not rerun successfully in the current host environments: the temporary Python environment lacks Alembic and the backend `.venv` lacks joblib. Existing complete 290-test Docker log remains green; the audit scripts executed successfully. | [`raw/focused-audit-tests-py312.txt`](raw/focused-audit-tests-py312.txt), [`raw/focused-audit-tests.txt`](raw/focused-audit-tests.txt) |

## Limitations and remaining scope

- This model is trained and evaluated on one synthetic seed. It is not evidence about real shipments, sensor vendors, products or failure prevalence, and it is not a release decision.
- The validation set has only 16 reference events; the one-shot test has 12. Scenario-level precision/recall is unstable at these counts.
- The model reports risk/no-risk only. It does not output a simulator-cause diagnosis, predict future excursion onset, or directly distinguish bias from drift as output labels.
- The model misses both ocean-gap reference events in the internal test. Missing or delayed observations can lead to insufficient evidence or missed detections; missing data never means safe.
- On this seed-11 internal holdout, the unchanged baseline outperformed ML on event recall, precision, and false alarms. The smaller paired validation sample shows only a 3.433-minute median difference on shared matches and does not support a general speed advantage.
- The model manifest pins the ordered `feature_spec.json` by SHA-256 and records its schema version, but it does not duplicate the ordered feature-name array as a separate manifest field. The verified feature-spec order matches inference code. The frozen bundle was left unchanged during this audit.
- The API returns a window-level advisory score. The deterministic aggregator merges adjacent windows for evaluation; no ML incident queue, push notification or event-level UI is implemented. The frontend UI for ML comparison is M7. Repeated API calls are separately recorded; the audit does not imply separate incidents.
- The general readiness endpoint reports API/database health; frozen-model readiness is reported separately at `GET /api/predictions/model`.
- Reserved seeds 22, 33, 44, 55 and 66 remain unopened for M9. No frontend ML display or quality workflow was started.

## Final acceptance status

The M4 implementation and requested final audit evidence are complete; the work is **ready for project-owner acceptance review**, not self-approved. Frozen artifacts, policy, canonical data, M3 logic and selection protocol were not changed. The main acceptance caveats are the lower Random Forest holdout recall versus M3, both missed ocean-gap events due to no received telemetry, the small synthetic evaluation sample, and the manifest's indirect feature-order pin through the checksummed feature spec.

## Evidence paths

- Frozen model and checksums: `ml/registry/coldchain-rf-v1.0.0/`
- Validation outputs and M3 baseline: `ml/evaluation/dev/`
- One-shot internal holdout: `ml/evaluation/internal-test-seed11/`
- M4 raw logs: `docs/milestones/m4/raw/`
- Feature definitions: [`docs/design/m4-feature-dictionary.md`](../../design/m4-feature-dictionary.md)
- Model/API contract: [`docs/design/m4-ml-contract.md`](../../design/m4-ml-contract.md), [`docs/api/predictions-api.md`](../../api/predictions-api.md)
