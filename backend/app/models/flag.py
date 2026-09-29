"""Review flags raised by validation, reconciled by fingerprint on every recompute."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JSONType, Timestamps, UUIDPk, WorkspaceScoped, str_enum
from app.models.enums import FeeCategory, FlagResolution, FlagSeverity, FlagStatus, FlagType


class Flag(UUIDPk, Timestamps, WorkspaceScoped, Base):
    __tablename__ = "flags"
    __table_args__ = (
        sa.UniqueConstraint("quote_id", "fingerprint"),
        sa.Index("ix_flags_trip_id_status", "trip_id", "status"),
    )

    # Links
    trip_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("trips.id", ondelete="CASCADE"))
    quote_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("quotes.id", ondelete="CASCADE")
    )
    # Document-level flags (extraction_failed, ocr_unavailable) may have no quote yet.
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("source_documents.id", ondelete="SET NULL")
    )
    field_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("quote_fields.id", ondelete="SET NULL")
    )
    fee_category: Mapped[FeeCategory | None] = mapped_column(str_enum(FeeCategory))

    # Classification
    type: Mapped[FlagType] = mapped_column(str_enum(FlagType, length=40))
    severity: Mapped[FlagSeverity] = mapped_column(str_enum(FlagSeverity))
    blocking: Mapped[bool] = mapped_column(default=False, server_default=sa.false())

    # Dedupe: fingerprint identifies the condition; data_hash detects changes to it.
    fingerprint: Mapped[str] = mapped_column(sa.String(200))
    data_hash: Mapped[str] = mapped_column(sa.String(64))

    # Content
    message: Mapped[str] = mapped_column(sa.String(500))
    details: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)

    # Resolution
    status: Mapped[FlagStatus] = mapped_column(str_enum(FlagStatus), default=FlagStatus.OPEN)
    resolution: Mapped[FlagResolution | None] = mapped_column(str_enum(FlagResolution))
    resolution_note: Mapped[str | None] = mapped_column(sa.String(1000))
    resolved_by_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("users.id", ondelete="SET NULL")
    )
    resolved_at: Mapped[datetime | None]
