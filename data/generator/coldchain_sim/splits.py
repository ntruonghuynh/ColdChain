"""Deterministic journey-level train / validation / test assignment (DATA-05, DATA-06, ML-09).

* The unit of assignment is the **journey**. Every reading, context record and any
  window later cut from a journey belongs to that journey's partition, so overlapping
  windows of one journey can never be split across partitions.
* Stratified greedy allocation that balances the primary scenario, the ambient
  profile and the overall totals at the same time (see ``assign_partitions``).
* The output file contains only ``journey_id`` and ``partition``: the stratification
  labels stay in the ground truth.
"""

import hashlib
from collections.abc import Iterable, Mapping

from coldchain_sim.config import PARTITIONS


class LeakageError(AssertionError):
    """A journey is assigned to more than one partition, or a partition is missing."""


def _order_key(split_seed: int, journey_id: str) -> str:
    return hashlib.sha256(f"split|{split_seed}|{journey_id}".encode()).hexdigest()


def assign_partitions(journeys: Iterable[tuple[str, str, str]], fractions: Mapping[str, float],
                      split_seed: int) -> dict[str, str]:
    """``journeys``: (journey_id, primary_scenario, ambient_profile). Returns journey_id -> partition.

    Journeys are visited in a seeded pseudo-random order (SHA-256 of split seed and journey ID).
    Each goes to the partition with the largest combined deficit against its target fraction,
    summed over three counters: its primary scenario, its ambient profile and the total.
    This balances both stratification variables at once.
    """
    ordered = sorted(journeys, key=lambda j: _order_key(split_seed, j[0]))
    total = dict.fromkeys(PARTITIONS, 0)
    by_scenario: dict[str, dict[str, int]] = {}
    by_ambient: dict[str, dict[str, int]] = {}
    seen_total = 0
    result: dict[str, str] = {}
    for journey_id, scenario, ambient in ordered:
        sc = by_scenario.setdefault(scenario, dict.fromkeys(PARTITIONS, 0))
        am = by_ambient.setdefault(ambient, dict.fromkeys(PARTITIONS, 0))
        seen_total += 1
        n_sc = sum(sc.values()) + 1
        n_am = sum(am.values()) + 1
        best = PARTITIONS[0]
        best_score = float("-inf")
        for p in PARTITIONS:  # ties keep the earlier partition (train, validation, test)
            f = float(fractions[p])
            score = round((f * n_sc - sc[p]) + (f * n_am - am[p]) + 2 * (f * seen_total - total[p]), 9)
            if score > best_score:
                best, best_score = p, score
        total[best] += 1
        sc[best] += 1
        am[best] += 1
        result[journey_id] = best
    return dict(sorted(result.items()))


def check_no_leakage(assignment_rows: Iterable[Mapping[str, str]], journey_ids: Iterable[str]) -> None:
    """Raise if a journey appears twice, has no partition, or an unknown partition name is used."""
    seen: dict[str, str] = {}
    for row in assignment_rows:
        jid, part = row["journey_id"], row["partition"]
        if part not in PARTITIONS:
            raise LeakageError(f"Unknown partition {part!r} for {jid}")
        if jid in seen and seen[jid] != part:
            raise LeakageError(f"Journey {jid} is in both {seen[jid]} and {part}")
        if jid in seen:
            raise LeakageError(f"Journey {jid} is listed twice")
        seen[jid] = part
    missing = set(journey_ids) - set(seen)
    if missing:
        raise LeakageError(f"Journeys without a partition: {sorted(missing)[:5]}")
