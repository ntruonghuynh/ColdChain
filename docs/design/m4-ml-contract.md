# Milestone 4 ML contract

| Item | Value |
|---|---|
| Status | Implemented on `feat/m4-machine-learning`; acceptance evidence in [`docs/milestones/m4/README.md`](../milestones/m4/README.md) |
| Protocol | `m4-dev-v1`; seed 11 train/validation for selection, seed-11 test once after freeze; reserved seeds 22, 33, 44, 55, 66 remain unopened |
| Model | `coldchain-rf-v1.0.0`, advisory-only Random Forest classifier |
| Policy | `POL-CHILL-01` v1.0; its stored content hash is pinned in the model manifest |

## Prediction target and scope

Each sample is a **window-level binary classification**: `1` means a policy-defined true excursion (`EXCURSION_HIGH` or `EXCURSION_LOW`) is active at the prediction timestamp; `0` means no such reference event is active at that timestamp. This is current-state detection, not prediction of future onset. High/low direction on an alert is derived from observed temperatures in the window. The model does not predict simulator causes.

The label loader reads only the approved `EXCURSION_*` reference event intervals. Scenario names, injected causes and hidden physical-temperature values never enter feature rows or inference. Scenario names are read separately for offline reporting strata only. Features contain no journey or sensor identity, route, upload identifier, dataset partition, scenario, label, or simulator metadata.

## Causal window protocol

- Window span is 60 minutes with endpoints `[prediction_at - 60m, prediction_at]`; stride and nominal sample interval are five minutes. There are 13 expected event-time slots in a complete closed window.
- An input contributes only if `event_at <= prediction_at` **and** `received_at <= prediction_at`. Context values also require `context.received_at <= prediction_at`.
- A window is generated at five-minute timestamps from journey departure through arrival. Its label is whether the reference interval contains that timestamp (`start <= at < end`).
- Gaps remain absent. No temperature is interpolated, forward-filled or considered safe. Feature coverage describes observed slots; fewer than six observations or coverage below 0.4 returns `INSUFFICIENT_EVIDENCE`, with no score and an explicit unknown-risk message.
- The operational endpoint accepts a timezone-aware `as_of` timestamp, queries observed operational readings/context only, and returns a score or insufficient-evidence result. It also appends one immutable `ml_prediction` audit row with model and feature-schema version. It never changes a shipment, baseline detection, incident, disposition, release or warehouse state.

## Model selection and event alerts

Three candidates are trained on train journeys only: logistic regression as the simple comparator and two deterministic Random Forest configurations. Preprocessing is a median imputer with missingness indicators; logistic regression additionally standardizes features. Random Forest uses `balanced_subsample` class weights. Candidate hyperparameters and selection grid are in [`ml/configs/training-v1.json`](../../ml/configs/training-v1.json).

On validation, probability cutoffs `{0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8}` and minimum runs of `{1, 2, 3}` adjacent positive windows are compared using event-level F1. Ties prefer precision, then recall, then fewer false alarms per journey. Selected windows must meet the fixed evidence rule. Consecutive predicted windows form an event; an inactive or insufficient-evidence window terminates it. The event starts at its first positive timestamp, ends at its last positive timestamp, and is raised at the timestamp that satisfies the selected consecutive-window rule. Score is the maximum member-window probability. A score is not a calibrated probability of product harm.

Event evaluation uses M3's deterministic one-to-one matching: same journey, same high/low direction, overlapping event-time intervals, with the tie breaks in `backend/app/evaluation/matching.py`. Delay is emission timestamp minus reference onset, floored at zero for the aggregate; missed events have no delay. Window precision/recall and confusion matrix are reported separately from event precision/recall.

## Frozen package

`ml/registry/coldchain-rf-v1.0.0/` contains `model.joblib`, `feature_spec.json`, `training_config.json`, `model_card.md`, `model_manifest.json`, and `SHA256SUMS`. The manifest records the selected candidate/settings, threshold, preprocessing, ordered features, seed, dataset fingerprint, policy hash, protocol, validation metrics and library versions. Inference checks listed file hashes and rejects an incompatible model version, policy hash, or feature schema. Startup does not train or replace the artifact.

## Limits

The only development corpus is synthetic, and the seed-11 validation partition contains 30 journeys and 16 excursion events. This provides limited evidence about real shipment variability, fault prevalence, calibration, sensor vendors, and operational costs. The target is a simulator-derived policy interval; it is not a clinical or regulatory label. Window overlap creates correlated samples, so window metrics are not independent-sample uncertainty estimates. The internal test is a single post-freeze check, not a tuning set. No result here supports a real-world safety or release decision.
