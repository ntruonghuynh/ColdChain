"""Validation of submitted sensor records (pure). Rules: FR-01, BR-07, BR-08, U-03, U-05.

* Measurements are validated as exact decimals. A value that cannot be stored exactly
  (more than 2 decimal places, the precision of ``reading.temperature_c NUMERIC(6,2)``) is
  rejected, never rounded (BR-08 amendment, 2026-11-15).
* −40.0 and +60.0 °C are valid (BR-08 range, inclusive).
* ``event_at`` may be at most 5 min after ``received_at`` (future clock skew, BR-08).
  A reading received long after it was measured is valid (delayed data is never rejected
  for lateness).
* A reading must belong to a sensor assigned to the shipment and lie inside the documented
  monitoring window ``[assigned_from, assigned_to]`` (U-03).
* Clients never supply ``received_at`` (C-09). A record that carries it is rejected.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any

TEMP_MIN_C = Decimal("-40")  # BR-08 sensor physical range (inclusive)
TEMP_MAX_C = Decimal("60")
BATTERY_MIN_PCT, BATTERY_MAX_PCT = Decimal("0"), Decimal("100")
MAX_FUTURE_SKEW = timedelta(minutes=5)  # BR-08
STORED_QUANTUM = Decimal("0.01")  # NUMERIC(6,2) / NUMERIC(5,2)
DOOR_STATES = ("OPEN", "CLOSED")

READING_FIELDS = frozenset({"sensor_id", "event_at", "temperature_c", "shipment_id"})
CONTEXT_FIELDS = frozenset(
    {"sensor_id", "event_at", "shipment_id", "door_state", "battery_level_pct", "ambient_temperature_c"}
)


class Reason(StrEnum):
    NOT_AN_OBJECT = "NOT_AN_OBJECT"
    MISSING_FIELD = "MISSING_FIELD"
    UNEXPECTED_FIELD = "UNEXPECTED_FIELD"
    INVALID_TYPE = "INVALID_TYPE"
    INVALID_TIMESTAMP = "INVALID_TIMESTAMP"
    NAIVE_TIMESTAMP = "NAIVE_TIMESTAMP"
    NOT_A_NUMBER = "NOT_A_NUMBER"
    PRECISION_EXCEEDED = "PRECISION_EXCEEDED"
    OUT_OF_PHYSICAL_RANGE = "OUT_OF_PHYSICAL_RANGE"
    OUT_OF_RANGE = "OUT_OF_RANGE"
    INVALID_VALUE = "INVALID_VALUE"
    CLOCK_SKEW = "CLOCK_SKEW"
    SHIPMENT_MISMATCH = "SHIPMENT_MISMATCH"
    UNKNOWN_SENSOR = "UNKNOWN_SENSOR"
    SENSOR_NOT_ASSIGNED = "SENSOR_NOT_ASSIGNED"
    OUTSIDE_MONITORING_WINDOW = "OUTSIDE_MONITORING_WINDOW"
    DUPLICATE_CONFLICT = "DUPLICATE_CONFLICT"
    CONTEXT_CONFLICT = "CONTEXT_CONFLICT"
    CONTEXT_WITHOUT_READING = "CONTEXT_WITHOUT_READING"


@dataclass(frozen=True, slots=True)
class Rejection:
    reason: Reason
    detail: str


@dataclass(frozen=True, slots=True)
class Window:
    assigned_from: datetime
    assigned_to: datetime | None

    def contains(self, t: datetime) -> bool:
        return self.assigned_from <= t and (self.assigned_to is None or t <= self.assigned_to)


@dataclass(frozen=True, slots=True)
class ReadingInput:
    sensor_id: str
    event_at: datetime
    temperature_c: Decimal


@dataclass(frozen=True, slots=True)
class ContextInput:
    sensor_id: str
    event_at: datetime
    door_state: str | None
    battery_level_pct: Decimal | None
    ambient_temperature_c: Decimal | None


# ------------------------------------------------------------------ field parsers


def parse_timestamp(value: Any, name: str) -> datetime | Rejection:
    if not isinstance(value, str):
        return Rejection(Reason.INVALID_TIMESTAMP, f"{name} must be an ISO 8601 string")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return Rejection(Reason.INVALID_TIMESTAMP, f"{name}={value!r} is not ISO 8601")
    if parsed.tzinfo is None or parsed.tzinfo.utcoffset(parsed) is None:
        return Rejection(Reason.NAIVE_TIMESTAMP, f"{name}={value!r} has no time zone (use Z or an offset)")
    return parsed.astimezone(UTC)


def parse_measurement(
    value: Any, name: str, lo: Decimal, hi: Decimal, range_reason: Reason = Reason.OUT_OF_RANGE
) -> Decimal | Rejection:
    """Exact decimal. JSON numbers arrive as ``Decimal`` (the body is parsed with parse_float=Decimal)."""
    if isinstance(value, bool) or not isinstance(value, (Decimal, int, str)):
        return Rejection(Reason.NOT_A_NUMBER, f"{name} must be a number")
    try:
        number = Decimal(value) if not isinstance(value, Decimal) else value
    except InvalidOperation:
        return Rejection(Reason.NOT_A_NUMBER, f"{name}={value!r} is not a number")
    if not number.is_finite():
        return Rejection(Reason.NOT_A_NUMBER, f"{name} must be finite")
    if number.quantize(STORED_QUANTUM) != number:
        return Rejection(
            Reason.PRECISION_EXCEEDED, f"{name}={value} has more than 2 decimal places; it is rejected, not rounded"
        )
    if not lo <= number <= hi:
        return Rejection(range_reason, f"{name}={number} is outside {lo} to {hi}")
    return number


def _check_fields(raw: Any, allowed: frozenset[str], required: Sequence[str]) -> Mapping[str, Any] | Rejection:
    if not isinstance(raw, Mapping):
        return Rejection(Reason.NOT_AN_OBJECT, "record must be a JSON object")
    extra = sorted(set(raw) - allowed)
    if extra:
        return Rejection(
            Reason.UNEXPECTED_FIELD,
            f"unexpected field(s) {extra}; received_at is set by the server and cannot be supplied",
        )
    missing = [f for f in required if raw.get(f) is None]
    if missing:
        return Rejection(Reason.MISSING_FIELD, f"missing field(s) {missing}")
    return raw


def _common(
    raw: Mapping[str, Any],
    *,
    shipment_id: str,
    received_at: datetime,
    known_sensors: set[str],
    windows: Mapping[str, Sequence[Window]],
) -> tuple[str, datetime] | Rejection:
    sensor_id = raw["sensor_id"]
    if not isinstance(sensor_id, str) or not sensor_id:
        return Rejection(Reason.INVALID_TYPE, "sensor_id must be a non-empty string")
    if raw.get("shipment_id") is not None and raw["shipment_id"] != shipment_id:
        return Rejection(
            Reason.SHIPMENT_MISMATCH, f"record shipment_id {raw['shipment_id']!r} != batch {shipment_id!r}"
        )
    event_at = parse_timestamp(raw["event_at"], "event_at")
    if isinstance(event_at, Rejection):
        return event_at
    if event_at - received_at > MAX_FUTURE_SKEW:
        return Rejection(
            Reason.CLOCK_SKEW,
            f"event_at {event_at.isoformat()} is more than 5 min after received_at {received_at.isoformat()}",
        )
    if sensor_id not in known_sensors:
        return Rejection(Reason.UNKNOWN_SENSOR, f"sensor {sensor_id!r} is not registered")
    sensor_windows = windows.get(sensor_id, ())
    if not sensor_windows:
        return Rejection(
            Reason.SENSOR_NOT_ASSIGNED, f"sensor {sensor_id!r} is not assigned to shipment {shipment_id!r}"
        )
    if not any(w.contains(event_at) for w in sensor_windows):
        return Rejection(
            Reason.OUTSIDE_MONITORING_WINDOW,
            f"event_at {event_at.isoformat()} is outside the documented monitoring window",
        )
    return sensor_id, event_at


# ------------------------------------------------------------------ records


def validate_reading(
    raw: Any,
    *,
    shipment_id: str,
    received_at: datetime,
    known_sensors: set[str],
    windows: Mapping[str, Sequence[Window]],
) -> ReadingInput | Rejection:
    checked = _check_fields(raw, READING_FIELDS, ("sensor_id", "event_at", "temperature_c"))
    if isinstance(checked, Rejection):
        return checked
    common = _common(
        checked, shipment_id=shipment_id, received_at=received_at, known_sensors=known_sensors, windows=windows
    )
    if isinstance(common, Rejection):
        return common
    temp = parse_measurement(
        checked["temperature_c"], "temperature_c", TEMP_MIN_C, TEMP_MAX_C, Reason.OUT_OF_PHYSICAL_RANGE
    )
    if isinstance(temp, Rejection):
        return temp
    return ReadingInput(common[0], common[1], temp)


def validate_context(
    raw: Any,
    *,
    shipment_id: str,
    received_at: datetime,
    known_sensors: set[str],
    windows: Mapping[str, Sequence[Window]],
) -> ContextInput | Rejection:
    checked = _check_fields(raw, CONTEXT_FIELDS, ("sensor_id", "event_at"))
    if isinstance(checked, Rejection):
        return checked
    common = _common(
        checked, shipment_id=shipment_id, received_at=received_at, known_sensors=known_sensors, windows=windows
    )
    if isinstance(common, Rejection):
        return common
    door = checked.get("door_state")
    if door is not None and door not in DOOR_STATES:
        return Rejection(Reason.INVALID_VALUE, f"door_state must be one of {DOOR_STATES} or null")
    battery: Decimal | Rejection | None = None
    if checked.get("battery_level_pct") is not None:
        battery = parse_measurement(checked["battery_level_pct"], "battery_level_pct", BATTERY_MIN_PCT, BATTERY_MAX_PCT)
        if isinstance(battery, Rejection):
            return battery
    ambient: Decimal | Rejection | None = None
    if checked.get("ambient_temperature_c") is not None:
        ambient = parse_measurement(
            checked["ambient_temperature_c"],
            "ambient_temperature_c",
            TEMP_MIN_C,
            TEMP_MAX_C,
            Reason.OUT_OF_PHYSICAL_RANGE,
        )
        if isinstance(ambient, Rejection):
            return ambient
    return ContextInput(common[0], common[1], door, battery, ambient)


# ------------------------------------------------------------------ BR-07 identity


def same_reading(stored_shipment_id: str, stored_temp: Decimal, shipment_id: str, temp: Decimal) -> bool:
    """Identical duplicate: same shipment and the same value compared as decimals (8.0 == 8.00)."""
    return stored_shipment_id == shipment_id and stored_temp == temp


def same_context(
    stored: tuple[str, str | None, Decimal | None, Decimal | None], shipment_id: str, ctx: ContextInput
) -> bool:
    return stored == (shipment_id, ctx.door_state, ctx.battery_level_pct, ctx.ambient_temperature_c)
