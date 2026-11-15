"""Missing readings vs delayed readings (BR-03, BR-04, FR-03, FR-04 data side, DEMO-01 data)."""

from collections import defaultdict
from datetime import UTC, datetime

from conftest import POLICY_FILE, Data

from coldchain_sim.policy import GAP_UNKNOWN, GAP_UNKNOWN_REVIEW, classify_gap, load_policy

POLICY = load_policy(POLICY_FILE, "policy")


def ts(value: str) -> datetime:
    return datetime.fromisoformat(value[:-1]).replace(tzinfo=UTC)


def test_br04_missing_readings_are_absent_and_never_filled(full: Data) -> None:
    delivered = {(r["shipment_id"], r["event_at"]) for r in full.readings}
    context = {(c["shipment_id"], c["event_at"]) for c in full.context}
    missing = [s for s in full.slots if s["observation_status"] == "MISSING"]
    assert missing
    for s in missing:
        key = (s["journey_id"], s["slot_at"])
        assert key not in delivered and key not in context
        assert s["transmission"] == "" and s["delay_s"] == ""
    assert len(delivered) + len(missing) == len(full.slots)


def test_br03_missing_data_events_match_the_gaps_between_received_readings(full: Data) -> None:
    by_ship: dict[str, list[datetime]] = defaultdict(list)
    for r in full.readings:
        by_ship[r["shipment_id"]].append(ts(r["event_at"]))
    arrival = {s["shipment_id"]: ts(s["arrival_at"]) for s in full.shipments}
    gaps = set()
    for ship, times in by_ship.items():
        times.sort()
        for a, b in zip(times, times[1:], strict=False):
            if (b - a).total_seconds() > 300:
                gaps.add((ship, a, b))
        if times[-1] < arrival[ship]:
            gaps.add((ship, times[-1], arrival[ship]))
    events = {}
    for e in full.events:
        if e["event_type"] == "MISSING_DATA":
            events[(e["journey_id"], ts(e["start_at"]), ts(e["end_at"]))] = e
    assert set(events) == gaps
    for (_ship, a, b), e in events.items():
        gap_min = (b - a).total_seconds() / 60
        assert e["attributes"]["observed_gap_min"] == gap_min
        assert e["attributes"]["policy_gap_status"] == classify_gap(gap_min, POLICY)


def test_all_gap_classes_are_present(full: Data) -> None:
    statuses = {e["attributes"]["policy_gap_status"] for e in full.events if e["event_type"] == "MISSING_DATA"}
    assert statuses == {"SHORT_GAP", GAP_UNKNOWN, GAP_UNKNOWN_REVIEW}


def test_eval13_dataset_contains_excursions_hidden_by_missing_data(full: Data) -> None:
    """Absent data can hide real risk: some UNKNOWN gaps overlap a true policy excursion."""
    hidden = [e for e in full.events if e["event_type"] == "MISSING_DATA"
              and e["attributes"]["overlaps_policy_excursion"]
              and e["attributes"]["policy_gap_status"] != "SHORT_GAP"]
    assert hidden


def test_fr03_ocean_gap_readings_keep_their_original_event_time(full: Data) -> None:
    outages = [e for e in full.events if e["event_type"] == "TRANSMISSION_DELAY"
               and e["cause"] == "OCEAN_COVERAGE_GAP"]
    assert len(outages) == sum(1 for j in full.journeys if j["primary_scenario"] == "OCEAN_COVERAGE_GAP")
    for e in outages:
        a = e["attributes"]
        members = [r for r in full.readings if r["upload_id"] == a["upload_id"]]
        assert len(members) == a["buffered_readings"] > 0
        outage_min = a["outage_end_min"] - a["outage_start_min"]
        assert outage_min >= 4 * 60 - 1
        for r in members:
            slot = full.slot_index[(r["shipment_id"], r["event_at"])]  # event_at is the original sample time
            assert slot["observation_status"] == "OBSERVED"
            assert slot["transmission"] == "BUFFERED_COVERAGE_GAP"
            assert r["received_at"] == a["upload_received_at"]
            assert ts(r["received_at"]) >= ts(e["end_at"])
        oldest = min(ts(r["event_at"]) for r in members)
        delay_min = (ts(a["upload_received_at"]) - oldest).total_seconds() / 60
        # received_at is later than event_at by at least the outage length
        assert delay_min >= outage_min
        assert abs(delay_min - a["max_delay_min"]) < 0.01


def test_delayed_and_missing_readings_are_disjoint(full: Data) -> None:
    for s in full.slots:
        if s["transmission"] in ("BUFFERED_COVERAGE_GAP", "RETRIED"):
            assert s["observation_status"] == "OBSERVED"
            assert int(s["delay_s"]) > 0


def test_retried_readings_arrive_after_the_failed_upload_with_original_event_time(full: Data) -> None:
    retries = [e for e in full.events if e["event_type"] == "TRANSMISSION_DELAY" and e["cause"] == "UPLOAD_RETRY"]
    assert retries
    by_upload: dict[str, list[dict[str, str]]] = defaultdict(list)
    for r in full.readings:
        by_upload[r["upload_id"]].append(r)
    for e in retries:
        failed_at = ts(e["start_at"])
        delayed = [r for r in by_upload[e["attributes"]["upload_id"]] if ts(r["event_at"]) <= failed_at]
        assert len(delayed) == e["attributes"]["delayed_readings"] > 0
        for r in delayed:
            assert ts(r["received_at"]) >= ts(e["end_at"]) > failed_at
            # a failure just before an ocean outage hands the readings to the restore upload
            assert full.slot_index[(r["shipment_id"], r["event_at"])]["transmission"] in (
                "RETRIED", "BUFFERED_COVERAGE_GAP")


def test_hidden_excursion_inside_an_ocean_gap_is_revealed_after_upload(full: Data) -> None:
    """DEMO-01 data: a policy excursion whose readings all arrived in the buffered upload."""
    found = [e for e in full.events if e["event_type"] == "EXCURSION_HIGH"
             and e["attributes"]["delayed_readings_in_interval"] > 0
             and full.journey_by_id[e["journey_id"]]["primary_scenario"] == "OCEAN_COVERAGE_GAP"]
    assert found
