"""Source documents and ingest."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import AwareDatetime, BaseModel, model_validator

from app.models.enums import DocumentChannel, DocumentIntent, DocumentKind, ExtractionStatus
from app.schemas.common import APIModel, ORMModel
from app.schemas.quote import QuoteSummaryOut


class TextPage(BaseModel):
    page: int
    text: str


class SourceDocumentOut(ORMModel):
    id: uuid.UUID
    trip_id: uuid.UUID
    quote_id: uuid.UUID | None
    parent_id: uuid.UUID | None
    operator_id: uuid.UUID | None
    uploaded_by_id: uuid.UUID | None
    kind: DocumentKind
    channel: DocumentChannel
    original_filename: str | None
    media_type: str
    size_bytes: int
    sha256: str
    page_count: int | None
    is_scanned: bool
    sender: str | None
    subject: str | None
    received_at: AwareDatetime | None
    intent: DocumentIntent | None
    extraction_status: ExtractionStatus
    extractor: str | None
    extractor_version: str | None
    extractor_model: str | None
    extraction_error: str | None
    processing_ms: int | None
    created_at: AwareDatetime


class SourceDocumentDetailOut(SourceDocumentOut):
    text_pages: list[TextPage]
    extraction_usage: dict[str, Any] | None
    children: list[SourceDocumentOut] = []


class IngestOut(BaseModel):
    """201 when processed inline, 202 when queued (poll `extraction_status`)."""

    source_document: SourceDocumentOut
    quote: QuoteSummaryOut | None
    created_quote: bool
    duplicate: bool


class DocumentMoveIn(APIModel):
    """Reattach a document to another quote, or to an operator (its quote is found or made)."""

    quote_id: uuid.UUID | None = None
    operator_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> DocumentMoveIn:
        if (self.quote_id is None) == (self.operator_id is None):
            raise ValueError("give exactly one of quote_id or operator_id")
        return self
