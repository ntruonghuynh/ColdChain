"""Ground truth of the synthetic dataset, in the separate PostgreSQL schema ``ground_truth`` (DATA-09).

These tables hold the simulator's labels: scenario, ambient profile and parameters per
journey, and labelled intervals (true out-of-range runs, policy-derived excursions,
injected causes, sensor faults, missing data, transmission delays).

**Detection, ML feature and API code must never read these tables** (CLAUDE.md: "Ground
truth is separate"). Only the dataset importer writes them and only evaluation code
(Milestone 9) may read them. ``backend/tests/test_ground_truth_boundary.py`` fails if
any other application module imports this module.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, created_at_col, str_enum
from app.db.models.enums import AmbientProfile, GroundTruthEventType, LabelSource, PrimaryScenario
from app.db.types import UTCDateTime

GROUND_TRUTH_SCHEMA = "ground_truth"


class GroundTruthJourney(Base):
    __tablename__ = "journey"

    journey_id: Mapped[str] = mapped_column(String(60), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("dataset_release.dataset_id"), nullable=False)
    shipment_id: Mapped[str] = mapped_column(ForeignKey("shipment.shipment_id"), nullable=False, unique=True)
    primary_scenario: Mapped[PrimaryScenario] = mapped_column(
        str_enum(PrimaryScenario, "primary_scenario"), nullable=False
    )
    scenario_tags: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    ambient_profile: Mapped[AmbientProfile] = mapped_column(
        str_enum(AmbientProfile, "ambient_profile"), nullable=False
    )
    route_type: Mapped[str] = mapped_column(String(20), nullable=False)
    policy_excursion_count: Mapped[int] = mapped_column(Integer, nullable=False)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        CheckConstraint("policy_excursion_count >= 0", name="policy_excursion_count_non_negative"),
        Index("ix_journey_dataset_id", "dataset_id"),
        {"schema": GROUND_TRUTH_SCHEMA},
    )


class GroundTruthEvent(Base):
    __tablename__ = "event"

    event_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("dataset_release.dataset_id"), nullable=False)
    journey_id: Mapped[str] = mapped_column(ForeignKey(f"{GROUND_TRUTH_SCHEMA}.journey.journey_id"), nullable=False)
    event_type: Mapped[GroundTruthEventType] = mapped_column(
        str_enum(GroundTruthEventType, "event_type"), nullable=False
    )
    label_source: Mapped[LabelSource] = mapped_column(str_enum(LabelSource, "label_source"), nullable=False)
    cause: Mapped[str] = mapped_column(String(200), nullable=False)
    start_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    end_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    duration_min: Mapped[int] = mapped_column(Integer, nullable=False)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        CheckConstraint("end_at >= start_at", name="interval_ordered"),
        CheckConstraint("duration_min >= 0", name="duration_non_negative"),
        Index("ix_event_journey_id_event_type", "journey_id", "event_type"),
        {"schema": GROUND_TRUTH_SCHEMA},
    )
