"""Deterministic temporal safeguards; no provider calls."""

from datetime import UTC, datetime

from coldchain_llm.schemas import Citation, ExplanationContent, TemporalClaim
from coldchain_llm.temporal import build_temporal_facts, timestamp_relation
from coldchain_llm.validate import validate_generated_content


def _content(claim: str, temporal: list[dict] | None = None) -> ExplanationContent:
    return ExplanationContent(
        summary_vi=claim,
        citations=[Citation(source_id="SYS:m3-detection/d1", claim="Detection timestamp", quote="raised")],
        temporal_claims=[TemporalClaim(**row) for row in (temporal or [])],
    )


def _validate(content: ExplanationContent, facts: list[dict], cutoff: str):
    interval = ("2026-09-14T00:00:00+00:00", "2026-11-17T08:27:42+00:00")
    raw = content.model_dump_json()
    return validate_generated_content(
        raw, {"SYS:m3-detection/d1": "raised"}, finish_reason="stop", prompt_tokens=10,
        completion_tokens=10, required_policy_version="1.0", required_sensor_interval=interval,
        response_policy_version="1.0", response_sensor_interval=interval,
        temporal_facts=facts, evidence_cutoff_at=cutoff,
    )


def test_m6r016_temporal_contradiction_fails_closed_and_correct_claim_passes() -> None:
    cutoff = "2026-11-17T08:27:42Z"
    fact = {"evidence_ref": "SYS:m3-detection/d1", "timestamp_field": "raised_at",
            "timestamp": "2026-09-14T09:51:13Z", "relation_to_cutoff": "before"}
    wrong_claim = {**fact, "statement_vi": "Detection raised_at 2026-09-14T09:51:13Z occurred after the cutoff.",
                   "relation_to_cutoff": "before"}
    result, diagnostics = _validate(_content("Detection occurred after cutoff.", [wrong_claim]), [fact], cutoff)
    assert result is None
    assert diagnostics.temporal_validation_status == "failed"
    assert diagnostics.temporal_failure_category == "temporal_cutoff_contradiction"
    good_claim = {**fact, "statement_vi": "Detection raised at 2026-09-14T09:51:13Z, before the cutoff."}
    result, diagnostics = _validate(_content("Detection was available before cutoff.", [good_claim]), [fact], cutoff)
    assert result is not None
    assert diagnostics.temporal_validation_status == "passed"


def test_invalid_temporal_claim_reference_or_relation_fails_closed() -> None:
    cutoff = "2026-11-17T08:27:42Z"
    fact = {"evidence_ref": "SYS:m3-detection/d1", "timestamp_field": "raised_at",
            "timestamp": "2026-09-14T09:51:13Z", "relation_to_cutoff": "before"}
    invalid_claim = {**fact, "statement_vi": "Mốc này đã có trước cutoff.",
                     "relation_to_cutoff": "after"}
    result, diagnostics = _validate(_content("Mốc thời gian được đối chiếu.", [invalid_claim]), [fact], cutoff)
    assert result is None
    assert diagnostics.temporal_validation_status == "failed"
    assert diagnostics.temporal_failure_category == "temporal_fact_mismatch"


def test_temporal_facts_keep_event_and_received_times_distinct_and_use_utc() -> None:
    cutoff = datetime.fromisoformat("2026-11-17T08:27:42+00:00")
    evidence = {
        "incident": {"incident_id": "i", "revision": 1, "opened_at": "2026-09-14T12:00:00+02:00"},
        "readings": [{"reading_id": "r", "event_at": "2026-11-17T11:20:00+02:00",
                      "received_at": "2026-11-17T11:30:00+02:00"}],
        "m3_detections": [], "gaps": [], "warnings": [],
        "m4_predictions_advisory_only": [], "m5_dispositions_available_by_cutoff": [],
        "sensor_interval_start_at": "2026-11-17T08:00:00+00:00",
        "sensor_interval_end_at": "2026-11-17T08:27:42+00:00",
    }
    facts = build_temporal_facts(evidence, cutoff)
    event = next(f for f in facts if f.get("timestamp_field") == "event_at")
    received = next(f for f in facts if f.get("timestamp_field") == "received_at")
    assert event["relation_to_cutoff"] == "after"
    assert received["relation_to_cutoff"] == "after"
    assert received["availability_at_cutoff"] == "unavailable"
    assert received["received_after_event_at"] == "yes"
    assert timestamp_relation("2026-11-17T08:27:42Z", cutoff) == "at"


def test_missing_timestamp_remains_unknown_and_detection_can_extend_beyond_readings() -> None:
    cutoff = datetime(2026, 11, 17, 8, 30, tzinfo=UTC)
    evidence = {
        "incident": {"incident_id": "i", "revision": 1, "opened_at": "2026-09-14T00:00:00Z"},
        "readings": [{"reading_id": "r", "event_at": "2026-11-17T08:00:00Z", "received_at": "2026-11-17T08:01:00Z"}],
        "m3_detections": [{"detection_id": "d", "last_event_at": "2026-11-17T08:15:00Z"}],
        "gaps": [], "warnings": [], "m4_predictions_advisory_only": [],
        "m5_dispositions_available_by_cutoff": [], "sensor_interval_start_at": "2026-11-17T07:00:00Z",
        "sensor_interval_end_at": "2026-11-17T08:30:00Z",
    }
    facts = build_temporal_facts(evidence, cutoff)
    missing = next(f for f in facts if f.get("timestamp_field") == "revision_raised_at")
    beyond = next(f for f in facts if f.get("timestamp_field") == "last_event_at_vs_latest_observed_reading")
    assert missing["relation_to_cutoff"] == "unknown"
    assert beyond["relation_to_latest_observed"] == "after"


def test_reading_with_missing_or_naive_timestamps_stays_unknown_without_crashing() -> None:
    cutoff = datetime(2026, 11, 17, 8, 30, tzinfo=UTC)
    evidence = {
        "incident": {"incident_id": "i", "revision": None, "opened_at": "2026-11-17T08:00:00Z"},
        "readings": [
            {"reading_id": "r1", "event_at": None, "received_at": None},
            {"reading_id": "r2", "event_at": "2026-11-17T08:10:00", "received_at": "2026-11-17T08:11:00"},
        ],
        "m3_detections": [], "gaps": [], "warnings": [],
        "m4_predictions_advisory_only": [], "m5_dispositions_available_by_cutoff": [],
        "sensor_interval_start_at": "2026-11-17T08:00:00Z", "sensor_interval_end_at": "2026-11-17T08:30:00Z",
    }
    facts = build_temporal_facts(evidence, cutoff)
    event = next(f for f in facts if f.get("evidence_ref") == "SYS:reading/r1" and f.get("timestamp_field") == "event_at")
    received = next(f for f in facts if f.get("evidence_ref") == "SYS:reading/r1" and f.get("timestamp_field") == "received_at")
    assert event["relation_to_cutoff"] == "unknown"
    assert received["availability_at_cutoff"] == "unavailable"


def test_sop_effective_date_before_cutoff_but_after_historical_incident_is_not_backdated() -> None:
    from coldchain_llm.temporal import date_relation

    incident = datetime.fromisoformat("2026-09-14T09:51:13+00:00")
    cutoff = datetime.fromisoformat("2026-11-17T08:27:42+00:00")
    assert date_relation("2026-11-14", cutoff) == "before"
    assert date_relation("2026-11-14", incident) == "after"
