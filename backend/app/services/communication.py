"""Communication status of a sensor's gateway, for presentation only (M3 acceptance review).

This is **not** a detector rule. It never changes the monitoring state (CURRENT / STALE /
UNKNOWN), never creates a gap, warning or incident, and never implies that the product is safe.
It describes only facts that are already stored:

* when the last upload (ingest batch carrying readings of this sensor) was received;
* how long ago that was at ``as_of`` (only uploads received by ``as_of`` are used: causal);
* the upload rhythm actually observed: the median and the longest of the most recent upload
  intervals.

``WITHIN_RECENT_UPLOAD_INTERVALS`` means the current silence is not longer than the longest
recent interval between uploads (the usual rhythm); ``LONGER_THAN_RECENT_UPLOAD_INTERVALS``
means it is longer than every recent interval (a possible communication delay or outage). Both
are plain comparisons with observed history; no tolerance or threshold is invented.

The expected gateway upload schedule is **not configured** in the approved detector configuration
``DET-BASELINE v1.0.0``. Classifying an upload as "overdue" against a configured schedule needs a
new configuration version and owner approval (proposal: contract §9 O-1).
"""

import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from app.domain.detector import MonitoringStateName

# Presentation only: how many of the most recent upload intervals describe the observed rhythm,
# and how many are needed before a rhythm is reported at all.
RECENT_UPLOAD_INTERVALS = 10
MIN_INTERVALS_FOR_PATTERN = 3


class CommunicationStatus(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    ENDED = "ENDED"
    NO_UPLOAD_YET = "NO_UPLOAD_YET"
    PATTERN_NOT_ESTABLISHED = "PATTERN_NOT_ESTABLISHED"
    WITHIN_RECENT_UPLOAD_INTERVALS = "WITHIN_RECENT_UPLOAD_INTERVALS"
    LONGER_THAN_RECENT_UPLOAD_INTERVALS = "LONGER_THAN_RECENT_UPLOAD_INTERVALS"


@dataclass(frozen=True, slots=True)
class CommunicationView:
    status: CommunicationStatus
    last_upload_received_at: datetime | None
    since_last_upload: timedelta | None
    observed_upload_interval: timedelta | None  # median of the recent intervals
    longest_recent_upload_interval: timedelta | None
    recent_intervals_used: int
    expected_schedule_configured: bool = False


def communication_view(
    upload_times: Sequence[datetime], as_of: datetime, monitoring: MonitoringStateName
) -> CommunicationView:
    """``upload_times``: receipt times of this sensor's uploads (any order); later ones are ignored."""
    received = sorted({t for t in upload_times if t <= as_of})
    last = received[-1] if received else None
    since = as_of - last if last is not None else None
    recent = received[-(RECENT_UPLOAD_INTERVALS + 1) :]
    intervals = [b - a for a, b in zip(recent, recent[1:], strict=False)]
    median = statistics.median_low(intervals) if intervals else None
    longest = max(intervals) if intervals else None
    if monitoring == MonitoringStateName.NOT_STARTED:
        status = CommunicationStatus.NOT_STARTED
    elif monitoring == MonitoringStateName.ENDED:
        status = CommunicationStatus.ENDED
    elif last is None:
        status = CommunicationStatus.NO_UPLOAD_YET
    elif len(intervals) < MIN_INTERVALS_FOR_PATTERN or longest is None or since is None:
        status = CommunicationStatus.PATTERN_NOT_ESTABLISHED
    elif since <= longest:
        status = CommunicationStatus.WITHIN_RECENT_UPLOAD_INTERVALS
    else:
        status = CommunicationStatus.LONGER_THAN_RECENT_UPLOAD_INTERVALS
    return CommunicationView(status, last, since, median, longest, len(intervals))
