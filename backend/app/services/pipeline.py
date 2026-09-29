"""Ingest and processing of source documents (design spec §0 "Pipeline", §3).

`process_source_document` is the one function that does the work:
load -> extract (with fallback) -> provenance -> resolve quote -> merge ->
recompute, writing processing events at each step. `PIPELINE_MODE=inline`
runs it inside the request; `background` runs the same function through
FastAPI `BackgroundTasks` with its own session (`run_in_background`).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.extraction.base import Extractor
from app.models.document import ProcessingEvent, SourceDocument
from app.models.enums import DocumentChannel, EventLevel, ProcessingStep
from app.models.quote import Quote
from app.models.trip import Trip
from app.permissions import RequestContext
from app.services.storage import Storage


@dataclass(frozen=True, slots=True)
class IngestCommand:
    """One upload: exactly one of `data` (a file) or `text` (pasted)."""

    data: bytes | None = None
    filename: str | None = None
    declared_media_type: str | None = None
    text: str | None = None
    channel: DocumentChannel | None = None
    sender: str | None = None
    subject: str | None = None
    received_at: datetime | None = None
    operator_id: uuid.UUID | None = None
    quote_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class IngestOutcome:
    document: SourceDocument
    quote: Quote | None
    created_quote: bool
    duplicate: bool  # same sha256 already on this trip; `document` is the existing row
    queued: bool  # True in background mode (respond 202)


@dataclass(frozen=True, slots=True)
class ProcessResult:
    document: SourceDocument
    quote: Quote | None
    created_quote: bool


def log_event(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    trip_id: uuid.UUID,
    step: ProcessingStep,
    message: str,
    level: EventLevel = EventLevel.INFO,
    quote_id: uuid.UUID | None = None,
    source_document_id: uuid.UUID | None = None,
    data: dict[str, Any] | None = None,
) -> ProcessingEvent:
    """Append one line to the trip's live processing log (message capped at 300 chars)."""
    event = ProcessingEvent(
        workspace_id=workspace_id,
        trip_id=trip_id,
        quote_id=quote_id,
        source_document_id=source_document_id,
        step=step,
        level=level,
        message=message[:300],
        data=data,
    )
    db.add(event)
    return event


def ingest(
    db: Session,
    ctx: RequestContext,
    trip: Trip,
    cmd: IngestCommand,
    *,
    settings: Settings,
    storage: Storage,
    extractor: Extractor,
) -> IngestOutcome:
    """Validate and store the upload, create the SourceDocument (deduplicated by
    sha256 per trip), create child documents for email PDF attachments, and in
    inline mode process it. Explicit `quote_id`/`operator_id` must belong to the
    caller's workspace and trip (404 otherwise). Audited as `document.ingest`.
    """
    raise NotImplementedError


def process_source_document(
    db: Session,
    doc_id: uuid.UUID,
    *,
    settings: Settings,
    storage: Storage,
    extractor: Extractor,
    now: datetime | None = None,
    operator_id: uuid.UUID | None = None,
    quote_id: uuid.UUID | None = None,
) -> ProcessResult:
    """Extract, verify provenance, resolve and merge into a quote, then recompute the trip.

    Sets `extraction_status` (succeeded, failed, needs_manual) and never raises
    for extraction problems: they become flags and processing events.
    """
    raise NotImplementedError


def run_in_background(
    session_factory: sessionmaker[Any],
    workspace_id: uuid.UUID,
    doc_id: uuid.UUID,
    *,
    settings: Settings,
    storage: Storage,
    extractor: Extractor,
) -> None:
    """BackgroundTasks entry point: opens its own workspace-scoped session and commits."""
    raise NotImplementedError


def reprocess_document(
    db: Session,
    ctx: RequestContext,
    doc: SourceDocument,
    *,
    settings: Settings,
    storage: Storage,
    extractor: Extractor,
) -> ProcessResult:
    """Re-extract a document; values from the same document are replaced unless locked."""
    raise NotImplementedError


def move_document(
    db: Session,
    ctx: RequestContext,
    doc: SourceDocument,
    *,
    quote_id: uuid.UUID | None,
    operator_id: uuid.UUID | None,
    settings: Settings,
) -> SourceDocument:
    """Reattach a document (and its fields) to another quote or operator on the same
    trip, then recompute both quotes. Audited as `document.move`."""
    raise NotImplementedError
