"""Quotes, the per-value provenance/review records, and derived fee lines."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, JSONType, Timestamps, UUIDPk, WorkspaceScoped, str_enum
from app.models.enums import (
    AircraftCategory,
    AmountStatus,
    Availability,
    ExtractorKind,
    FeeCategory,
    FeeUnit,
    FieldGroup,
    FieldStatus,
    IncludedBy,
    PricingBasis,
    QuoteStatus,
    ValueType,
)


class Quote(UUIDPk, Timestamps, WorkspaceScoped, Base):
    """One operator's offer for one trip, merged from every source document.

    Everything under "derived" is rebuilt by `services.recompute` and never
    edited directly.
    """

    __tablename__ = "quotes"
    __table_args__ = (sa.Index("ix_quotes_trip_id_operator_id", "trip_id", "operator_id"),)

    # Identity
    trip_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("trips.id", ondelete="CASCADE"))
    operator_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("operators.id", ondelete="RESTRICT"), index=True
    )
    trip_operator_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("trip_operators.id", ondelete="SET NULL")
    )
    status: Mapped[QuoteStatus] = mapped_column(str_enum(QuoteStatus), default=QuoteStatus.ACTIVE)
    original_currency: Mapped[str] = mapped_column(sa.String(3), default="USD")
    pricing_basis: Mapped[PricingBasis] = mapped_column(
        str_enum(PricingBasis), default=PricingBasis.FLAT
    )

    # Derived prices (USD cents)
    headline_cents: Mapped[int | None]
    known_total_cents: Mapped[int | None]  # lower bound
    upper_total_cents: Mapped[int | None]
    is_fully_priced: Mapped[bool] = mapped_column(default=False, server_default=sa.false())

    # Derived review state
    open_blocking_flags: Mapped[int] = mapped_column(default=0, server_default="0")
    open_info_flags: Mapped[int] = mapped_column(default=0, server_default="0")
    pending_review_count: Mapped[int] = mapped_column(default=0, server_default="0")
    quote_confidence: Mapped[int | None]
    confidence_mean: Mapped[float | None]

    # Derived ranking
    fit_score: Mapped[int | None]
    fit_breakdown: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    is_recommended: Mapped[bool] = mapped_column(default=False, server_default=sa.false())
    eligible_for_proposal: Mapped[bool] = mapped_column(default=False, server_default=sa.false())
    eligibility_reasons: Mapped[list[Any]] = mapped_column(JSONType, default=list)

    # Denormalized scalars (from current quote_fields)
    aircraft_model: Mapped[str | None] = mapped_column(sa.String(120))
    aircraft_category: Mapped[AircraftCategory | None] = mapped_column(str_enum(AircraftCategory))
    tail_number: Mapped[str | None] = mapped_column(sa.String(16))
    seats: Mapped[int | None]
    wifi: Mapped[bool | None]
    flight_time_minutes: Mapped[int | None]
    departure_local: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=False))
    availability: Mapped[Availability | None] = mapped_column(str_enum(Availability))

    # Timing
    first_received_at: Mapped[datetime | None]
    last_received_at: Mapped[datetime | None]
    computed_at: Mapped[datetime | None]
    calc_version: Mapped[str | None] = mapped_column(sa.String(32))

    fields: Mapped[list[QuoteField]] = relationship(
        back_populates="quote",
        foreign_keys="QuoteField.quote_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    fee_lines: Mapped[list[FeeLine]] = relationship(
        back_populates="quote",
        order_by="FeeLine.sort_order",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class QuoteField(UUIDPk, Timestamps, WorkspaceScoped, Base):
    """The provenance and review record for one extracted value, scalar or fee.

    `original_value` is never mutated. Superseded and conflicting values are
    kept as non-current rows; at most one row per (quote, key) is current.
    `version` is the optimistic-locking counter: stale writes raise
    `StaleDataError`, which the API maps to 409.
    """

    __tablename__ = "quote_fields"
    __table_args__ = (
        sa.CheckConstraint(
            "(locked AND status <> 'extracted') OR (NOT locked AND status = 'extracted')",
            name="locked_iff_reviewed",
        ),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 100", name="confidence_range"),
        sa.Index(
            "uq_quote_fields_current_key",
            "quote_id",
            "key",
            unique=True,
            sqlite_where=sa.text("is_current"),
            postgresql_where=sa.text("is_current"),
        ),
    )

    # Identity
    quote_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("quotes.id", ondelete="CASCADE"), index=True
    )
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("source_documents.id", ondelete="SET NULL")
    )
    key: Mapped[str] = mapped_column(sa.String(80))  # "headline_price", "fee.fuel_surcharge", ...
    group: Mapped[FieldGroup] = mapped_column(str_enum(FieldGroup))
    label: Mapped[str | None] = mapped_column(sa.String(200))  # fee label as written

    # Value, validated by `schemas.field_values`
    value_type: Mapped[ValueType] = mapped_column(str_enum(ValueType))
    original_value: Mapped[Any] = mapped_column(JSONType)
    current_value: Mapped[Any] = mapped_column(JSONType)

    # Provenance
    confidence: Mapped[int]
    extractor: Mapped[ExtractorKind] = mapped_column(str_enum(ExtractorKind))
    extractor_version: Mapped[str | None] = mapped_column(sa.String(64))
    snippet: Mapped[str | None] = mapped_column(sa.String(500))
    page: Mapped[int | None]
    char_start: Mapped[int | None]
    char_end: Mapped[int | None]
    snippet_verified: Mapped[bool] = mapped_column(default=False, server_default=sa.false())
    sequence: Mapped[int] = mapped_column(default=0, server_default="0")

    # Review
    status: Mapped[FieldStatus] = mapped_column(
        str_enum(FieldStatus), default=FieldStatus.EXTRACTED
    )
    locked: Mapped[bool] = mapped_column(default=False, server_default=sa.false())
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[datetime | None]
    review_note: Mapped[str | None] = mapped_column(sa.String(1000))

    # Revision history
    is_current: Mapped[bool] = mapped_column(default=True, server_default=sa.true())
    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("quote_fields.id", ondelete="SET NULL")
    )
    corroborating_source_ids: Mapped[list[str]] = mapped_column(JSONType, default=list)
    version: Mapped[int] = mapped_column(nullable=False)

    quote: Mapped[Quote] = relationship(back_populates="fields", foreign_keys=[quote_id])

    __mapper_args__ = {"version_id_col": version}


class FeeLine(UUIDPk, Timestamps, WorkspaceScoped, Base):
    """The typed, normalized view of one fee on a quote (derived, rebuilt on recompute)."""

    __tablename__ = "fee_lines"

    # Identity
    quote_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("quotes.id", ondelete="CASCADE"), index=True
    )
    # Null for synthetic lines (expected-fee rules, "all in" coverage).
    field_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("quote_fields.id", ondelete="SET NULL")
    )
    category: Mapped[FeeCategory] = mapped_column(str_enum(FeeCategory))
    label: Mapped[str] = mapped_column(sa.String(200))

    # Amount
    amount_status: Mapped[AmountStatus] = mapped_column(str_enum(AmountStatus))
    included_by: Mapped[IncludedBy | None] = mapped_column(str_enum(IncludedBy))
    amount_cents: Mapped[int | None]  # USD
    original_amount_minor: Mapped[int | None]
    original_currency: Mapped[str | None] = mapped_column(sa.String(3))

    # Basis
    unit: Mapped[FeeUnit] = mapped_column(str_enum(FeeUnit), default=FeeUnit.FLAT)
    quantity: Mapped[Decimal | None] = mapped_column(sa.Numeric(12, 4))
    percent: Mapped[Decimal | None] = mapped_column(sa.Numeric(7, 4))
    explicitly_extra: Mapped[bool] = mapped_column(default=False, server_default=sa.false())

    # Totals
    counts_in_known: Mapped[bool] = mapped_column(default=False, server_default=sa.false())
    counts_in_upper: Mapped[bool] = mapped_column(default=False, server_default=sa.false())
    estimate_cents: Mapped[int | None]
    # e.g. "operator_estimate", "rule:fet", "learned:KTEB"
    estimate_basis: Mapped[str | None] = mapped_column(sa.String(64))

    # Display
    confidence: Mapped[int | None]
    review_status: Mapped[FieldStatus | None] = mapped_column(str_enum(FieldStatus))
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("source_documents.id", ondelete="SET NULL")
    )
    page: Mapped[int | None]
    sort_order: Mapped[int] = mapped_column(default=0)

    quote: Mapped[Quote] = relationship(back_populates="fee_lines")
