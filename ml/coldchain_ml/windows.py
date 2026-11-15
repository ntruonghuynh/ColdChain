"""Causal 60-minute windows on the approved five-minute event-time grid."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable


@dataclass(frozen=True, slots=True)
class Reading:
    event_at: datetime
    received_at: datetime
    temperature_c: float
    ambient_temperature_c: float | None = None
    door_open: bool | None = None
    battery_level_pct: float | None = None
    context_received_at: datetime | None = None


def causal_readings(readings: Iterable[Reading], as_of: datetime) -> list[Reading]:
    """Keep only readings both measured and received by the prediction timestamp."""
    rows = [r for r in readings if r.event_at <= as_of and r.received_at <= as_of]
    return sorted(rows, key=lambda r: (r.event_at, r.received_at))


def window_start(end_at: datetime, minutes: int = 60) -> datetime:
    return end_at - timedelta(minutes=minutes)
