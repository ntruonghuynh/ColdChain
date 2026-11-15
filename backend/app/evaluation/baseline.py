"""Offline evaluation of the M3 policy baseline on DEVELOPMENT data (not the final M9 result).

Protocol (D-13, contract §6):

* Input: a verified dataset release. The reserved final-evaluation seeds 22, 33, 44, 55 and 66
  are refused. By default only the development partitions ``train`` and ``validation`` of
  seed 11 are used; the seed-11 ``test`` partition stays untouched for M4 (used once, after
  freezing). The baseline has no tunable parameter: every value comes from the approved
  policy and detector configuration, so nothing is tuned here.
* Detection: each journey is replayed causally, exactly as the operational detector does it
  (same ``SensorEvaluator``), from the observed files only: batches at their recorded
  ``received_at`` and the documented monitoring boundaries (departure, arrival).
* Reference: the ``EXCURSION_HIGH`` / ``EXCURSION_LOW`` labels (events) and ``MISSING_DATA``
  intervals, read here and nowhere else.
* Matching: deterministic one-to-one (``app.evaluation.matching``).
* Delay: physical onset ``T0`` (reference start), alert-sufficient evidence ``Ea``
  (``confirmed_event_at``) and emission time ``Te`` (``raised_at``) of the earliest raised
  incident revision that overlaps the reference. Missed events have no delay; false alarms
  have no delay. No hindsight: values come from the replay log, not the final state.
"""

import csv
import gzip
import hashlib
import io
import json
import statistics
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.dataset.manifest import load_and_verify
from app.domain.detector import GapStatus, Obs, TempClass
from app.domain.reconcile import IncidentBasis, IncidentCategoryName
from app.domain.replay import SensorEvaluator, StepKind, build_timeline
from app.domain.rules import DETECTOR_CODE_VERSION, DetectorConfig, PolicyRules, parse_detector_config
from app.evaluation.matching import Interval, match_one_to_one

FINAL_EVALUATION_SEEDS = frozenset({22, 33, 44, 55, 66})
DEVELOPMENT_PARTITIONS = ("train", "validation")
PROTOCOL_VERSION = "m3-dev-baseline-1"


class EvaluationRefused(RuntimeError):
    """The requested evaluation would break the evaluation protocol (D-13)."""


def _utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _csv(path: Path) -> Iterable[dict[str, str]]:
    raw = gzip.decompress(path.read_bytes()) if path.suffix == ".gz" else path.read_bytes()
    yield from csv.DictReader(io.StringIO(raw.decode("utf-8")))


def canonical_sha256(document: Any) -> str:
    return hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


@dataclass
class DetectedIncident:
    journey_id: str
    business_ref: str
    category: str
    direction: str | None
    revisions: list[dict[str, Any]] = field(default_factory=list)  # raised_at + values, in order

    @property
    def final(self) -> dict[str, Any]:
        return self.revisions[-1]


def _replay_journey(
    journey_id: str,
    sensor_id: str,
    departure: datetime,
    arrival: datetime,
    uploads: list[tuple[datetime, str]],
    readings: list[Obs],
    policy: PolicyRules,
    config: DetectorConfig,
) -> tuple[dict[str, DetectedIncident], Any, int, int]:
    ev = SensorEvaluator(
        shipment_id=journey_id,
        sensor_id=sensor_id,
        mode="OFFLINE",
        policy=policy,
        config=config,
        assigned_from=departure,
        assigned_to=arrival,
    )
    ev.add(readings)
    incidents: dict[str, DetectedIncident] = {}
    evaluations = 0
    transient_end_gaps = 0
    for step in build_timeline(departure, arrival, uploads):
        trigger = "BATCH" if step.kind == StepKind.BATCH else step.kind.value
        outcome = ev.evaluate(step.at, trigger)
        if outcome is None:
            continue
        evaluations += 1
        transient_end_gaps += sum(1 for g in outcome.changes.new_gaps if g.gap.end_bound.value == "MONITORING_END")
        for change in outcome.changes.incident_changes:
            rec = change.record
            inc = incidents.setdefault(
                rec.business_ref,
                DetectedIncident(
                    journey_id,
                    rec.business_ref,
                    rec.category.value,
                    rec.values.direction.value if rec.values.direction else None,
                ),
            )
            v = rec.values
            inc.revisions.append(
                dict(
                    revision=rec.revision,
                    raised_at=outcome.as_of,
                    start=v.extent_start_at,
                    end=v.extent_end_at,
                    confirmed_event_at=v.confirmed_event_at,
                    first_event_at=v.extent_start_at,
                    basis=v.basis.value,
                    gap_continuity_warning=v.gap_continuity_warning,
                    gap_status=v.gap_status.value if v.gap_status else None,
                )
            )
    return incidents, ev.state, evaluations, transient_end_gaps


def _summary_stats(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"n": 0}
    ordered = sorted(values)
    p90 = ordered[min(len(ordered) - 1, int(round(0.9 * (len(ordered) - 1))))]
    return {
        "n": len(values),
        "mean": round(statistics.fmean(values), 3),
        "median": round(statistics.median(values), 3),
        "p90_nearest_rank": round(p90, 3),
        "min": round(min(values), 3),
        "max": round(max(values), 3),
    }


def summarize(
    journeys: list[str],
    detected: list[DetectedIncident],
    final_gaps: dict[str, list[Any]],
    reference_ex: list[dict[str, Any]],
    reference_missing: list[dict[str, Any]],
    evaluations: int,
    end_gap_revisions: int,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], set[str]]:
    """Metrics from replayed detections and reference events (pure; tested with hand-made fixtures, B79/B80).

    ``reference_ex`` / ``reference_missing`` rows: ``event_id``, ``journey_id``, ``event_type``, ``start``,
    ``end``, ``attributes``. Returns (summary, match rows, missing-data rows, matched detection refs).
    """
    tex = [d for d in detected if d.category == IncidentCategoryName.TEMPERATURE_EXCURSION.value]
    det_intervals = [
        Interval(
            d.business_ref,
            d.journey_id,
            d.direction or "",
            d.final["start"],
            d.final["end"],
            d.revisions[0]["raised_at"],
        )
        for d in tex
    ]
    ref_intervals = [
        Interval(
            r["event_id"],
            r["journey_id"],
            "HIGH" if r["event_type"] == "EXCURSION_HIGH" else "LOW",
            r["start"],
            r["end"],
        )
        for r in reference_ex
    ]
    matches = match_one_to_one(det_intervals, ref_intervals)
    det_by_ref = {ref: det for det, ref in matches}
    tex_by_ref = {d.business_ref: d for d in tex}

    delays_event, delays_emit, parts_sampling, parts_policy, parts_transport = [], [], [], [], []
    preceded = 0
    match_rows = []
    for ref in reference_ex:
        det_ref = det_by_ref.get(ref["event_id"])
        if det_ref is None:
            match_rows.append(
                dict(
                    reference_id=ref["event_id"],
                    journey_id=ref["journey_id"],
                    reference_type=ref["event_type"],
                    reference_start=ref["start"].isoformat(),
                    detection_ref="",
                    matched=False,
                )
            )
            continue
        d = tex_by_ref[det_ref]
        rev = next((r for r in d.revisions if r["start"] < ref["end"] and r["end"] >= ref["start"]), d.revisions[0])
        t0, e1, ea, te = ref["start"], rev["first_event_at"], rev["confirmed_event_at"] or rev["end"], rev["raised_at"]
        d_event = (ea - t0).total_seconds() / 60
        d_emit = (te - t0).total_seconds() / 60
        delays_event.append(d_event)
        delays_emit.append(d_emit)
        parts_sampling.append((e1 - t0).total_seconds() / 60)
        parts_policy.append((ea - e1).total_seconds() / 60)
        parts_transport.append((te - ea).total_seconds() / 60)
        if te < t0:
            preceded += 1
        match_rows.append(
            dict(
                reference_id=ref["event_id"],
                journey_id=ref["journey_id"],
                reference_type=ref["event_type"],
                reference_start=t0.isoformat(),
                detection_ref=det_ref,
                matched=True,
                first_event_at=e1.isoformat(),
                confirmed_event_at=ea.isoformat(),
                raised_at=te.isoformat(),
                delay_event_min=round(d_event, 3),
                delay_emit_min=round(d_emit, 3),
                missing_readings_in_interval=ref["attributes"].get("missing_readings_in_interval"),
                delayed_readings_in_interval=ref["attributes"].get("delayed_readings_in_interval"),
            )
        )

    matched_dets = {det for det, _ in matches}
    n_det, n_ref, n_match = len(tex), len(reference_ex), len(matches)
    current = [d for d in tex if d.final["basis"] == IncidentBasis.CURRENT.value]
    false_alarms = [d for d in tex if d.business_ref not in matched_dets]

    def recall_where(pred: Any) -> dict[str, Any]:
        refs = [r for r in reference_ex if pred(r)]
        hit = sum(1 for r in refs if r["event_id"] in det_by_ref)
        return {"reference_events": len(refs), "detected": hit, "recall": round(hit / len(refs), 4) if refs else None}

    # ---- missing-data behaviour
    gap_rows, status_agree, gap_found = [], 0, 0
    for ref in reference_missing:
        gaps = final_gaps.get(ref["journey_id"], [])
        same = [g for g in gaps if g.gap.start_at == ref["start"] and g.gap.end_at == ref["end"]]
        over = same or [g for g in gaps if g.gap.start_at < ref["end"] and ref["start"] < g.gap.end_at]
        ref_status = ref["attributes"].get("policy_gap_status")
        op_status = over[0].gap.status.value if over else None
        gap_found += bool(over)
        status_agree += op_status == ref_status
        gap_rows.append(
            dict(
                reference_id=ref["event_id"],
                journey_id=ref["journey_id"],
                reference_start=ref["start"].isoformat(),
                reference_end=ref["end"].isoformat(),
                reference_status=ref_status,
                operational_status=op_status or "",
                exact_bounds=bool(same),
            )
        )
    all_gaps = [g for gs in final_gaps.values() for g in gs]
    gap_incidents = [d for d in detected if d.category == IncidentCategoryName.DATA_GAP.value]

    summary: dict[str, Any] = {
        "label": "DEVELOPMENT measurement on seed 11 (train + validation partitions). NOT the final M9 result.",
        "journeys": len(journeys),
        "evaluations": evaluations,
        "excursion_detection": {
            "reference_events": n_ref,
            "detections_raised": n_det,
            "matched": n_match,
            "precision": round(n_match / n_det, 4) if n_det else None,
            "recall": round(n_match / n_ref, 4) if n_ref else None,
            "false_alarms": len(false_alarms),
            "false_alarms_per_journey": round(len(false_alarms) / len(journeys), 4) if journeys else None,
            "false_alarms_later_superseded_or_merged": sum(
                1 for d in false_alarms if d.final["basis"] != IncidentBasis.CURRENT.value
            ),
            "detections_with_final_basis_current": len(current),
            "by_direction": {
                dirn: {
                    "reference_events": sum(1 for r in reference_ex if r["event_type"] == f"EXCURSION_{dirn}"),
                    "detections_raised": sum(1 for d in tex if d.direction == dirn),
                    "matched": sum(1 for det, _ in matches if tex_by_ref[det].direction == dirn),
                }
                for dirn in (TempClass.HIGH.value, TempClass.LOW.value)
            },
        },
        "detection_delay_min": {
            "definition": "T0 = reference start (ground truth); Ea = confirmed_event_at; Te = raised_at of the "
            "earliest raised incident revision overlapping the reference. Matched events only.",
            "event_time_delay_Ea_minus_T0": _summary_stats(delays_event),
            "emission_delay_Te_minus_T0": _summary_stats(delays_emit),
            "component_first_evidence_E1_minus_T0": _summary_stats(parts_sampling),
            "component_policy_duration_Ea_minus_E1": _summary_stats(parts_policy),
            "component_transmission_Te_minus_Ea": _summary_stats(parts_transport),
            "alerts_raised_before_onset": preceded,
            "missed_events_without_delay": n_ref - n_match,
        },
        "missing_readings_behaviour": {
            "recall_reference_excursions_with_missing_readings": recall_where(
                lambda r: (r["attributes"].get("missing_readings_in_interval") or 0) > 0
            ),
            "recall_reference_excursions_without_missing_readings": recall_where(
                lambda r: (r["attributes"].get("missing_readings_in_interval") or 0) == 0
            ),
            "recall_reference_excursions_with_delayed_readings": recall_where(
                lambda r: (r["attributes"].get("delayed_readings_in_interval") or 0) > 0
            ),
            "reference_missing_data_intervals": len(reference_missing),
            "found_as_confirmed_gap": gap_found,
            "found_with_identical_bounds": sum(1 for g in gap_rows if g["exact_bounds"]),
            "gap_status_agreement": status_agree,
            "operational_confirmed_gaps_final": len(all_gaps),
            "operational_gaps_by_status": {s.value: sum(1 for g in all_gaps if g.gap.status == s) for s in GapStatus},
            "monitoring_end_gap_revisions_raised": end_gap_revisions,
            "monitoring_end_gaps_in_final_state": sum(1 for g in all_gaps if g.gap.end_bound.value == "MONITORING_END"),
            "data_gap_incidents_raised": len(gap_incidents),
            "data_gap_incidents_final_basis_superseded": sum(
                1 for d in gap_incidents if d.final["basis"] != IncidentBasis.CURRENT.value
            ),
            "gap_time_counted_in_range_s": 0,
            "gap_time_counted_in_range_note": "Zero by construction: the detector has no in-range-time measure; "
            "every confirmed gap is not-observed time (C-06).",
        },
    }
    return summary, match_rows, gap_rows, matched_dets


def check_protocol(manifest: dict[str, Any], partitions: tuple[str, ...]) -> None:
    """Refuse before reading any data (D-13)."""
    seed = int(manifest["seed"])
    if seed in FINAL_EVALUATION_SEEDS:
        raise EvaluationRefused(f"seed {seed} is reserved for final evaluation (D-13); it is never used in M3")
    if "test" in partitions:
        raise EvaluationRefused("the test partition is not used for development measurements (D-13)")
    unknown = set(partitions) - set(DEVELOPMENT_PARTITIONS)
    if unknown or not partitions:
        raise EvaluationRefused(f"partitions must be a non-empty subset of {DEVELOPMENT_PARTITIONS}")


def run_baseline_evaluation(
    dataset_dir: Path,
    policy_file: Path,
    detector_config_file: Path,
    out_dir: Path,
    *,
    partitions: tuple[str, ...] = DEVELOPMENT_PARTITIONS,
    git_commit: str | None = None,
) -> dict[str, Any]:
    check_protocol(json.loads((dataset_dir / "manifest.json").read_text(encoding="utf-8")), partitions)
    ds = load_and_verify(dataset_dir)  # checksums of every file, before any record is read
    manifest = ds.manifest
    seed = int(manifest["seed"])
    policy_doc = json.loads(policy_file.read_text(encoding="utf-8"))
    policy_sha = canonical_sha256(policy_doc)
    if policy_sha != manifest["policy"]["content_sha256"]:
        raise EvaluationRefused("the dataset labels were derived from a different policy content")
    policy = PolicyRules.from_document(policy_doc, policy_sha)
    config_doc = json.loads(detector_config_file.read_text(encoding="utf-8"))
    config = parse_detector_config(config_doc, canonical_sha256(config_doc))

    split = {r["journey_id"]: r["partition"] for r in _csv(dataset_dir / "splits" / "journey_split.csv")}
    journeys = sorted(j for j, p in split.items() if p in partitions)
    selected = set(journeys)
    shipments = {
        r["shipment_id"]: r for r in _csv(dataset_dir / "observed" / "shipments.csv") if r["shipment_id"] in selected
    }
    uploads: dict[str, list[tuple[datetime, str]]] = defaultdict(list)
    for r in _csv(dataset_dir / "observed" / "uploads.csv.gz"):
        if r["shipment_id"] in selected:
            uploads[r["shipment_id"]].append((_utc(r["received_at"]), r["upload_id"]))
    readings: dict[str, list[Obs]] = defaultdict(list)
    for r in _csv(dataset_dir / "observed" / "readings.csv.gz"):
        if r["shipment_id"] in selected:
            readings[r["shipment_id"]].append(
                Obs(_utc(r["event_at"]), Decimal(r["temperature_c"]), _utc(r["received_at"]))
            )

    detected: list[DetectedIncident] = []
    final_gaps: dict[str, list[Any]] = {}
    evaluations = 0
    end_gap_revisions = 0
    for j in journeys:
        s = shipments[j]
        incs, state, n_eval, end_gaps = _replay_journey(
            j, s["sensor_id"], _utc(s["departure_at"]), _utc(s["arrival_at"]), uploads[j], readings[j], policy, config
        )
        detected.extend(incs.values())
        final_gaps[j] = sorted(state.gaps.values(), key=lambda g: g.gap.start_at)
        evaluations += n_eval
        end_gap_revisions += end_gaps

    # ---- reference labels (evaluation only)
    reference_ex: list[dict[str, Any]] = []
    reference_missing: list[dict[str, Any]] = []
    for r in _csv(dataset_dir / "ground_truth" / "events.csv.gz"):
        if r["journey_id"] not in selected:
            continue
        attrs = json.loads(r["attributes"]) if r["attributes"] else {}
        row = dict(
            event_id=r["event_id"],
            journey_id=r["journey_id"],
            event_type=r["event_type"],
            start=_utc(r["start_at"]),
            end=_utc(r["end_at"]),
            attributes=attrs,
        )
        if r["event_type"] in ("EXCURSION_HIGH", "EXCURSION_LOW"):
            reference_ex.append(row)
        elif r["event_type"] == "MISSING_DATA":
            reference_missing.append(row)

    summary, match_rows, gap_rows, matched_dets = summarize(
        journeys, detected, final_gaps, reference_ex, reference_missing, evaluations, end_gap_revisions
    )
    run_config = {
        "protocol_version": PROTOCOL_VERSION,
        "purpose": "M3 development measurement of the policy baseline; final evaluation is M9 on seeds 22-66 (D-13)",
        "dataset_id": manifest["dataset_id"],
        "dataset_fingerprint": manifest["dataset_fingerprint"],
        "seed": seed,
        "split_seed": manifest.get("split_seed"),
        "partitions": list(partitions),
        "journey_count": len(journeys),
        "policy": {
            "code": policy.policy_code,
            "version": policy.policy_version,
            "content_sha256": policy.content_sha256,
        },
        "detector_config": {
            "code": config.detector_code,
            "version": config.config_version,
            "content_sha256": config.content_sha256,
            "nominal_sampling_interval_s": int(config.nominal_interval.total_seconds()),
            "max_continuous_interval_s": int(config.max_continuous_interval.total_seconds()),
        },
        "detector_code_version": DETECTOR_CODE_VERSION,
        "git_commit": git_commit or "not recorded",
        "matching": "one-to-one; same journey, same type, overlapping event-time intervals; ties: overlap desc, "
        "start distance asc, raised_at asc, detection id, reference id (app/evaluation/matching.py)",
        "tuned_parameters": "none",
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "run_config.json").write_text(json.dumps(run_config, indent=2, sort_keys=True) + "\n")
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n")
    _write_csv(out_dir / "matches.csv", match_rows)
    _write_csv(
        out_dir / "detections.csv",
        [
            dict(
                detection_ref=d.business_ref,
                journey_id=d.journey_id,
                category=d.category,
                direction=d.direction or "",
                revisions=len(d.revisions),
                first_raised_at=d.revisions[0]["raised_at"].isoformat(),
                final_start=d.final["start"].isoformat(),
                final_end=d.final["end"].isoformat(),
                final_basis=d.final["basis"],
                gap_continuity_warning=d.final["gap_continuity_warning"],
                matched=d.business_ref in matched_dets,
            )
            for d in sorted(detected, key=lambda x: x.business_ref)
        ],
    )
    _write_csv(out_dir / "missing_data_intervals.csv", gap_rows)
    return {"summary": summary, "run_config": run_config}


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields: list[str] = []
    for row in rows:
        fields += [k for k in row if k not in fields]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields or ["empty"], lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: ("" if v is None else v) for k, v in row.items()})
