"""Journey-level splits: reproducible, stratified, no leakage (DATA-05, DATA-06, ML-09)."""

from collections import Counter
from datetime import UTC, datetime, timedelta

import pytest
from conftest import Data

from coldchain_sim.config import AMBIENT_PROFILES, PARTITIONS, PRIMARY_SCENARIOS
from coldchain_sim.splits import LeakageError, assign_partitions, check_no_leakage

FRACTIONS = {"train": 0.70, "validation": 0.15, "test": 0.15}


def _journeys(data: Data) -> list[tuple[str, str, str]]:
    return [(j["journey_id"], j["primary_scenario"], j["ambient_profile"]) for j in data.journeys]


def test_split_file_is_reproducible_from_the_seed(full: Data) -> None:
    again = assign_partitions(_journeys(full), FRACTIONS, full.manifest["split_seed"])
    assert again == {r["journey_id"]: r["partition"] for r in full.split}


def test_a_different_split_seed_gives_a_different_assignment(full: Data) -> None:
    a = assign_partitions(_journeys(full), FRACTIONS, 11)
    b = assign_partitions(_journeys(full), FRACTIONS, 12)
    assert a != b
    assert Counter(a.values()) == Counter(b.values())


def test_every_journey_is_in_exactly_one_partition(full: Data) -> None:
    check_no_leakage(full.split, [j["journey_id"] for j in full.journeys])
    parts = {p: {r["journey_id"] for r in full.split if r["partition"] == p} for p in PARTITIONS}
    assert not parts["train"] & parts["validation"]
    assert not parts["train"] & parts["test"]
    assert not parts["validation"] & parts["test"]


def test_partition_sizes_follow_70_15_15(full: Data) -> None:
    counts = Counter(r["partition"] for r in full.split)
    assert abs(counts["train"] - 140) <= 2
    assert abs(counts["validation"] - 30) <= 2
    assert abs(counts["test"] - 30) <= 2


def test_data06_every_ambient_profile_and_scenario_is_in_every_partition(full: Data) -> None:
    part = {r["journey_id"]: r["partition"] for r in full.split}
    for p in PARTITIONS:
        members = [j for j in full.journeys if part[j["journey_id"]] == p]
        assert {j["ambient_profile"] for j in members} == set(AMBIENT_PROFILES), p
        assert {j["primary_scenario"] for j in members} == set(PRIMARY_SCENARIOS), p


def test_overlapping_windows_of_one_journey_never_cross_partitions(full: Data) -> None:
    """Cut 60-minute windows with a 5-minute stride (the planned M4 windowing) and check partitions."""
    part = {r["journey_id"]: r["partition"] for r in full.split}
    window_partitions: dict[str, set[str]] = {}
    start = {s["shipment_id"]: datetime.fromisoformat(s["departure_at"][:-1]).replace(tzinfo=UTC)
             for s in full.shipments}
    for r in full.readings:
        at = datetime.fromisoformat(r["event_at"][:-1]).replace(tzinfo=UTC)
        offset = int((at - start[r["shipment_id"]]) / timedelta(minutes=5))
        for w in range(max(0, offset - 11), offset + 1):  # every window that contains this reading
            window_partitions.setdefault(f"{r['shipment_id']}#{w}", set()).add(part[r["shipment_id"]])
    assert all(len(p) == 1 for p in window_partitions.values())


def test_leakage_check_detects_duplicates_and_omissions() -> None:
    with pytest.raises(LeakageError):
        check_no_leakage([{"journey_id": "J1", "partition": "train"},
                          {"journey_id": "J1", "partition": "test"}], ["J1"])
    with pytest.raises(LeakageError):
        check_no_leakage([{"journey_id": "J1", "partition": "train"}], ["J1", "J2"])
    with pytest.raises(LeakageError):
        check_no_leakage([{"journey_id": "J1", "partition": "holdout"}], ["J1"])
