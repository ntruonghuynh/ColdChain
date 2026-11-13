"""Database-level integrity rules of the data model.

Rule references: FR-03 (both clocks kept), DATA-01, BC-05 / approved rule "only the
authorized Quality Officer can approve shipment release", BR-13 (unique business refs).
"""

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session

from app.db.models import (
    BusinessEvent,
    DispositionIncident,
    Incident,
    Policy,
    Product,
    Reading,
    WarehouseRelease,
)
from app.db.models.enums import BusinessEventType, Decision, DetectionSource, IncidentCategory, PolicyStatus, Role
from tests.factories import T0, active_policy, make_batch, make_disposition, make_sensor, make_shipment, sha, user


def _reading(shipment, sensor, batch, event_at, received_at, temp="5.00") -> Reading:
    return Reading(sensor_id=sensor.sensor_id, shipment_id=shipment.shipment_id,
                   ingest_batch_id=batch.batch_id, event_at=event_at, received_at=received_at,
                   temperature_c=Decimal(temp))


# ---------------- readings: two clocks, UTC, uniqueness ----------------

def test_fr03_reading_keeps_event_and_received_time_as_utc(db_session: Session) -> None:
    shipment = make_shipment(db_session)
    sensor = make_sensor(db_session)
    batch = make_batch(db_session, shipment)
    plus7 = timezone(timedelta(hours=7))
    event_at = datetime(2026, 1, 1, 10, 0, tzinfo=plus7)
    received_at = datetime(2026, 1, 1, 18, 30, tzinfo=plus7)  # delayed by an 8.5 h coverage gap
    db_session.add(_reading(shipment, sensor, batch, event_at, received_at))
    db_session.flush()
    db_session.expire_all()

    stored = db_session.scalars(select(Reading).where(Reading.sensor_id == sensor.sensor_id)).one()
    assert stored.event_at == datetime(2026, 1, 1, 3, 0, tzinfo=UTC)
    assert stored.received_at == datetime(2026, 1, 1, 11, 30, tzinfo=UTC)
    assert stored.event_at.tzinfo is not None and stored.received_at.tzinfo is not None
    assert stored.received_at - stored.event_at == timedelta(hours=8, minutes=30)


def test_fr03_reading_requires_received_time(db_session: Session) -> None:
    shipment = make_shipment(db_session)
    sensor = make_sensor(db_session)
    batch = make_batch(db_session, shipment)
    db_session.add(_reading(shipment, sensor, batch, T0, None))
    with pytest.raises(IntegrityError, match="received_at"):
        db_session.flush()
    db_session.rollback()


def test_nfr05_naive_timestamp_is_rejected(db_session: Session) -> None:
    shipment = make_shipment(db_session)
    sensor = make_sensor(db_session)
    batch = make_batch(db_session, shipment)
    db_session.add(_reading(shipment, sensor, batch, datetime(2026, 1, 1, 10, 0), T0))
    with pytest.raises(StatementError, match="no timezone"):
        db_session.flush()
    db_session.rollback()


def test_data01_reading_unique_per_sensor_and_event_time(db_session: Session) -> None:
    shipment = make_shipment(db_session)
    sensor = make_sensor(db_session)
    batch = make_batch(db_session, shipment)
    db_session.add(_reading(shipment, sensor, batch, T0, T0))
    db_session.flush()
    db_session.add(_reading(shipment, sensor, batch, T0, T0 + timedelta(minutes=5), temp="6.00"))
    with pytest.raises(IntegrityError, match="uq_reading_sensor_id_event_at"):
        db_session.flush()
    db_session.rollback()


# ---------------- authorization: only QUALITY decides, release needs RELEASE ----------------

def test_release_authority_quality_user_can_record_disposition(db_session: Session) -> None:
    shipment = make_shipment(db_session)
    disposition = make_disposition(db_session, shipment, Decision.RELEASE)
    assert disposition.decided_by_role == Role.QUALITY


@pytest.mark.parametrize("username", ["carrier.demo", "warehouse.demo", "shipper.demo", "platform.admin"])
def test_release_authority_non_quality_user_cannot_record_disposition(db_session: Session, username: str) -> None:
    shipment = make_shipment(db_session)
    with pytest.raises(IntegrityError, match="fk_disposition_decider_role"):
        make_disposition(db_session, shipment, Decision.RELEASE, username=username)
    db_session.rollback()


def test_release_authority_disposition_role_must_be_quality(db_session: Session) -> None:
    shipment = make_shipment(db_session)
    with pytest.raises(IntegrityError, match="ck_disposition_decider_is_quality"):
        make_disposition(db_session, shipment, Decision.RELEASE, username="carrier.demo",
                         decided_by_role=Role.CARRIER)
    db_session.rollback()


def _release(shipment, disposition, released_by) -> WarehouseRelease:
    return WarehouseRelease(business_ref=f"REL-{shipment.shipment_id}", shipment_id=shipment.shipment_id,
                            disposition_id=disposition.disposition_id, released_by_user_id=released_by,
                            released_at=T0)


def test_release_authority_warehouse_release_with_release_disposition(db_session: Session) -> None:
    shipment = make_shipment(db_session)
    disposition = make_disposition(db_session, shipment, Decision.RELEASE)
    db_session.add(_release(shipment, disposition, user(db_session, "warehouse.demo").user_id))
    db_session.flush()


def test_release_authority_warehouse_release_rejected_for_quarantine(db_session: Session) -> None:
    shipment = make_shipment(db_session)
    disposition = make_disposition(db_session, shipment, Decision.QUARANTINE)
    db_session.add(_release(shipment, disposition, user(db_session, "warehouse.demo").user_id))
    with pytest.raises(IntegrityError, match="fk_warehouse_release_disposition"):
        db_session.flush()
    db_session.rollback()


def test_release_authority_warehouse_release_rejected_for_other_shipments_decision(db_session: Session) -> None:
    shipment_a = make_shipment(db_session)
    shipment_b = make_shipment(db_session)
    disposition_a = make_disposition(db_session, shipment_a, Decision.RELEASE)
    db_session.add(_release(shipment_b, disposition_a, user(db_session, "warehouse.demo").user_id))
    with pytest.raises(IntegrityError, match="fk_warehouse_release_disposition"):
        db_session.flush()
    db_session.rollback()


def test_disposition_cannot_close_incident_of_another_shipment(db_session: Session) -> None:
    shipment_a = make_shipment(db_session)
    shipment_b = make_shipment(db_session)
    incident_b = Incident(business_ref="INC-TEST-B", shipment_id=shipment_b.shipment_id,
                          category=IncidentCategory.DATA_GAP, interval_start=T0,
                          detected_by=DetectionSource.MANUAL, policy_id=shipment_b.policy_id, opened_at=T0)
    db_session.add(incident_b)
    disposition_a = make_disposition(db_session, shipment_a, Decision.QUARANTINE)
    db_session.add(DispositionIncident(disposition_id=disposition_a.disposition_id,
                                       incident_id=incident_b.incident_id, shipment_id=shipment_a.shipment_id))
    with pytest.raises(IntegrityError, match="fk_disposition_incident_incident"):
        db_session.flush()
    db_session.rollback()


# ---------------- business references and policy integrity ----------------

def test_br13_business_reference_is_unique(db_session: Session) -> None:
    shipment = make_shipment(db_session)

    def event() -> BusinessEvent:
        return BusinessEvent(business_ref="EVT-DUPLICATE", event_type=BusinessEventType.SHIPMENT_REGISTERED,
                             shipment_id=shipment.shipment_id, actor_org_id="ORG-SHIPPER", occurred_at=T0,
                             payload={"shipment_id": shipment.shipment_id}, payload_sha256=sha("x"))

    db_session.add(event())
    db_session.flush()
    db_session.add(event())
    with pytest.raises(IntegrityError, match="uq_business_event_business_ref"):
        db_session.flush()
    db_session.rollback()


def _policy(product_id: str, **overrides: object) -> Policy:
    base = dict(policy_code="POL-TEST", policy_version="9.9", product_id=product_id, status=PolicyStatus.DRAFT,
                min_temp_c=Decimal("2.0"), max_temp_c=Decimal("8.0"), high_excursion_min_duration_min=30,
                low_excursion_min_duration_min=15, gap_unknown_after_min=15, gap_review_at_min=30,
                release_authority_role=Role.QUALITY, procedure_version="SOP-TEST", effective_from=T0,
                is_teaching_policy=True, disclaimer="test", approval_reference="test", source_file="test",
                content_sha256=sha("policy"))
    base.update(overrides)
    return Policy(**base)


def test_only_one_active_policy_per_product(db_session: Session) -> None:
    db_session.add(_policy(active_policy(db_session).product_id, status=PolicyStatus.ACTIVE))
    with pytest.raises(IntegrityError, match="uq_policy_one_active_per_product"):
        db_session.flush()
    db_session.rollback()


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"release_authority_role": Role.WAREHOUSE}, "ck_policy_release_authority_is_quality"),
        ({"min_temp_c": Decimal("8.0"), "max_temp_c": Decimal("2.0")}, "ck_policy_min_below_max"),
        ({"gap_review_at_min": 10}, "ck_policy_gap_review_not_below_unknown"),
        ({"high_excursion_min_duration_min": 0}, "ck_policy_high_duration_positive"),
    ],
)
def test_policy_check_constraints(db_session: Session, overrides: dict, constraint: str) -> None:
    db_session.add(_policy(active_policy(db_session).product_id, **overrides))
    with pytest.raises(IntegrityError, match=constraint):
        db_session.flush()
    db_session.rollback()


def test_shipment_policy_must_belong_to_shipment_product(db_session: Session) -> None:
    db_session.add(Product(product_id="PRD-OTHER", name="Other", category="TEST"))
    db_session.flush()
    other_policy = _policy("PRD-OTHER")
    db_session.add(other_policy)
    db_session.flush()
    shipment = make_shipment(db_session)
    shipment.policy_id = other_policy.policy_id  # product stays PRD-CHILL-01
    with pytest.raises(IntegrityError, match="fk_shipment_policy_product"):
        db_session.flush()
    db_session.rollback()
