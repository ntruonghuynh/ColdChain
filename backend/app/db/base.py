"""Declarative base, naming conventions and shared column helpers."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Enum, MetaData, Uuid, func, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.db.types import UTCDateTime

# Stable constraint names so Alembic migrations are deterministic.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


# Schemas managed by Alembic: the default schema (operational data) and ``ground_truth``
# (synthetic dataset labels, kept apart from what detection code reads; DATA-09).
MANAGED_SCHEMAS: frozenset[str | None] = frozenset({None, "public", "ground_truth"})


def include_name(name: str | None, type_: str, parent_names: object) -> bool:
    """Alembic ``include_name`` hook: compare only the schemas this project manages."""
    if type_ == "schema":
        return name in MANAGED_SCHEMAS
    return True


def str_enum(enum_cls: type[enum.Enum], name: str) -> Enum:
    """Store an enum as VARCHAR + CHECK constraint (easier to migrate than native PG enums)."""
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=40,
        values_callable=lambda e: [m.value for m in e],
        validate_strings=True,
    )


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )


def created_at_col() -> Mapped[datetime]:
    return mapped_column(UTCDateTime(), nullable=False, server_default=func.now())
