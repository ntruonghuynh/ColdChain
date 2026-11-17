"""Deterministic, cutoff-relative facts for timestamps supplied to explanations."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any


def parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC)


def timestamp_relation(value: Any, cutoff: datetime) -> str:
    parsed = parse_timestamp(value)
    if parsed is None:
        return "unknown"
    cutoff_utc = cutoff.astimezone(UTC)
    return "before" if parsed < cutoff_utc else "at" if parsed == cutoff_utc else "after"


def date_relation(value: Any, reference: datetime) -> str:
    if not isinstance(value, str):
        return "unknown"
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return "unknown"
    ref = reference.astimezone(UTC).date()
    return "before" if parsed < ref else "at" if parsed == ref else "after"


def build_temporal_facts(evidence: dict[str, Any], cutoff: datetime) -> list[dict[str, Any]]:
    """Compute UTC timestamp relations without asking the model to compare dates."""
    cutoff = cutoff.astimezone(UTC)
    facts: list[dict[str, Any]] = []

    def add(ref: str, field: str, value: Any, *, availability: str | None = None) -> None:
        facts.append({
            "evidence_ref": ref,
            "timestamp_field": field,
            "timestamp": value,
            "relation_to_cutoff": timestamp_relation(value, cutoff),
            **({"availability_at_cutoff": availability} if availability is not None else {}),
        })

    incident = evidence.get("incident") or {}
    incident_ref = f"SYS:incident/{incident.get('incident_id', 'unknown')}:revision/{incident.get('revision') or 0}"
    add(incident_ref, "opened_at", incident.get("opened_at"))
    add(incident_ref, "revision_raised_at", incident.get("revision_raised_at"))

    for item in evidence.get("readings") or []:
        ref = f"SYS:reading/{item.get('reading_id', 'unknown')}"
        event_at, received_at = item.get("event_at"), item.get("received_at")
        add(ref, "event_at", event_at)
        add(ref, "received_at", received_at)
        event, received = parse_timestamp(event_at), parse_timestamp(received_at)
        facts[-1]["availability_at_cutoff"] = (
            "available" if received is not None and received <= cutoff else "unavailable"
        )
        facts[-1]["received_after_event_at"] = (
            "yes" if event is not None and received is not None and received > event
            else "no" if event is not None and received is not None else "unknown"
        )

    for kind, key in (("m3-detection", "detection_id"), ("gap", "gap_revision_id"), ("warning", "warning_id")):
        for item in evidence.get({"m3-detection": "m3_detections", "gap": "gaps", "warning": "warnings"}[kind]) or []:
            ref = f"SYS:{kind}/{item.get(key, 'unknown')}"
            for field in ("raised_at", "first_event_at", "last_event_at", "start_at", "end_at",
                          "interval_start_at", "interval_end_at"):
                if field in item:
                    add(ref, field, item[field])

    observed_times = [
        parsed for item in evidence.get("readings", [])
        if (parsed := parse_timestamp(item.get("event_at"))) is not None
    ]
    latest_reading = max(observed_times, default=None)
    for item in evidence.get("m3_detections") or []:
        last_event = parse_timestamp(item.get("last_event_at"))
        if item.get("last_event_at") is not None:
            facts.append({
                "evidence_ref": f"SYS:m3-detection/{item.get('detection_id', 'unknown')}",
                "timestamp_field": "last_event_at_vs_latest_observed_reading",
                "timestamp": item["last_event_at"],
                "relation_to_cutoff": timestamp_relation(item["last_event_at"], cutoff),
                "latest_observed_event_at": latest_reading.isoformat() if latest_reading else None,
                "relation_to_latest_observed": (
                    "after" if last_event and latest_reading and last_event > latest_reading
                    else "at_or_before" if last_event and latest_reading else "unknown"
                ),
            })

    for item in evidence.get("m4_predictions_advisory_only") or []:
        add(f"SYS:m4-prediction/{item.get('prediction_id', 'unknown')}", "as_of", item.get("as_of"))
    for item in evidence.get("m5_dispositions_available_by_cutoff") or []:
        ref = f"SYS:m5-disposition/{item.get('disposition_id', 'unknown')}"
        add(ref, "decided_at", item.get("decided_at"))
        add(ref, "chain_confirmed_at", item.get("chain_confirmed_at"))

    start, end = evidence.get("sensor_interval_start_at"), evidence.get("sensor_interval_end_at")
    if start is not None and end is not None:
        observed_times = [
            parsed for x in evidence.get("readings", [])
            if (parsed := parse_timestamp(x.get("event_at"))) is not None
        ]
        latest = max(observed_times, default=None)
        end_at = parse_timestamp(end)
        facts.append({
            "evidence_ref": "SYS:evidence/sensor-interval",
            "timestamp_field": "detection_window_end_vs_latest_observed_event_at",
            "timestamp": end,
            "relation_to_cutoff": timestamp_relation(end, cutoff),
            "latest_observed_event_at": latest.isoformat() if latest else None,
            "relation_to_latest_observed": (
                "after" if end_at and latest and end_at > latest
                else "at_or_before" if end_at and latest else "unknown"
            ),
        })
    return facts
