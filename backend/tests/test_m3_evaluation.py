"""Milestone 3 offline baseline evaluation: protocol guards (D-13), deterministic matching (U-06), delay."""

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.evaluation.baseline import EvaluationRefused, check_protocol, run_baseline_evaluation
from app.evaluation.matching import Interval, match_one_to_one

T = datetime(2026, 9, 1, tzinfo=UTC)
REPO_DIR = Path(os.environ.get("COLDCHAIN_REPO_DIR", Path(__file__).resolve().parents[2]))
CANONICAL = REPO_DIR / "data/release/coldchain-sim-v1.0.0-seed11"
APP_DIR = Path(__file__).resolve().parents[1] / "app"


def iv(
    item: str, start: float, end: float, kind: str = "HIGH", journey: str = "J1", raised: float | None = None
) -> Interval:
    return Interval(
        item,
        journey,
        kind,
        T + timedelta(minutes=start),
        T + timedelta(minutes=end),
        T + timedelta(minutes=raised) if raised is not None else None,
    )


@pytest.mark.parametrize("seed", [22, 33, 44, 55, 66])
def test_d13_reserved_final_evaluation_seeds_are_refused(seed: int) -> None:
    with pytest.raises(EvaluationRefused, match="reserved"):
        check_protocol({"seed": seed}, ("train", "validation"))


def test_d13_test_partition_is_refused_for_development_measurements() -> None:
    with pytest.raises(EvaluationRefused):
        check_protocol({"seed": 11}, ("train", "test"))
    check_protocol({"seed": 11}, ("validation",))


def test_u06_matching_requires_same_journey_type_and_overlap() -> None:
    dets = [iv("D1", 0, 30), iv("D2", 0, 30, kind="LOW"), iv("D3", 0, 30, journey="J2"), iv("D4", 100, 130)]
    refs = [iv("R1", 10, 40)]
    assert match_one_to_one(dets, refs) == [("D1", "R1")]


def test_u06_closed_detection_touching_half_open_reference_start_matches_but_not_its_end() -> None:
    assert match_one_to_one([iv("D", 0, 10)], [iv("R", 10, 20)]) == [("D", "R")]  # reading at reference start
    assert match_one_to_one([iv("D", 20, 30)], [iv("R", 10, 20)]) == []  # reference end is exclusive


def test_u06_one_to_one_with_largest_overlap_first() -> None:
    dets = [iv("D-small", 0, 5, raised=1), iv("D-big", 0, 40, raised=50)]
    refs = [iv("R", 0, 30)]
    assert match_one_to_one(dets, refs) == [("D-big", "R")]  # D-small becomes a false alarm


def test_u06_tie_breaks_are_deterministic_and_independent_of_input_order() -> None:
    # Same overlap and start distance: earlier raised_at wins; then detection id; then reference id.
    dets = [iv("D-b", 0, 10, raised=5), iv("D-a", 0, 10, raised=9)]
    refs = [iv("R", 0, 10)]
    assert match_one_to_one(dets, refs) == match_one_to_one(list(reversed(dets)), refs) == [("D-b", "R")]
    same_time = [iv("D-b", 0, 10, raised=5), iv("D-a", 0, 10, raised=5)]
    assert match_one_to_one(same_time, refs) == [("D-a", "R")]
    two_refs = [iv("R-2", 0, 10), iv("R-1", 0, 10)]
    assert match_one_to_one([iv("D", 0, 10, raised=1)], two_refs) == [("D", "R-1")]


def test_b64_c10_evaluation_code_has_no_database_access() -> None:
    for path in (APP_DIR / "evaluation").glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "app.db" not in text and "sqlalchemy" not in text, path.name


def test_b79_b80_development_run_on_the_validation_partition(tmp_path: Path) -> None:
    out = tmp_path / "run"
    result = run_baseline_evaluation(
        CANONICAL,
        APP_DIR / "seed/data/policies/POL-CHILL-01_v1.0.json",
        APP_DIR / "seed/data/detector/DET-BASELINE_v1.0.0.json",
        out,
        partitions=("validation",),
    )
    s = result["summary"]["excursion_detection"]
    assert result["run_config"]["partitions"] == ["validation"] and result["run_config"]["tuned_parameters"] == "none"
    assert s["matched"] <= min(s["reference_events"], s["detections_raised"])
    assert s["false_alarms"] == s["detections_raised"] - s["matched"]
    delay = result["summary"]["detection_delay_min"]
    assert delay["missed_events_without_delay"] == s["reference_events"] - s["matched"]
    assert delay["event_time_delay_Ea_minus_T0"].get("n", 0) == s["matched"]
    assert {p.name for p in out.iterdir()} == {
        "run_config.json",
        "summary.json",
        "matches.csv",
        "detections.csv",
        "missing_data_intervals.csv",
    }
    again = run_baseline_evaluation(
        CANONICAL,
        APP_DIR / "seed/data/policies/POL-CHILL-01_v1.0.json",
        APP_DIR / "seed/data/detector/DET-BASELINE_v1.0.0.json",
        tmp_path / "again",
        partitions=("validation",),
    )
    assert json.dumps(again["summary"], sort_keys=True, default=str) == json.dumps(
        result["summary"], sort_keys=True, default=str
    )
    assert (out / "matches.csv").read_bytes() == (tmp_path / "again" / "matches.csv").read_bytes()
