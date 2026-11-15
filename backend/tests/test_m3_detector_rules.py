"""Milestone 3 baseline detector: pure boundary tests from the detector contract §7.

Every test names its contract case (Bnn) and business rule. Series are hand-built because the
synthetic dataset is exactly on the 5-minute grid and never exercises jitter.
"""

import json
from datetime import timedelta
from decimal import Decimal

import pytest

from app.domain.detector import (
    GapBound,
    GapStatus,
    MonitoringStateName,
    TempClass,
    classify,
    estimated_missing_samples,
    monitoring_state,
)
from app.domain.rules import DetectorConfigError, parse_detector_config
from tests.m3_helpers import CONFIG, POLICY, T0, at, run, series


def test_policy_and_config_values_come_from_the_approved_files() -> None:
    assert (POLICY.min_temp_c, POLICY.max_temp_c) == (Decimal("2.0"), Decimal("8.0"))
    assert (POLICY.high_min_duration, POLICY.low_min_duration) == (timedelta(minutes=30), timedelta(minutes=15))
    assert (POLICY.gap_unknown_after, POLICY.gap_review_at) == (timedelta(minutes=15), timedelta(minutes=30))
    assert CONFIG.nominal_interval == timedelta(minutes=5)
    assert CONFIG.max_continuous_interval == timedelta(minutes=7, seconds=30)  # C-01


# ------------------------------------------------------------------ 7.1 classification and duration


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("8.0", TempClass.IN_RANGE),
        ("8.1", TempClass.HIGH),
        ("8.01", TempClass.HIGH),
        ("2.0", TempClass.IN_RANGE),
        ("1.9", TempClass.LOW),
        ("1.99", TempClass.LOW),
    ],
)
def test_b01_b04_br02_limits_are_inclusive_without_tolerance(value: str, expected: TempClass) -> None:
    assert classify(Decimal(value), POLICY) == expected


def test_b02_single_high_reading_is_a_zero_minute_near_miss() -> None:
    snap = run([(at(0), 8.1)])
    assert len(snap.runs) == 1 and snap.runs[0].observed_duration == timedelta(0)
    assert not snap.runs[0].meets_policy_duration


def test_b05_br02_six_readings_span_25_min_no_excursion() -> None:
    r = run(series(0, 6, 9.0)).runs[0]
    assert (r.observed_duration, r.meets_policy_duration, r.reading_count) == (timedelta(minutes=25), False, 6)


def test_b06_br05_seven_readings_span_30_min_excursion_confirmed_at_the_seventh() -> None:
    r = run(series(0, 7, 9.0)).runs[0]
    assert r.meets_policy_duration and r.observed_duration == timedelta(minutes=30)
    assert r.confirmed_event_at == at(30)


def test_b07_br02_run_continues_after_confirmation() -> None:
    r = run(series(0, 8, 9.0)).runs[0]
    assert (r.confirmed_event_at, r.last_event_at, r.run_open) == (at(30), at(35), True)
    closed = run([*series(0, 8, 9.0), (at(40), 5.0)]).runs[0]
    assert closed.run_open is False


def test_b08_b09_br05_low_three_readings_no_four_readings_yes() -> None:
    assert not run(series(0, 3, 1.0)).runs[0].meets_policy_duration
    r = run(series(0, 4, 1.0)).runs[0]
    assert r.meets_policy_duration and r.observed_duration == timedelta(minutes=15) and r.direction == TempClass.LOW


def test_b10_c05_jitter_29m59s_is_not_an_excursion_until_the_next_reading() -> None:
    points = [(at(0, 1), 9.0)] + [(at(5 * i), 9.0) for i in range(1, 7)]
    r = run(points).runs[0]
    assert r.observed_duration == timedelta(minutes=29, seconds=59) and not r.meets_policy_duration
    r8 = run([*points, (at(35), 9.0)]).runs[0]
    assert r8.meets_policy_duration and r8.confirmed_event_at == at(35)


def test_b11_br02_one_in_range_reading_splits_the_run() -> None:
    snap = run([*series(0, 4, 9.0), (at(20), 8.0), *series(25, 5, 9.0)])
    assert [r.observed_duration for r in snap.runs] == [timedelta(minutes=15), timedelta(minutes=20)]
    assert not any(r.meets_policy_duration for r in snap.runs)


def test_b12_br02_direction_change_separates_runs() -> None:
    snap = run([*series(0, 7, 9.0), *series(35, 4, 1.0)])
    assert [(r.direction, r.meets_policy_duration) for r in snap.runs] == [
        (TempClass.HIGH, True),
        (TempClass.LOW, True),
    ]


def test_b41_c05_off_grid_run_of_exactly_30_min_qualifies() -> None:
    r = run([(at(5 * i, 2), 9.0) for i in range(7)]).runs[0]
    assert r.observed_duration == timedelta(minutes=30) and r.meets_policy_duration


def test_b42_c05_low_run_of_14m59_5s_does_not_qualify() -> None:
    r = run([(at(0, 0.5), 1.0), (at(5), 1.0), (at(10), 1.0), (at(15), 1.0)]).runs[0]
    assert r.observed_duration == timedelta(minutes=14, seconds=59.5) and not r.meets_policy_duration


def test_b43_c01_five_readings_7m30s_apart_are_continuous_and_qualify() -> None:
    snap = run([(at(7.5 * i), 9.0) for i in range(5)])
    assert snap.gaps == () and snap.runs[0].reading_count == 5 and snap.runs[0].meets_policy_duration


# ------------------------------------------------------------------ 7.2 continuity tolerance (C-01)


def test_b13_c01_exactly_7m30s_is_continuous() -> None:
    snap = run([(at(0), 9.0), (at(7.5), 9.0)])
    assert snap.gaps == () and len(snap.runs) == 1


def test_b14_c01_7m30_001s_is_a_short_gap_that_splits_the_run() -> None:
    snap = run([(at(0), 9.0), (at(7, 30.001), 9.0)])
    assert len(snap.gaps) == 1 and snap.gaps[0].status == GapStatus.SHORT_GAP
    assert len(snap.runs) == 2 and all(r.gap_adjacent for r in snap.runs)


def test_b16_c01_extra_sample_is_continuous() -> None:
    assert run([(at(0), 5.0), (at(2), 5.0), (at(5), 5.0)]).gaps == ()


def test_b44_c01_only_the_pair_beyond_the_limit_is_split() -> None:
    snap = run([(at(0), 9.0), (at(5), 9.0), (at(12.5), 9.0), (at(20, 0.001), 9.0)])
    assert len(snap.gaps) == 1 and snap.gaps[0].start_at == at(12.5)
    assert [r.reading_count for r in snap.runs] == [3, 1]


def test_b76_detector_config_continuity_limit_must_lie_between_one_and_two_intervals() -> None:
    base = json.loads(json.dumps({"detector_code": "X", "config_version": "1", "nominal_sampling_interval_s": 300}))
    for bad in (300, 600, 0):
        with pytest.raises(DetectorConfigError):
            parse_detector_config({**base, "max_continuous_interval_s": bad}, "h")
    with pytest.raises(DetectorConfigError):
        parse_detector_config({**base, "max_continuous_interval_s": 450.5}, "h")
    assert parse_detector_config({**base, "max_continuous_interval_s": 450}, "h").max_continuous_interval.seconds == 450


# ------------------------------------------------------------------ 7.3 gap span and status (BR-03, BR-04, C-02)


def test_b15_br05_one_missing_reading_splits_a_40_min_run_into_two_warnings_no_excursion() -> None:
    snap = run([*series(0, 4, 9.0), *series(25, 4, 9.0)])
    gap = snap.gaps[0]
    assert (gap.bracketing_span, gap.status, gap.estimated_missing_samples) == (
        timedelta(minutes=10),
        GapStatus.SHORT_GAP,
        1,
    )
    assert [r.observed_duration for r in snap.runs] == [timedelta(minutes=15)] * 2
    assert not any(r.meets_policy_duration for r in snap.runs) and all(r.gap_adjacent for r in snap.runs)


@pytest.mark.parametrize(
    ("span", "status"),
    [
        (timedelta(minutes=15), GapStatus.SHORT_GAP),  # B17
        (timedelta(minutes=15, milliseconds=1), GapStatus.UNKNOWN),  # B18
        (timedelta(minutes=29, seconds=59, milliseconds=999), GapStatus.UNKNOWN),  # B19
        (timedelta(minutes=30), GapStatus.UNKNOWN_REVIEW_REQUIRED),  # B20
    ],
)
def test_b17_b20_br03_br04_bracketing_span_boundaries(span: timedelta, status: GapStatus) -> None:
    snap = run([(T0, 5.0), (T0 + span, 5.0)])
    assert snap.gaps[0].status == status and snap.gaps[0].bracketing_span == span


def test_b45_jittered_29m56s_is_unknown_not_review() -> None:
    gap = run([(at(0, 2), 5.0), (at(29, 58), 5.0)]).gaps[0]
    assert gap.bracketing_span == timedelta(minutes=29, seconds=56)
    assert gap.status == GapStatus.UNKNOWN and gap.estimated_missing_samples == 5


def test_b46_jittered_30m03s_requires_review() -> None:
    gap = run([(at(-0, -2), 5.0), (at(30, 1), 5.0)]).gaps[0]
    assert gap.status == GapStatus.UNKNOWN_REVIEW_REQUIRED and gap.estimated_missing_samples == 5


@pytest.mark.parametrize(
    ("minutes", "expected"), [(7.5, 0), (7.5 + 1 / 60000, 1), (10, 1), (15, 2), (20, 3), (30, 5), (40, 7)]
)
def test_b47_estimated_missing_samples_is_a_separate_measurement(minutes: float, expected: int) -> None:
    span = timedelta(minutes=minutes)
    assert estimated_missing_samples(span, CONFIG) == expected
    if minutes > 7.5:
        gap = run([(T0, 5.0), (T0 + span, 5.0)]).gaps[0]
        # The duration represented by missing samples is not the bracketing span.
        assert gap.estimated_missing_duration == expected * CONFIG.nominal_interval
        assert gap.estimated_missing_duration < gap.bracketing_span


# ------------------------------------------------------------------ 7.4 BR-05 adjacency


def test_b21_br05_qualifying_run_followed_by_long_gap_is_flagged() -> None:
    snap = run([*series(0, 7, 9.0), (at(70), 5.0)])
    assert snap.runs[0].meets_policy_duration and snap.runs[0].followed_by_gap is not None
    assert snap.gaps[0].status == GapStatus.UNKNOWN_REVIEW_REQUIRED and snap.gaps[0].out_of_range_before


def test_b22_br05_short_run_before_long_gap_is_not_an_excursion() -> None:
    snap = run([*series(0, 5, 9.0), (at(60), 5.0)])
    assert not snap.runs[0].meets_policy_duration and snap.runs[0].gap_adjacent


def test_b23_br05_runs_on_both_sides_of_a_gap_are_separate() -> None:
    snap = run([*series(0, 5, 9.0), *series(60, 5, 9.0)])
    assert len(snap.runs) == 2 and not any(r.meets_policy_duration for r in snap.runs)
    assert snap.runs[0].followed_by_gap == snap.runs[1].preceded_by_gap == snap.gaps[0].key


def test_b24_br05_qualifying_run_starting_at_the_closing_reading_is_flagged() -> None:
    snap = run([(at(0), 5.0), *series(40, 7, 9.0)])
    assert snap.runs[0].meets_policy_duration and snap.runs[0].preceded_by_gap == snap.gaps[0].key


def test_b25_br05_run_ending_one_reading_before_the_gap_is_not_adjacent() -> None:
    snap = run([*series(0, 5, 9.0), (at(25), 7.5), (at(65), 5.0)])
    assert not snap.runs[0].gap_adjacent


def test_b26_br05_short_gaps_also_flag_adjacent_runs() -> None:
    snap = run([*series(0, 7, 9.0), (at(40), 5.0)])
    assert snap.gaps[0].status == GapStatus.SHORT_GAP and snap.runs[0].followed_by_gap is not None


# ------------------------------------------------------------------ 7.5 monitoring states (C-02, C-06)


@pytest.mark.parametrize(
    ("age", "state", "review"),
    [
        (timedelta(minutes=7, seconds=30), MonitoringStateName.CURRENT, False),
        (timedelta(minutes=7, seconds=30, milliseconds=1), MonitoringStateName.STALE, False),
        (timedelta(minutes=15), MonitoringStateName.STALE, False),
        (timedelta(minutes=15, milliseconds=1), MonitoringStateName.UNKNOWN, False),
        (timedelta(minutes=45), MonitoringStateName.UNKNOWN, True),
        (timedelta(minutes=-3), MonitoringStateName.CURRENT, False),  # allowed future skew
    ],
)
def test_b48_c02_monitoring_state_thresholds(age: timedelta, state: MonitoringStateName, review: bool) -> None:
    st = monitoring_state(
        newest_event_at=T0, assigned_from=at(-60), assigned_to=None, as_of=T0 + age, policy=POLICY, config=CONFIG
    )
    assert (st.state, st.provisional_review_threshold_reached) == (state, review)


def test_b27_b48_stale_telemetry_creates_no_gap_until_bounded() -> None:
    """A trailing silence is never a confirmed gap while the end boundary is not established."""
    snap = run([*series(0, 3, 9.0)], start=at(0), end=None)
    assert snap.gaps == () and snap.runs[0].run_open


def test_monitoring_not_started_and_ended() -> None:
    assert (
        monitoring_state(
            newest_event_at=None, assigned_from=at(10), assigned_to=None, as_of=at(0), policy=POLICY, config=CONFIG
        ).state
        == MonitoringStateName.NOT_STARTED
    )
    assert (
        monitoring_state(
            newest_event_at=at(5), assigned_from=at(0), assigned_to=at(10), as_of=at(10), policy=POLICY, config=CONFIG
        ).state
        == MonitoringStateName.ENDED
    )


# ------------------------------------------------------------------ 7.12 monitoring boundaries (C-04)


@pytest.mark.parametrize(("first_min", "status"), [(20, GapStatus.UNKNOWN), (30, GapStatus.UNKNOWN_REVIEW_REQUIRED)])
def test_b70_c04_leading_gap_from_documented_start(first_min: int, status: GapStatus) -> None:
    gap = run([(at(first_min), 5.0)], start=at(0)).gaps[0]
    assert (gap.start_bound, gap.end_bound, gap.status) == (GapBound.MONITORING_START, GapBound.READING, status)


def test_b71_c04_first_reading_7m30s_after_start_is_no_gap() -> None:
    assert run([(at(7.5), 5.0)], start=at(0)).gaps == ()


def test_b37_c04_no_readings_with_both_boundaries_is_one_gap() -> None:
    gap = run([], start=at(0), end=at(120)).gaps[0]
    assert (gap.start_bound, gap.end_bound, gap.status) == (
        GapBound.MONITORING_START,
        GapBound.MONITORING_END,
        GapStatus.UNKNOWN_REVIEW_REQUIRED,
    )


def test_b72_b74_c04_without_end_boundary_nothing_is_confirmed_and_state_is_unknown() -> None:
    assert run([], start=at(0), end=None).gaps == ()
    st = monitoring_state(
        newest_event_at=None, assigned_from=at(0), assigned_to=None, as_of=at(120), policy=POLICY, config=CONFIG
    )
    assert st.state == MonitoringStateName.UNKNOWN and st.unobserved_since_at == at(0)
    st2 = monitoring_state(
        newest_event_at=at(0), assigned_from=at(0), assigned_to=None, as_of=at(120), policy=POLICY, config=CONFIG
    )
    assert st2.state == MonitoringStateName.UNKNOWN


def test_b73_c04_trailing_gap_to_documented_end() -> None:
    snap = run([*series(0, 3, 5.0)], start=at(0), end=at(50))
    gap = snap.gaps[0]
    assert (gap.start_at, gap.end_bound, gap.bracketing_span, gap.status) == (
        at(10),
        GapBound.MONITORING_END,
        timedelta(minutes=40),
        GapStatus.UNKNOWN_REVIEW_REQUIRED,
    )
