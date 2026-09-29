"""Uploaded source documents and the processing log they produce."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JSONType, Timestamps, UUIDPk, WorkspaceScoped, str_enum
from app.models.enums import (
    DocumentChannel,
    DocumentIntent,
    DocumentKind,
    EventLevel,
    ExtractionStatus,
    ProcessingStep,
)


class SourceDocument(UUIDPk, Timestamps, WorkspaceScoped, Base):
    __tablename__ = "source_documents"
    # A re-upload of the same bytes to the same trip returns the existing row.
    __table_args__ = (sa.UniqueConstraint("trip_id", "sha256"),)

    # Links
    trip_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("trips.id", ondelete="CASCADE"), index=True
    )
    quote_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("quotes.id", ondelete="SET NULL"), index=True
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("source_documents.id", ondelete="CASCADE")
    )
    operator_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("operators.id", ondelete="SET NULL")
    )
    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("users.id", ondelete="SET NULL")
    )

    # Type
    kind: Mapped[DocumentKind] = mapped_column(str_enum(DocumentKind))
    channel: Mapped[DocumentChannel] = mapped_column(str_enum(DocumentChannel))

    # File
    original_filename: Mapped[str | None] = mapped_column(sa.String(255))
    media_type: Mapped[str] = mapped_column(sa.String(127))
    storage_key: Mapped[str] = mapped_column(sa.String(512))
    size_bytes: Mapped[int]
    sha256: Mapped[str] = mapped_column(sa.String(64))
    page_count: Mapped[int | None]
    is_scanned: Mapped[bool] = mapped_column(default=False, server_default=sa.false())
    # [{"page": 1, "text": "..."}]; pages are 1-based.
    text_pages: Mapped[list[Any]] = mapped_column(JSONType, default=list)

    # Message metadata
    sender: Mapped[str | None] = mapped_column(sa.String(320))
    subject: Mapped[str | None] = mapped_column(sa.String(500))
    received_at: Mapped[datetime | None]
    intent: Mapped[DocumentIntent | None] = mapped_column(str_enum(DocumentIntent))

    # Extraction
    extraction_status: Mapped[ExtractionStatus] = mapped_column(
        str_enum(ExtractionStatus), default=ExtractionStatus.PENDING
    )
    extractor: Mapped[str | None] = mapped_column(sa.String(32))
    extractor_version: Mapped[str | None] = mapped_column(sa.String(64))
    extractor_model: Mapped[str | None] = mapped_column(sa.String(64))
    extraction_error: Mapped[str | None] = mapped_column(sa.Text)
    # Raw `ExtractionResult.model_dump(mode="json")`.
    extraction_result: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    # Token usage, including cache read tokens for Claude.
    extraction_usage: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    processing_ms: Mapped[int | None]


class ProcessingEvent(UUIDPk, Timestamps, WorkspaceScoped, Base):
    """One line of a trip's live processing log."""

    __tablename__ = "processing_events"
    __table_args__ = (sa.Index("ix_processing_events_trip_id_created_at", "trip_id", "created_at"),)

    trip_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("trips.id", ondelete="CASCADE"))
    quote_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("quotes.id", ondelete="SET NULL")
    )
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("source_documents.id", ondelete="SET NULL")
    )
    step: Mapped[ProcessingStep] = mapped_column(str_enum(ProcessingStep))
    level: Mapped[EventLevel] = mapped_column(str_enum(EventLevel), default=EventLevel.INFO)
    message: Mapped[str] = mapped_column(sa.String(300))
    data: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
