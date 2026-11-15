# M4 prediction API

The prediction API is advisory. It reads operational `reading` and `context_reading` rows received by the requested cutoff, uses the shipment's pinned policy, and appends the result to `ml_prediction`. It never reads ground-truth data or modifies incidents, decisions, releases or shipment status.

## Model readiness

`GET /api/predictions/model` verifies the configured model bundle and reports `ready` with its version, or `unavailable` with a controlled detail code. General API/database health remains at `GET /api/health`.

## Score a window

`POST /api/predictions`

```json
{
  "shipment_id": "SIM-S11-J0001",
  "sensor_id": "SIM-S11-L0001",
  "as_of": "2026-09-10T12:00:00Z"
}
```

`sensor_id` may be omitted when exactly one sensor is assigned at `as_of`. Extra request fields are rejected. The timestamp must include a timezone, and both `event_at` and `received_at` must be no later than it. Only readings from the trailing 60 minutes are used.

`SCORED` includes `risk_probability`, selected threshold, alert flag, evidence counts, frozen model/schema version, and a unique `prediction_id`. `INSUFFICIENT_EVIDENCE` has no score and states that temperature risk is unknown. A low score or no alert is never a safety result: `temperature_safety_established` is always `false`, and `advisory_only` is always `true`.

Each response is written once to the append-only `ml_prediction` table. Repeating an identical request creates another auditable inference record; no request idempotency key is defined. The ML record cannot authorize release, quarantine disposition or warehouse activity.
