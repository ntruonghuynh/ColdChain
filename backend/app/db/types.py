"""Custom column types."""

from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator


class NaiveDatetimeError(ValueError):
    """Raised when a timestamp without timezone information is written."""


class UTCDateTime(TypeDecorator[datetime]):
    """``timestamptz`` column that rejects naive datetimes and always returns UTC.

    Sensor event time and received time must never be guessed: a timestamp
    without an explicit timezone is an error, not "probably UTC" (NFR-05).
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            raise NaiveDatetimeError(
                "Timestamp has no timezone. Provide a timezone-aware value (UTC recommended)."
            )
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:  # defensive: timestamptz always returns aware values
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
