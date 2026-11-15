"""Test-only helpers for the Milestone 3 detector tests (hand-built series, never shipped)."""

import json
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from app.domain.detector import Obs, Snapshot, evaluate
from app.domain.rules import DetectorConfig, PolicyRules, parse_detector_config
from app.seed.loader import canonical_sha256

APP_DIR = Path(__file__).resolve().parents[1] / "app"
_POLICY_DOC = json.loads((APP_DIR / "seed/data/policies/POL-CHILL-01_v1.0.json").read_text())
_CONFIG_DOC = json.loads((APP_DIR / "seed/data/detector/DET-BASELINE_v1.0.0.json").read_text())

# Values come from the approved files, not from the tests (CLAUDE.md rule 3).
POLICY: PolicyRules = PolicyRules.from_document(_POLICY_DOC, canonical_sha256(_POLICY_DOC))
CONFIG: DetectorConfig = parse_detector_config(_CONFIG_DOC, canonical_sha256(_CONFIG_DOC))

T0 = datetime(2026, 9, 1, 10, 0, tzinfo=UTC)


def at(minutes: float = 0, seconds: float = 0) -> datetime:
    return T0 + timedelta(minutes=minutes, seconds=seconds)


def obs(points: Iterable[tuple[datetime, float | str]], received_at: datetime | None = None) -> list[Obs]:
    return [Obs(t, Decimal(str(v)), received_at or t) for t, v in points]


def series(start_min: float, count: int, value: float | str, step_min: float = 5) -> list[tuple[datetime, float | str]]:
    return [(at(start_min + i * step_min), value) for i in range(count)]


def run(
    points: Iterable[tuple[datetime, float | str]], *, start: datetime | None = None, end: datetime | None = None
) -> Snapshot:
    readings = sorted(obs(points), key=lambda o: o.event_at)
    return evaluate(readings, start=start, end=end, policy=POLICY, config=CONFIG)
