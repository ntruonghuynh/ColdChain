"""Rule inputs of the baseline detector: the shipment's policy and the detector configuration.

The policy (product requirement, immutable, approved by quality) and the detector
configuration (measuring equipment: nominal sampling interval, continuity limit) are kept
apart on purpose (requirements analysis §13.1, 2026-11-15). Both are versioned and both
versions are recorded with every detector result.
"""

import uuid
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Any, Protocol

# Bump when the detector's algorithm changes in a way that can change results.
DETECTOR_CODE_VERSION = "m3-baseline-1"


class DetectorConfigError(ValueError):
    """The detector configuration document is invalid."""


class _PolicyLike(Protocol):
    policy_id: uuid.UUID
    policy_code: str
    policy_version: str
    min_temp_c: Decimal
    max_temp_c: Decimal
    high_excursion_min_duration_min: int
    low_excursion_min_duration_min: int
    gap_unknown_after_min: int
    gap_review_at_min: int
    content_sha256: str


@dataclass(frozen=True, slots=True)
class PolicyRules:
    """The values of one immutable policy version (BR-01 to BR-04)."""

    policy_id: uuid.UUID | None
    policy_code: str
    policy_version: str
    content_sha256: str
    min_temp_c: Decimal
    max_temp_c: Decimal
    high_min_duration: timedelta
    low_min_duration: timedelta
    gap_unknown_after: timedelta
    gap_review_at: timedelta

    @classmethod
    def from_row(cls, row: _PolicyLike) -> "PolicyRules":
        return cls(
            policy_id=row.policy_id,
            policy_code=row.policy_code,
            policy_version=row.policy_version,
            content_sha256=row.content_sha256,
            min_temp_c=Decimal(row.min_temp_c),
            max_temp_c=Decimal(row.max_temp_c),
            high_min_duration=timedelta(minutes=row.high_excursion_min_duration_min),
            low_min_duration=timedelta(minutes=row.low_excursion_min_duration_min),
            gap_unknown_after=timedelta(minutes=row.gap_unknown_after_min),
            gap_review_at=timedelta(minutes=row.gap_review_at_min),
        )

    @classmethod
    def from_document(
        cls, document: dict[str, Any], content_sha256: str, policy_id: uuid.UUID | None = None
    ) -> "PolicyRules":
        """From the policy JSON file (offline evaluation, which does not use the database)."""
        pol = document["policy"]
        return cls(
            policy_id=policy_id,
            policy_code=pol["policy_code"],
            policy_version=pol["policy_version"],
            content_sha256=content_sha256,
            min_temp_c=Decimal(str(pol["limits"]["min_temp_c"])),
            max_temp_c=Decimal(str(pol["limits"]["max_temp_c"])),
            high_min_duration=timedelta(minutes=int(pol["duration_rule"]["high_excursion_min_duration_min"])),
            low_min_duration=timedelta(minutes=int(pol["duration_rule"]["low_excursion_min_duration_min"])),
            gap_unknown_after=timedelta(minutes=int(pol["missing_data_rule"]["gap_unknown_after_min"])),
            gap_review_at=timedelta(minutes=int(pol["missing_data_rule"]["gap_review_at_min"])),
        )


@dataclass(frozen=True, slots=True)
class DetectorConfig:
    """One immutable detector configuration version (D-01, C-01)."""

    detector_config_id: uuid.UUID | None
    detector_code: str
    config_version: str
    content_sha256: str
    nominal_interval: timedelta
    max_continuous_interval: timedelta

    @property
    def label(self) -> str:
        return f"{self.detector_code} v{self.config_version}"


def parse_detector_config(
    document: dict[str, Any], content_sha256: str, detector_config_id: uuid.UUID | None = None
) -> DetectorConfig:
    """Validate a detector configuration document (contract §5.3, test B76)."""
    try:
        code = str(document["detector_code"])
        version = str(document["config_version"])
        nominal_s = document["nominal_sampling_interval_s"]
        max_s = document["max_continuous_interval_s"]
    except KeyError as exc:
        raise DetectorConfigError(f"missing field {exc.args[0]!r}") from exc
    if not all(isinstance(v, int) and not isinstance(v, bool) for v in (nominal_s, max_s)):
        raise DetectorConfigError("intervals must be whole seconds")
    if nominal_s <= 0:
        raise DetectorConfigError("nominal_sampling_interval_s must be positive")
    # One missing reading (about 2 x nominal) must always be a gap, and on-schedule
    # readings (1 x nominal) must always be continuous.
    if not nominal_s < max_s < 2 * nominal_s:
        raise DetectorConfigError(
            "max_continuous_interval_s must be greater than the nominal interval and less than twice it"
        )
    return DetectorConfig(
        detector_config_id=detector_config_id,
        detector_code=code,
        config_version=version,
        content_sha256=content_sha256,
        nominal_interval=timedelta(seconds=nominal_s),
        max_continuous_interval=timedelta(seconds=max_s),
    )
