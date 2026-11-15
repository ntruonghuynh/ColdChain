"""Sensor spikes, bias and drift change observations, not the product (FR-14 data side, DATA-04)."""

from datetime import UTC, datetime, timedelta

from conftest import Data


def ts(value: str) -> datetime:
    return datetime.fromisoformat(value[:-1]).replace(tzinfo=UTC)


def test_spikes_change_only_the_observation(full: Data) -> None:
    spikes = [e for e in full.events if e["event_type"] == "SENSOR_SPIKE"]
    assert len(spikes) >= 20
    for e in spikes:
        start, end = ts(e["start_at"]), ts(e["end_at"])
        at = start
        values = []
        while at < end:
            s = full.slot_index[(e["journey_id"], at.strftime("%Y-%m-%dT%H:%M:%SZ"))]
            spike = float(s["sensor_spike_c"])
            assert abs(spike) >= 4.0
            values.append(spike)
            at += timedelta(minutes=5)
        assert [round(v, 3) for v in values] == e["attributes"]["spike_c"]
        assert len(values) in (1, 2)  # isolated: one or two consecutive readings


def test_spike_readings_deviate_while_neighbours_track_the_truth(full: Data) -> None:
    observed = {(r["shipment_id"], r["event_at"]): float(r["temperature_c"]) for r in full.readings}
    for e in full.events:
        if e["event_type"] != "SENSOR_SPIKE" or not e["attributes"]["delivered"]:
            continue
        key = (e["journey_id"], e["start_at"])
        slot = full.slot_index[key]
        assert abs(observed[key] - float(slot["true_product_temperature_c"])) > 3.0
        before = (ts(e["start_at"]) - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        prev = full.slot_index[(e["journey_id"], before)]
        if (e["journey_id"], before) in observed:
            err = observed[(e["journey_id"], before)] - float(prev["true_product_temperature_c"])
            assert abs(err - float(prev["sensor_offset_c"])) < 1.0


def test_sensor_bias_shifts_every_reading_by_a_constant(full: Data) -> None:
    biased = [e for e in full.events if e["event_type"] == "SENSOR_BIAS"]
    assert biased
    observed = {(r["shipment_id"], r["event_at"]): float(r["temperature_c"]) for r in full.readings}
    for e in biased:
        bias = e["attributes"]["bias_c"]
        assert abs(bias) >= 0.5
        drift_start = full.journey_by_id[e["journey_id"]]["sensor_drift_start_at"] or "9999"
        rows = [s for s in full.slots if s["journey_id"] == e["journey_id"] and s["slot_at"] <= drift_start]
        assert all(abs(float(s["sensor_offset_c"]) - bias) < 1e-3 for s in rows)
        errors = [observed[(s["journey_id"], s["slot_at"])] - float(s["true_product_temperature_c"])
                  - float(s["sensor_spike_c"]) for s in rows if (s["journey_id"], s["slot_at"]) in observed]
        assert abs(sum(errors) / len(errors) - bias) < 0.05


def test_sensor_drift_grows_linearly_to_the_documented_offset(full: Data) -> None:
    drifts = [e for e in full.events if e["event_type"] == "SENSOR_DRIFT"]
    assert drifts
    for e in drifts:
        rows = [s for s in full.slots if s["journey_id"] == e["journey_id"] and s["slot_at"] >= e["start_at"]]
        offsets = [float(s["sensor_offset_c"]) for s in rows]
        rate = e["attributes"]["drift_c_per_day"]
        assert all((b - a) * rate >= -1e-3 for a, b in zip(offsets, offsets[1:], strict=False))
        assert abs(offsets[-1] - e["attributes"]["offset_at_arrival_c"]) < 2e-3


def test_physical_temperature_is_normal_in_sensor_fault_journeys(full: Data) -> None:
    for j in full.journeys:
        if j["primary_scenario"] in ("SENSOR_SPIKE", "SENSOR_BIAS_DRIFT"):
            assert int(j["true_minutes_above_max"]) == 0
            assert int(j["true_minutes_below_min"]) == 0
