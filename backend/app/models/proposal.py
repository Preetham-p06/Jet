"""Client proposals and their frozen per-quote options."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, JSONType, Timestamps, UUIDPk, WorkspaceScoped, str_enum
from app.models.enums import ProposalStatus


class Proposal(UUIDPk, Timestamps, WorkspaceScoped, Base):
    __tablename__ = "proposals"
    __table_args__ = (
        sa.CheckConstraint("markup_pct >= 0 AND markup_pct <= 100", name="markup_range"),
    )

    # Identity
    trip_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("trips.id", ondelete="CASCADE"), index=True
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("users.id", ondelete="SET NULL")
    )
    status: Mapped[ProposalStatus] = mapped_column(
        str_enum(ProposalStatus), default=ProposalStatus.DRAFT
    )
    title: Mapped[str] = mapped_column(sa.String(200))
    client_name: Mapped[str | None] = mapped_column(sa.String(200))
    message: Mapped[str | None] = mapped_column(sa.Text)
    markup_pct: Mapped[Decimal] = mapped_column(sa.Numeric(5, 2), default=Decimal("0"))

    # Share link (plaintext by design: see the design spec, risk 7)
    share_token: Mapped[str | None] = mapped_column(sa.String(64), unique=True)
    share_enabled: Mapped[bool] = mapped_column(default=False, server_default=sa.false())
    share_expires_at: Mapped[datetime | None]

    # Lifecycle
    sent_at: Mapped[datetime | None]
    sent_by_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("users.id", ondelete="SET NULL")
    )
    accepted_at: Mapped[datetime | None]
    accepted_option_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("proposal_options.id", ondelete="SET NULL", use_alter=True)
    )
    accepted_by_name: Mapped[str | None] = mapped_column(sa.String(200))
    booked_at: Mapped[datetime | None]
    declined_at: Mapped[datetime | None]
    cancelled_at: Mapped[datetime | None]

    # Views and versioning
    first_viewed_at: Mapped[datetime | None]
    last_viewed_at: Mapped[datetime | None]
    view_count: Mapped[int] = mapped_column(default=0, server_default="0")
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("proposals.id", ondelete="SET NULL")
    )

    options: Mapped[list[ProposalOption]] = relationship(
        back_populates="proposal",
        foreign_keys="ProposalOption.proposal_id",
        order_by="ProposalOption.sort_order",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class ProposalOption(UUIDPk, Timestamps, WorkspaceScoped, Base):
    __tablename__ = "proposal_options"
    __table_args__ = (sa.UniqueConstraint("proposal_id", "quote_id"),)

    # Identity
    proposal_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("proposals.id", ondelete="CASCADE"), index=True
    )
    quote_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("quotes.id", ondelete="CASCADE"))
    sort_order: Mapped[int] = mapped_column(default=0)
    is_recommended: Mapped[bool] = mapped_column(default=False, server_default=sa.false())

    # Pricing (USD cents)
    cost_basis_cents: Mapped[int]
    markup_pct_override: Mapped[Decimal | None] = mapped_column(sa.Numeric(5, 2))
    markup_cents: Mapped[int]
    client_total_cents: Mapped[int]

    # Snapshots, frozen at send
    client_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    broker_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    snapshot_at: Mapped[datetime | None]

    proposal: Mapped[Proposal] = relationship(back_populates="options", foreign_keys=[proposal_id])
