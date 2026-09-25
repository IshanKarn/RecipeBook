"""Declarative base and shared column mixins."""

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, MetaData, func, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Deterministic constraint names keep Alembic migrations stable and reviewable.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(AsyncAttrs, DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )


class CreatedAtMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TimestampMixin(CreatedAtMixin):
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


def pg_enum(enum_cls: type[Enum], name: str) -> SAEnum:
    """A PostgreSQL enum type that stores the enum *values* (not member names)."""
    return SAEnum(
        enum_cls,
        name=name,
        values_callable=lambda members: [member.value for member in members],
        validate_strings=True,
    )
