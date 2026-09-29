"""Learned fee observations and persisted recommendation runs."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JSONType, Timestamps, UUIDPk, WorkspaceScoped, str_enum
from app.models.enums import (
    AircraftCategory,
    AirportRole,
    AmountStatus,
    FeeCategory,
    ObservationSource,
)


class FeeObservation(UUIDPk, Timestamps, WorkspaceScoped, Base):
    """Whether a quote carried a fee category at an airport.

    One row per canonical category, present or not, so frequencies have a real
    denominator. Rebuilt for a quote on every recompute.
    """

    __tablename__ = "fee_observations"
    __table_args__ = (
        sa.UniqueConstraint("quote_id", "airport_icao", "airport_role", "fee_category"),
        sa.Index(
            "ix_fee_observations_lookup", "workspace_id", "airport_icao", "fee_category", "month"
        ),
    )

    # Links
    quote_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("quotes.id", ondelete="CASCADE"))
    operator_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("operators.id", ondelete="SET NULL")
    )

    # Context
    airport_icao: Mapped[str] = mapped_column(sa.String(4))
    airport_role: Mapped[AirportRole] = mapped_column(str_enum(AirportRole))
    month: Mapped[int]  # 1-12, of the departure
    aircraft_category: Mapped[AircraftCategory | None] = mapped_column(str_enum(AircraftCategory))

    # Observation
    fee_category: Mapped[FeeCategory] = mapped_column(str_enum(FeeCategory))
    present: Mapped[bool]
    amount_status: Mapped[AmountStatus | None] = mapped_column(str_enum(AmountStatus))
    amount_cents: Mapped[int | None]
    source: Mapped[ObservationSource] = mapped_column(str_enum(ObservationSource))
    observed_at: Mapped[datetime]


class Recommendation(UUIDPk, Timestamps, WorkspaceScoped, Base):
    """One scoring run for a trip; the latest row is the current recommendation."""

    __tablename__ = "recommendations"
    __table_args__ = (sa.Index("ix_recommendations_trip_id_computed_at", "trip_id", "computed_at"),)

    trip_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("trips.id", ondelete="CASCADE"))
    recommended_quote_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("quotes.id", ondelete="SET NULL")
    )
    algorithm_version: Mapped[str] = mapped_column(sa.String(16))
    weights: Mapped[dict[str, Any]] = mapped_column(JSONType)
    # Serialized `RecommendationResult` (per quote: signals, fit, eligibility, reasons, checks).
    ranking: Mapped[dict[str, Any]] = mapped_column(JSONType)
    computed_at: Mapped[datetime]
