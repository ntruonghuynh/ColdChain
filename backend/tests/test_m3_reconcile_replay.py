"""Milestone 3: append-only reconciliation and causal evaluation (pure; contract §5.10-§5.12, §7.7, §7.11)."""

import itertools
from dataclasses import replace
from datetime import datetime

from app.domain.detector import Obs
from app.domain.reconcile import IncidentBasis, IncidentCategoryName, WarningKind
from app.domain.replay import SensorEvaluator, StepKind, build_timeline
from tests.m3_helpers import CONFIG, POLICY, at, obs, series


def evaluator(start: datetime | None = None, end: datetime | None = None) -> SensorEvaluator:
    return SensorEvaluator(
        shipment_id="SHP",
        sensor_id="SNS",
        mode="TEST",
        policy=POLICY,
        config=CONFIG,
        assigned_from=start,
        assigned_to=end,
    )


def batch(points: list[tuple[datetime, float]], received_at: datetime) -> list[Obs]:
    return obs(points, received_at)


def incidents(ev: SensorEvaluator, category: IncidentCategoryName) -> list:
    return sorted((i for i in ev.state.incidents.values() if i.category == category), key=lambda i: i.business_ref)


def current(ev: SensorEvaluator) -> tuple:
    """Final current results in event time, without history.

    Identity keys and receipt-time fields (``evidence_received_at``, ``raised_at``) depend on the
    arrival history by design and are excluded (contract §5.10).
    """
    return (
        sorted((k, g.gap) for k, g in ev.state.gaps.items()),
        sorted((r.run.first_event_at, replace(r.run, evidence_received_at=None)) for r in ev.state.runs.values()),
        sorted(
            (w.spec.kind, w.spec.gap_key, w.spec.interval_start_at, w.spec.interval_end_at, w.spec.message)
            for w in ev.state.warnings.values()
        ),
        sorted(
            (i.category, i.values.extent_start_at, i.values.extent_end_at, i.values.basis)
            for i in ev.state.incidents.values()
        ),
    )


def test_b53_c07_same_inputs_give_a_noop_evaluation() -> None:
    ev = evaluator()
    ev.add(batch(series(0, 8, 9.0), at(40)))
    assert ev.evaluate(at(40), "BATCH") is not None
    assert ev.evaluate(at(41), "BATCH") is None  # nothing new: no evaluation, no rows


def test_b65_c09_readings_received_after_as_of_are_invisible() -> None:
    ev = evaluator()
    ev.add(batch(series(0, 4, 9.0), at(20)))
    ev.add(batch(series(20, 4, 9.0), at(60)))  # stored, but received later
    out = ev.evaluate(at(30), "BATCH")
    assert out is not None and out.visible_reading_count == 4
    assert not any(r.run.meets_policy_duration for r in ev.state.runs.values())


def test_b29_br09_backfill_supersedes_gap_and_keeps_data_gap_incident_open() -> None:
    ev = evaluator()
    ev.add(batch(series(0, 3, 5.0), at(10)))
    ev.add(batch(series(50, 2, 5.0), at(55)))
    ev.evaluate(at(55), "BATCH")
    [gap_inc] = incidents(ev, IncidentCategoryName.DATA_GAP)
    assert gap_inc.values.basis == IncidentBasis.CURRENT and gap_inc.status == "OPEN"
    ev.add(batch(series(15, 7, 5.0), at(70)))  # the missing readings arrive late
    out = ev.evaluate(at(70), "BATCH")
    assert out is not None and len(out.changes.superseded_gaps) == 1 and not ev.state.gaps
    [gap_inc] = incidents(ev, IncidentCategoryName.DATA_GAP)
    assert gap_inc.values.basis == IncidentBasis.SUPERSEDED_BY_DATA and gap_inc.revision == 2
    assert gap_inc.status == "OPEN"  # never closed by the detector


def test_b30_br05_backfill_merges_two_short_runs_into_an_excursion() -> None:
    ev = evaluator()
    ev.add(batch([*series(0, 3, 9.0), *series(30, 3, 9.0)], at(45)))
    ev.evaluate(at(45), "BATCH")
    assert not incidents(ev, IncidentCategoryName.TEMPERATURE_EXCURSION)
    assert sum(1 for w in ev.state.warnings.values() if w.spec.kind == WarningKind.GAP_ADJACENT_OUT_OF_RANGE) == 2
    ev.add(batch(series(15, 3, 9.0), at(60)))
    ev.evaluate(at(60), "BATCH")
    [tex] = incidents(ev, IncidentCategoryName.TEMPERATURE_EXCURSION)
    assert tex.values.extent_start_at == at(0) and tex.values.extent_end_at == at(40)
    assert not any(w.spec.kind == WarningKind.GAP_ADJACENT_OUT_OF_RANGE for w in ev.state.warnings.values())


def test_b31_c08_backfill_merging_two_incidents_keeps_both_open() -> None:
    ev = evaluator()
    ev.add(batch([*series(0, 7, 9.0), *series(45, 7, 9.0)], at(80)))
    ev.evaluate(at(80), "BATCH")
    assert len(incidents(ev, IncidentCategoryName.TEMPERATURE_EXCURSION)) == 2
    ev.add(batch(series(35, 2, 9.0), at(90)))
    ev.evaluate(at(90), "BATCH")
    first, second = sorted(incidents(ev, IncidentCategoryName.TEMPERATURE_EXCURSION), key=lambda i: i.opened_at)
    assert first.values.basis == IncidentBasis.CURRENT and first.values.extent_end_at == at(75)
    assert second.values.basis == IncidentBasis.MERGED_INTO and second.values.merged_into_ref == first.business_ref
    assert first.status == second.status == "OPEN"


def test_b61_c08_backfill_that_splits_a_run_below_threshold_supersedes_without_deleting() -> None:
    ev = evaluator()
    ev.add(batch([(at(0), 9.0), (at(7), 9.0), (at(14), 9.0), (at(21), 9.0), (at(28), 9.0), (at(35), 9.0)], at(40)))
    ev.evaluate(at(40), "BATCH")
    [tex] = incidents(ev, IncidentCategoryName.TEMPERATURE_EXCURSION)
    ev.add(batch([(at(17), 5.0)], at(50)))  # an in-range reading arrives late inside the run
    ev.evaluate(at(50), "BATCH")
    [tex2] = incidents(ev, IncidentCategoryName.TEMPERATURE_EXCURSION)
    assert tex2.business_ref == tex.business_ref and tex2.revision == 2
    assert tex2.values.basis == IncidentBasis.SUPERSEDED_BY_DATA and tex2.status == "OPEN"


def test_b52_out_of_order_batches_supersede_then_converge() -> None:
    ev = evaluator()
    ev.add(batch([(at(0), 5.0)], at(1)))
    ev.evaluate(at(1), "BATCH")
    ev.add(batch(series(30, 4, 5.0), at(60)))  # batch B (later events) arrives first
    ev.evaluate(at(60), "BATCH")
    assert [i.values.basis for i in incidents(ev, IncidentCategoryName.DATA_GAP)] == [IncidentBasis.CURRENT]
    ev.add(batch(series(5, 5, 5.0), at(65)))  # batch A fills the gap
    ev.evaluate(at(65), "BATCH")
    assert [i.values.basis for i in incidents(ev, IncidentCategoryName.DATA_GAP)] == [IncidentBasis.SUPERSEDED_BY_DATA]
    in_order = evaluator()
    in_order.add(batch([(at(0), 5.0)], at(1)))
    in_order.add(batch(series(5, 5, 5.0), at(30)))
    in_order.add(batch(series(30, 4, 5.0), at(50)))
    for t in (at(1), at(30), at(50)):
        in_order.evaluate(t, "BATCH")
    assert current(ev)[:3] == current(in_order)[:3]  # same gaps, runs and warnings; only history differs


def test_b33_c07_any_arrival_order_gives_the_same_final_results() -> None:
    batches = [series(0, 4, 5.0), [*series(20, 3, 9.0), *series(35, 5, 9.0)], series(60, 2, 1.0), series(75, 3, 5.0)]
    results = []
    for order in itertools.permutations(range(len(batches))):
        ev = evaluator(start=at(0), end=at(90))
        for step, idx in enumerate(order):
            t = at(100 + step)
            ev.add(batch(batches[idx], t))
            ev.evaluate(t, "BATCH")
        results.append(current(ev)[:3])
    assert all(r == results[0] for r in results)


def test_b69_timeline_order_start_batches_then_end_at_the_same_instant() -> None:
    steps = build_timeline(at(0), at(60), [(at(60), "B-2"), (at(60), "B-1"), (at(0), "B-0")])
    assert [(s.kind, s.batch_ref) for s in steps] == [
        (StepKind.MONITORING_START, None),
        (StepKind.BATCH, "B-0"),
        (StepKind.BATCH, "B-1"),
        (StepKind.BATCH, "B-2"),
        (StepKind.MONITORING_END, None),
    ]


def test_b67_c09_end_boundary_is_not_used_before_it_is_reached() -> None:
    ev = evaluator(start=at(0), end=at(60))
    ev.add(batch(series(0, 3, 5.0), at(11)))
    ev.evaluate(at(30), "BATCH")
    assert not ev.state.gaps  # assigned_to is known but not yet reached
    ev.evaluate(at(60), "MONITORING_END")
    assert [g.gap.end_bound.value for g in ev.state.gaps.values()] == ["MONITORING_END"]


def test_b28_ocean_outage_complete_backfill_detects_excursion_without_gap_incident() -> None:
    ev = evaluator(start=at(0), end=at(600))
    ev.add(batch(series(0, 4, 5.0), at(16)))
    ev.evaluate(at(16), "BATCH")
    buffered = [*series(20, 30, 5.0), *series(170, 13, 10.5), *series(235, 70, 5.0)]
    ev.add(batch(buffered, at(400)))  # one restore upload after 6 h of silence
    out = ev.evaluate(at(400), "BATCH")
    assert out is not None
    [tex] = incidents(ev, IncidentCategoryName.TEMPERATURE_EXCURSION)
    assert tex.values.extent_start_at == at(170) and tex.opened_at == at(400)  # original event_at, raised at receipt
    assert not incidents(ev, IncidentCategoryName.DATA_GAP) and not ev.state.gaps


def test_b51_ocean_restore_batch_with_a_real_hole_opens_a_gap_incident_at_receipt() -> None:
    ev = evaluator()
    ev.add(batch([*series(0, 10, 5.0), *series(85, 5, 5.0)], at(400)))
    ev.evaluate(at(400), "BATCH")
    [gap] = incidents(ev, IncidentCategoryName.DATA_GAP)
    assert gap.opened_at == at(400) and gap.values.bracketing_span is not None
