"""Trips, their legs, and the operators asked to quote them (RFQ tracking)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, JSONType, Timestamps, UUIDPk, WorkspaceScoped, str_enum
from app.models.enums import RequestChannel, TripOperatorStatus, TripStatus, TripType


class Trip(UUIDPk, Timestamps, WorkspaceScoped, Base):
    __tablename__ = "trips"
    __table_args__ = (
        sa.UniqueConstraint("workspace_id", "reference"),
        sa.CheckConstraint("pax >= 1", name="pax_positive"),
        sa.Index("ix_trips_workspace_id_status", "workspace_id", "status"),
        sa.Index("ix_trips_workspace_id_created_at", "workspace_id", "created_at"),
    )

    reference: Mapped[str] = mapped_column(sa.String(32))
    status: Mapped[TripStatus] = mapped_column(str_enum(TripStatus), default=TripStatus.DRAFT)
    trip_type: Mapped[TripType] = mapped_column(str_enum(TripType), default=TripType.ONE_WAY)
    pax: Mapped[int]
    client_name: Mapped[str | None] = mapped_column(sa.String(200))
    client_email: Mapped[str | None] = mapped_column(sa.String(320))
    # Validated by `schemas.trip.TripPreferences`.
    preferences: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    notes: Mapped[str | None] = mapped_column(sa.Text)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("users.id", ondelete="SET NULL")
    )
    booked_quote_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("quotes.id", ondelete="SET NULL", use_alter=True)
    )
    booked_at: Mapped[datetime | None]

    legs: Mapped[list[TripLeg]] = relationship(
        back_populates="trip",
        order_by="TripLeg.seq",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class TripLeg(UUIDPk, Timestamps, WorkspaceScoped, Base):
    __tablename__ = "trip_legs"
    __table_args__ = (sa.UniqueConstraint("trip_id", "seq"),)

    trip_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("trips.id", ondelete="CASCADE"), index=True
    )
    seq: Mapped[int]
    origin_icao: Mapped[str] = mapped_column(sa.String(4))
    destination_icao: Mapped[str] = mapped_column(sa.String(4))
    # Naive wall-clock time at the origin; `depart_tz` gives its zone.
    depart_local: Mapped[datetime] = mapped_column(sa.DateTime(timezone=False))
    depart_tz: Mapped[str] = mapped_column(sa.String(64))

    trip: Mapped[Trip] = relationship(back_populates="legs")


class TripOperator(UUIDPk, Timestamps, WorkspaceScoped, Base):
    __tablename__ = "trip_operators"
    __table_args__ = (sa.UniqueConstraint("trip_id", "operator_id"),)

    trip_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("trips.id", ondelete="CASCADE"), index=True
    )
    operator_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("operators.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[TripOperatorStatus] = mapped_column(
        str_enum(TripOperatorStatus), default=TripOperatorStatus.REQUESTED
    )
    channel: Mapped[RequestChannel] = mapped_column(
        str_enum(RequestChannel), default=RequestChannel.EMAIL
    )
    requested_at: Mapped[datetime]
    responded_at: Mapped[datetime | None]
    declined_reason: Mapped[str | None] = mapped_column(sa.String(500))
    notes: Mapped[str | None] = mapped_column(sa.Text)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("users.id", ondelete="SET NULL")
    )
