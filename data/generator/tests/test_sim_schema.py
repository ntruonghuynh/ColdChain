"""Field completeness, types, units, timestamps and uniqueness (DATA-01, DATA-02, NFR-05, NFR-06, SC-02)."""

import re
from collections import Counter
from datetime import UTC, datetime, timedelta

from conftest import CONFIG, Data

from coldchain_sim.config import AMBIENT_PROFILES, PRIMARY_SCENARIOS, largest_remainder, load_config
from coldchain_sim.dataset import CONTEXT_COLUMNS, READING_COLUMNS, SHIPMENT_COLUMNS, UPLOAD_COLUMNS

UTC_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def ts(value: str) -> datetime:
    assert UTC_PATTERN.match(value), value
    return datetime.fromisoformat(value[:-1]).replace(tzinfo=UTC)


def test_data01_readings_have_every_required_field(full: Data) -> None:
    assert list(full.readings[0]) == list(READING_COLUMNS)
    for row in full.readings:
        for col in ("shipment_id", "sensor_id", "event_at", "received_at", "temperature_c", "upload_id"):
            assert row[col] != "", (col, row)
        assert -40.0 <= float(row["temperature_c"]) <= 60.0


def test_data02_context_has_required_fields_and_null_only_means_not_reported(full: Data) -> None:
    assert list(full.context[0]) == list(CONTEXT_COLUMNS)
    probe = {j["shipment_id"]: j["has_ambient_probe"] == "1" for j in full.journeys}
    for row in full.context:
        assert row["door_state"] in ("OPEN", "CLOSED")
        assert 0.0 <= float(row["battery_level_pct"]) <= 100.0
        # ambient is empty exactly when the logger has no ambient probe (never a default value)
        assert (row["ambient_temperature_c"] == "") == (not probe[row["shipment_id"]])


def test_observed_files_have_the_documented_columns(full: Data) -> None:
    assert list(full.shipments[0]) == list(SHIPMENT_COLUMNS)
    assert list(full.uploads[0]) == list(UPLOAD_COLUMNS)


def test_sc02_at_least_200_journeys_with_every_scenario_and_ambient_profile(full: Data) -> None:
    assert len(full.shipments) == len(full.journeys) == 200
    scen = Counter(j["primary_scenario"] for j in full.journeys)
    expected = largest_remainder(200, load_config(CONFIG).raw["scenario_mix"])
    assert dict(scen) == {k: v for k, v in expected.items() if v}
    assert set(scen) == set(PRIMARY_SCENARIOS)
    assert {j["ambient_profile"] for j in full.journeys} == set(AMBIENT_PROFILES)
    for s in PRIMARY_SCENARIOS:  # different ambient conditions inside every scenario
        assert len({j["ambient_profile"] for j in full.journeys if j["primary_scenario"] == s}) >= 3


def test_journey_ids_shipments_and_sensors_are_unique_and_one_to_one(full: Data) -> None:
    ship = [s["shipment_id"] for s in full.shipments]
    sens = [s["sensor_id"] for s in full.shipments]
    assert len(set(ship)) == len(ship) and len(set(sens)) == len(sens)
    sensor_of = dict(zip(ship, sens, strict=True))
    for row in full.readings:
        assert sensor_of[row["shipment_id"]] == row["sensor_id"]


def test_reading_keys_are_unique_and_match_context(full: Data) -> None:
    keys = [(r["sensor_id"], r["event_at"]) for r in full.readings]
    assert len(keys) == len(set(keys))
    assert keys == [(c["sensor_id"], c["event_at"]) for c in full.context]


def test_nfr05_timestamps_are_utc_inside_the_journey_and_on_the_sampling_grid(full: Data) -> None:
    window = {s["shipment_id"]: (ts(s["departure_at"]), ts(s["arrival_at"])) for s in full.shipments}
    for dep, arr in window.values():
        assert timedelta(hours=24) <= arr - dep <= timedelta(hours=72)
    for row in full.readings:
        event_at, received_at = ts(row["event_at"]), ts(row["received_at"])
        dep, arr = window[row["shipment_id"]]
        assert dep <= event_at <= arr
        assert (event_at - dep) % timedelta(minutes=5) == timedelta(0)
        assert received_at >= event_at


def test_uploads_are_consistent_with_their_readings(full: Data) -> None:
    by_upload: dict[str, list[dict[str, str]]] = {}
    for r in full.readings:
        by_upload.setdefault(r["upload_id"], []).append(r)
    assert set(by_upload) == {u["upload_id"] for u in full.uploads}
    for u in full.uploads:
        members = by_upload[u["upload_id"]]
        assert int(u["reading_count"]) == len(members)
        assert {m["received_at"] for m in members} == {u["received_at"]}
        assert min(m["event_at"] for m in members) == u["first_event_at"]
        assert max(m["event_at"] for m in members) == u["last_event_at"]


def test_dataset_is_marked_synthetic_everywhere(full: Data) -> None:
    assert full.manifest["synthetic"] is True
    assert {s["data_origin"] for s in full.shipments} == {"SIMULATED"}
    assert {s["dataset_id"] for s in full.shipments} == {full.manifest["dataset_id"]}
    assert "SYNTHETIC" in (full.path / "README.md").read_text()
    assert all(s["origin"].startswith("Simulated site") for s in full.shipments)


def test_manifest_row_counts_match_the_files(full: Data) -> None:
    counts = {f["path"]: f["rows"] for f in full.manifest["files"]}
    assert counts["observed/readings.csv.gz"] == len(full.readings)
    assert counts["observed/context.csv.gz"] == len(full.context)
    assert counts["ground_truth/slots.csv.gz"] == len(full.slots)
    assert counts["ground_truth/events.csv.gz"] == len(full.events)
