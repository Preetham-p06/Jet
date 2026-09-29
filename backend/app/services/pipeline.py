"""Ingest and processing of source documents (design spec §0 "Pipeline", §3).

`process_source_document` is the one function that does the work:
load -> extract (with fallback) -> provenance -> resolve quote -> merge ->
recompute, writing processing events at each step. `PIPELINE_MODE=inline`
runs it inside the request; `background` runs the same function through
FastAPI `BackgroundTasks` with its own session (`run_in_background`).
"""

from __future__ import annotations

import dataclasses
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.config import PipelineMode, Settings
from app.db import set_workspace
from app.errors import DomainError, NotFound, Unprocessable
from app.extraction import provenance
from app.extraction.base import (
    DocumentInput,
    DocumentUnreadable,
    ExtractionContext,
    Extractor,
    ExtractorError,
    LegContext,
)
from app.extraction.documents import Attachment, LoadedDocument, load_document, load_pdf
from app.extraction.registry import error_code, run_extractor
from app.extraction.types import ExtractionResult
from app.models.base import utcnow
from app.models.document import ProcessingEvent, SourceDocument
from app.models.enums import (
    DocumentChannel,
    DocumentIntent,
    DocumentKind,
    EventLevel,
    ExtractionStatus,
    FlagResolution,
    FlagSeverity,
    FlagStatus,
    FlagType,
    ProcessingStep,
    QuoteStatus,
)
from app.models.flag import Flag
from app.models.operator import Operator
from app.models.quote import Quote, QuoteField
from app.models.trip import Trip
from app.models.workspace import Workspace
from app.permissions import RequestContext
from app.services import audit, merge, recompute
from app.services.contracts import RecommendationResult, flag_fingerprint
from app.services.money import format_usd
from app.services.operators import match_operator
from app.services.storage import Storage, StorageError, sha256_hex


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


_SUFFIXES: Final[dict[DocumentKind, str]] = {
    DocumentKind.PDF: ".pdf",
    DocumentKind.EMAIL: ".eml",
    DocumentKind.SMS: ".txt",
    DocumentKind.WHATSAPP: ".txt",
    DocumentKind.TEXT: ".txt",
}
_IMAGE_SUFFIXES: Final[dict[str, str]] = {"image/png": ".png", "image/jpeg": ".jpg"}
_DOC_AUDITED: Final = (
    "trip_id",
    "quote_id",
    "parent_id",
    "operator_id",
    "kind",
    "channel",
    "original_filename",
    "media_type",
    "size_bytes",
    "sha256",
    "page_count",
    "sender",
    "subject",
    "received_at",
    "extraction_status",
)

log = logging.getLogger("app.pipeline")


def _suffix(kind: DocumentKind, media_type: str) -> str:
    if kind is DocumentKind.IMAGE:
        return _IMAGE_SUFFIXES.get(media_type, "")
    return _SUFFIXES.get(kind, "")


def _filename(name: str | None) -> str | None:
    if not name:
        return None
    return name.replace("\\", "/").rsplit("/", 1)[-1][:255] or None


def _pages_json(doc: DocumentInput) -> list[dict[str, Any]]:
    return [{"page": p.page, "text": p.text} for p in doc.pages]


def _describe(doc: SourceDocument) -> str:
    name = doc.original_filename or f"{merge.channel_label(doc.channel)} message"
    if doc.page_count:
        return f"{name} ({doc.page_count} page{'s' if doc.page_count != 1 else ''})"
    return name


def _new_document(
    db: Session,
    ctx: RequestContext,
    trip: Trip,
    loaded: LoadedDocument,
    data: bytes,
    *,
    filename: str | None,
    storage: Storage,
    now: datetime,
    parent: SourceDocument | None = None,
    operator_id: uuid.UUID | None = None,
    quote_id: uuid.UUID | None = None,
) -> SourceDocument:
    doc_in = loaded.input
    stored = storage.put(
        trip.workspace_id,
        data,
        suffix=_suffix(doc_in.kind, doc_in.media_type),
        content_type=doc_in.media_type,
    )
    doc = SourceDocument(
        workspace_id=trip.workspace_id,
        trip_id=trip.id,
        quote_id=quote_id,
        parent_id=parent.id if parent is not None else None,
        operator_id=operator_id,
        uploaded_by_id=ctx.user_id,
        kind=doc_in.kind,
        channel=doc_in.channel,
        original_filename=_filename(filename),
        media_type=doc_in.media_type,
        storage_key=stored.key,
        size_bytes=stored.size,
        sha256=stored.sha256,
        page_count=loaded.page_count,
        is_scanned=doc_in.is_scanned,
        text_pages=_pages_json(doc_in),
        sender=(doc_in.sender or (parent.sender if parent else None) or None),
        subject=(doc_in.subject or (parent.subject if parent else None) or None),
        received_at=doc_in.received_at or (parent.received_at if parent else None) or now,
        extraction_status=ExtractionStatus.PENDING,
    )
    if doc.sender:
        doc.sender = doc.sender[:320]
    if doc.subject:
        doc.subject = doc.subject[:500]
    db.add(doc)
    db.flush()
    return doc


def _existing(db: Session, trip: Trip, sha: str) -> SourceDocument | None:
    return db.scalars(
        select(SourceDocument).where(
            SourceDocument.trip_id == trip.id, SourceDocument.sha256 == sha
        )
    ).first()


def _attachments(
    db: Session,
    ctx: RequestContext,
    trip: Trip,
    parent: SourceDocument,
    attachments: tuple[Attachment, ...],
    *,
    settings: Settings,
    storage: Storage,
    now: datetime,
) -> list[SourceDocument]:
    children: list[SourceDocument] = []
    for att in attachments:
        if _existing(db, trip, sha256_hex(att.data)) is not None:
            continue
        try:
            if len(att.data) > settings.max_upload_bytes:
                raise Unprocessable("Attachment too large", code="payload_too_large")
            loaded = load_pdf(att.data, max_pages=settings.max_pdf_pages)
        except DomainError as exc:
            log_event(
                db,
                workspace_id=trip.workspace_id,
                trip_id=trip.id,
                source_document_id=parent.id,
                step=ProcessingStep.INGEST,
                level=EventLevel.WARN,
                message=f"Skipped attachment {att.filename or 'PDF'}: {exc.detail}",
            )
            continue
        loaded = LoadedDocument(
            input=_with_channel(loaded.input, DocumentChannel.EMAIL),
            page_count=loaded.page_count,
        )
        child = _new_document(
            db,
            ctx,
            trip,
            loaded,
            att.data,
            filename=att.filename,
            storage=storage,
            now=now,
            parent=parent,
            operator_id=parent.operator_id,
        )
        children.append(child)
        log_event(
            db,
            workspace_id=trip.workspace_id,
            trip_id=trip.id,
            source_document_id=child.id,
            step=ProcessingStep.INGEST,
            message=f"Found attachment {_describe(child)} in {_describe(parent)}",
        )
    return children


def _with_channel(doc: DocumentInput, channel: DocumentChannel) -> DocumentInput:
    return dataclasses.replace(doc, channel=channel)


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
    if trip.workspace_id != ctx.workspace_id:
        raise NotFound("Trip not found")
    now = utcnow()
    explicit_quote = merge.explicit_quote(db, trip, cmd.quote_id) if cmd.quote_id else None
    explicit_op = merge.explicit_operator(db, trip, cmd.operator_id) if cmd.operator_id else None
    if (
        explicit_quote is not None
        and explicit_op is not None
        and explicit_quote.operator_id != explicit_op.id
    ):
        raise Unprocessable("quote_id belongs to a different operator", code="operator_mismatch")

    loaded = load_document(
        data=cmd.data,
        text=cmd.text,
        filename=cmd.filename,
        channel=cmd.channel,
        sender=cmd.sender,
        subject=cmd.subject,
        received_at=cmd.received_at,
        settings=settings,
    )
    data = cmd.data if cmd.data is not None else (cmd.text or "").encode("utf-8")
    duplicate = _existing(db, trip, sha256_hex(data))
    if duplicate is not None:
        quote = db.get(Quote, duplicate.quote_id) if duplicate.quote_id else None
        return IngestOutcome(
            document=duplicate, quote=quote, created_quote=False, duplicate=True, queued=False
        )

    doc = _new_document(
        db,
        ctx,
        trip,
        loaded,
        data,
        filename=cmd.filename,
        storage=storage,
        now=now,
        operator_id=explicit_op.id if explicit_op else None,
        quote_id=explicit_quote.id if explicit_quote else None,
    )
    log_event(
        db,
        workspace_id=trip.workspace_id,
        trip_id=trip.id,
        source_document_id=doc.id,
        step=ProcessingStep.INGEST,
        message=f"Received {_describe(doc)} via {merge.channel_label(doc.channel)}",
    )
    children = _attachments(
        db, ctx, trip, doc, loaded.attachments, settings=settings, storage=storage, now=now
    )
    audit.record(
        db,
        ctx,
        "document.ingest",
        doc,
        None,
        {
            **audit.snapshot(doc, _DOC_AUDITED),
            "children": [str(c.id) for c in children],
        },
        trip_id=trip.id,
    )
    db.flush()

    if settings.pipeline_mode is PipelineMode.BACKGROUND:
        return IngestOutcome(
            document=doc,
            quote=explicit_quote,
            created_quote=False,
            duplicate=False,
            queued=True,
        )
    result = process_source_document(
        db, doc.id, settings=settings, storage=storage, extractor=extractor, now=now
    )
    quote, created = result.quote, result.created_quote
    for child in children:
        child_result = process_source_document(
            db,
            child.id,
            settings=settings,
            storage=storage,
            extractor=extractor,
            now=now,
            quote_id=child.quote_id or (quote.id if quote is not None else None),
        )
        if quote is None and child_result.quote is not None:
            quote, created = child_result.quote, child_result.created_quote
    return IngestOutcome(
        document=result.document, quote=quote, created_quote=created, duplicate=False, queued=False
    )


# --------------------------------------------------------------------------- processing


def _extraction_context(db: Session, trip: Trip, operator_hint: str | None) -> ExtractionContext:
    names = db.scalars(
        select(Operator.name)
        .where(Operator.workspace_id == trip.workspace_id, Operator.is_archived.is_(False))
        .order_by(Operator.name)
    )
    legs = tuple(
        LegContext(
            origin_icao=leg.origin_icao,
            destination_icao=leg.destination_icao,
            depart_local=leg.depart_local,
        )
        for leg in sorted(trip.legs, key=lambda leg: leg.seq)
    )
    workspace = db.get(Workspace, trip.workspace_id)
    return ExtractionContext(
        legs=legs,
        pax=trip.pax,
        known_operator_names=tuple(names),
        base_currency=workspace.base_currency if workspace else "USD",
        default_year=legs[0].depart_local.year if legs else None,
        trip_reference=trip.reference,
        operator_hint=operator_hint,
    )


def _reload(doc: SourceDocument, storage: Storage, settings: Settings) -> DocumentInput:
    data = storage.open(doc.storage_key, workspace_id=doc.workspace_id)
    loaded = load_document(
        data=data,
        text=None,
        filename=doc.original_filename,
        channel=doc.channel,
        sender=doc.sender,
        subject=doc.subject,
        received_at=doc.received_at,
        settings=settings,
    )
    return loaded.input


def _document_flag(db: Session, doc: SourceDocument, flag_type: FlagType, message: str) -> Flag:
    """A document-level flag (no quote yet), deduplicated per document."""
    fingerprint = flag_fingerprint(flag_type, str(doc.id))
    flag = db.scalars(
        select(Flag).where(
            Flag.trip_id == doc.trip_id,
            Flag.quote_id.is_(None),
            Flag.fingerprint == fingerprint,
        )
    ).first()
    severity = (
        FlagSeverity.CRITICAL if flag_type is FlagType.EXTRACTION_FAILED else FlagSeverity.WARNING
    )
    if flag is None:
        flag = Flag(
            workspace_id=doc.workspace_id,
            trip_id=doc.trip_id,
            quote_id=None,
            source_document_id=doc.id,
            fingerprint=fingerprint,
            data_hash="0" * 64,
            type=flag_type,
            severity=severity,
            blocking=True,
            message=message[:500],
            details={"kind": flag_type.value, "document": doc.original_filename},
            status=FlagStatus.OPEN,
        )
        db.add(flag)
    else:
        flag.message = message[:500]
        flag.status = FlagStatus.OPEN
        flag.resolution = None
        flag.resolved_at = None
        flag.resolved_by_id = None
    db.flush()
    return flag


def _clear_document_flags(db: Session, doc: SourceDocument, now: datetime) -> None:
    for flag in db.scalars(
        select(Flag).where(
            Flag.trip_id == doc.trip_id,
            Flag.quote_id.is_(None),
            Flag.source_document_id == doc.id,
            Flag.status == FlagStatus.OPEN,
        )
    ):
        flag.status = FlagStatus.RESOLVED
        flag.resolution = FlagResolution.AUTO_CLEARED
        flag.resolved_at = now


def _quote_without_extraction(
    db: Session,
    trip: Trip,
    doc: SourceDocument,
    *,
    quote_id: uuid.UUID | None,
    operator_id: uuid.UUID | None,
) -> Quote | None:
    """The quote an unreadable document belongs to, when the broker or sender says so."""
    if quote_id is not None:
        return merge.explicit_quote(db, trip, quote_id)
    op: Operator | None = None
    if operator_id is not None:
        op = merge.explicit_operator(db, trip, operator_id)
    else:
        match = match_operator(db, trip.workspace_id, sender=doc.sender, name=None)
        op = match.operator if match is not None else None
    if op is None:
        return None
    return db.scalars(
        select(Quote)
        .where(
            Quote.trip_id == trip.id,
            Quote.operator_id == op.id,
            Quote.status == QuoteStatus.ACTIVE,
        )
        .order_by(Quote.created_at.desc())
    ).first()


def _log(
    db: Session,
    doc: SourceDocument,
    step: ProcessingStep,
    message: str,
    *,
    level: EventLevel = EventLevel.INFO,
    quote_id: uuid.UUID | None = None,
    data: dict[str, Any] | None = None,
) -> None:
    log_event(
        db,
        workspace_id=doc.workspace_id,
        trip_id=doc.trip_id,
        step=step,
        message=message,
        level=level,
        quote_id=quote_id or doc.quote_id,
        source_document_id=doc.id,
        data=data,
    )


def _money_text(cents: int | None) -> str:
    return "unknown" if cents is None else format_usd(cents)


def _log_outcome(
    db: Session,
    doc: SourceDocument,
    quote: Quote,
    operator_name: str,
    result: RecommendationResult | None,
) -> None:
    if quote.is_fully_priced:
        total = f"true cost {_money_text(quote.known_total_cents)} (fully priced)"
    else:
        total = (
            f"true cost {_money_text(quote.known_total_cents)}+ "
            f"(up to {_money_text(quote.upper_total_cents)})"
        )
    _log(db, doc, ProcessingStep.NORMALIZE, f"{operator_name}: {total}", quote_id=quote.id)
    blocking = db.scalars(
        select(Flag.message).where(
            Flag.quote_id == quote.id, Flag.status == FlagStatus.OPEN, Flag.blocking.is_(True)
        )
    ).all()
    if blocking:
        _log(
            db,
            doc,
            ProcessingStep.VALIDATE,
            f"{operator_name}: {len(blocking)} blocking flag"
            f"{'s' if len(blocking) != 1 else ''}: " + "; ".join(blocking),
            level=EventLevel.WARN,
            quote_id=quote.id,
        )
    else:
        _log(
            db,
            doc,
            ProcessingStep.VALIDATE,
            f"{operator_name}: no blocking flags",
            level=EventLevel.OK,
            quote_id=quote.id,
        )
    if result is None:
        return
    _log(
        db,
        doc,
        ProcessingStep.COMPARE,
        f"Compared {len(result.ranking)} quote{'s' if len(result.ranking) != 1 else ''}",
    )
    if result.recommended_quote_id is None:
        _log(
            db, doc, ProcessingStep.RECOMMENDATION, "No quote is eligible for a recommendation yet"
        )
        return
    rec_quote = db.get(Quote, result.recommended_quote_id)
    rec_op = db.get(Operator, rec_quote.operator_id) if rec_quote else None
    ranked = result.for_quote(result.recommended_quote_id)
    fit = ranked.breakdown.fit if ranked else None
    _log(
        db,
        doc,
        ProcessingStep.RECOMMENDATION,
        f"Recommended {rec_op.name if rec_op else 'quote'} (fit {fit})",
        level=EventLevel.OK,
        quote_id=result.recommended_quote_id,
    )


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
    now = now or utcnow()
    doc = db.get(SourceDocument, doc_id)
    if doc is None:
        raise NotFound("Source document not found")
    trip = db.get(Trip, doc.trip_id)
    if trip is None:  # pragma: no cover - FK guarantees it
        raise NotFound("Trip not found")
    workspace = db.get(Workspace, trip.workspace_id)
    threshold = workspace.review_threshold if workspace else 75
    quote_id = quote_id or doc.quote_id
    operator_id = operator_id or doc.operator_id
    started = time.monotonic()
    doc.extraction_status = ExtractionStatus.PROCESSING
    doc.extraction_error = None
    db.flush()

    hint: str | None = None
    if operator_id is not None:
        hint_op = db.get(Operator, operator_id)
        hint = (
            hint_op.name
            if hint_op is not None and hint_op.workspace_id == trip.workspace_id
            else None
        )

    try:
        doc_in = _reload(doc, storage, settings)
        attempt = run_extractor(extractor, doc_in, _extraction_context(db, trip, hint))
    except DocumentUnreadable as exc:
        return _unreadable(
            db,
            trip,
            doc,
            settings=settings,
            started=started,
            now=now,
            quote_id=quote_id,
            operator_id=operator_id,
            reason=exc.reason,
        )
    except (ExtractorError, DomainError, StorageError) as exc:
        code = error_code(exc) if isinstance(exc, ExtractorError) else "unreadable"
        detail = exc.detail if isinstance(exc, DomainError) else str(exc)
        return _failed(
            db,
            trip,
            doc,
            f"Extraction failed ({code}): {detail}",
            started=started,
            now=now,
            quote_id=quote_id,
            operator_id=operator_id,
        )

    if attempt.fallback_error is not None:
        _log(
            db,
            doc,
            ProcessingStep.EXTRACT,
            f"{extractor.name} extractor failed ({error_code(attempt.fallback_error)}); "
            f"used {attempt.used}",
            level=EventLevel.WARN,
        )
    result, prov = provenance.verify(attempt.result, doc_in)
    doc.extraction_result = result.model_dump(mode="json")
    doc.extractor = attempt.used[:32]
    doc.extractor_version = result.extractor_version[:64]
    doc.extractor_model = result.model[:64] if result.model else None
    doc.extraction_usage = dict(result.usage) if result.usage else None
    doc.intent = DocumentIntent(result.intent)
    _log(
        db,
        doc,
        ProcessingStep.EXTRACT,
        f"Extracted {len(result.fields)} fields and {len(result.fees)} fees from "
        f"{_describe(doc)} with {attempt.used}"
        + (f"; {len(prov.unverified)} snippet(s) unverified" if prov.unverified else ""),
        level=EventLevel.OK,
        data={
            "verified": prov.verified,
            "pages_corrected": prov.pages_corrected,
            "unverified": prov.unverified,
            "warnings": result.warnings,
        },
    )
    return _merge_and_recompute(
        db,
        trip,
        doc,
        result,
        threshold=threshold,
        started=started,
        now=now,
        quote_id=quote_id,
        operator_id=operator_id,
    )


def _merge_and_recompute(
    db: Session,
    trip: Trip,
    doc: SourceDocument,
    result: ExtractionResult,
    *,
    threshold: int,
    started: float,
    now: datetime,
    quote_id: uuid.UUID | None,
    operator_id: uuid.UUID | None,
) -> ProcessResult:
    resolution = merge.resolve_quote(
        db, trip, doc, result, quote_id=quote_id, operator_id=operator_id, now=now
    )
    op_name = resolution.operator.name if resolution.operator else "Unknown operator"
    if resolution.created_operator:
        _log(db, doc, ProcessingStep.NORMALIZE, f"Created operator {op_name} from the document")
    quote = resolution.quote
    if quote is None:
        _log(
            db,
            doc,
            ProcessingStep.NORMALIZE,
            f"{op_name} declined the request",
            level=EventLevel.WARN,
        )
        _finish(db, doc, ExtractionStatus.SUCCEEDED, started, now)
        return ProcessResult(document=doc, quote=None, created_quote=False)

    doc.quote_id = quote.id
    report = merge.merge_result(db, quote, doc, result, review_threshold=threshold, now=now)
    verb = "New quote from" if resolution.created_quote else "Merged into the quote from"
    _log(
        db,
        doc,
        ProcessingStep.NORMALIZE,
        f"{verb} {op_name}: {len(report.inserted)} new, {len(report.corroborated)} corroborated, "
        f"{len(report.superseded)} revised, {len(report.conflicts)} in conflict",
        quote_id=quote.id,
        data={
            "inserted": report.inserted,
            "replaced": report.replaced,
            "superseded": report.superseded,
            "corroborated": report.corroborated,
            "conflicts": report.conflicts,
            "history_only": report.history_only,
        },
    )
    for line in report.events:
        level = EventLevel.WARN if line.startswith("Conflict") else EventLevel.INFO
        _log(db, doc, ProcessingStep.NORMALIZE, line, level=level, quote_id=quote.id)
    _clear_document_flags(db, doc, now)
    _finish(db, doc, ExtractionStatus.SUCCEEDED, started, now)
    rec = recompute.recompute_trip(db, trip, now=now)
    _log_outcome(db, doc, quote, op_name, rec)
    return ProcessResult(document=doc, quote=quote, created_quote=resolution.created_quote)


def _finish(
    db: Session, doc: SourceDocument, status: ExtractionStatus, started: float, now: datetime
) -> None:
    doc.extraction_status = status
    doc.processing_ms = int((time.monotonic() - started) * 1000)
    db.flush()


def _attach_issue(
    db: Session,
    trip: Trip,
    doc: SourceDocument,
    *,
    flag_type: FlagType,
    message: str,
    now: datetime,
    quote_id: uuid.UUID | None,
    operator_id: uuid.UUID | None,
) -> Quote | None:
    """Attach the document to its quote (a quote-level flag via recompute), or raise a
    document-level flag when no quote is known."""
    try:
        quote = _quote_without_extraction(db, trip, doc, quote_id=quote_id, operator_id=operator_id)
    except NotFound:
        quote = None
    if quote is None:
        _document_flag(db, doc, flag_type, message)
        return None
    doc.quote_id = quote.id
    db.flush()
    recompute.recompute_trip(db, trip, now=now)
    return quote


def _unreadable(
    db: Session,
    trip: Trip,
    doc: SourceDocument,
    *,
    settings: Settings,
    started: float,
    now: datetime,
    quote_id: uuid.UUID | None,
    operator_id: uuid.UUID | None,
    reason: str,
) -> ProcessResult:
    if doc.kind is DocumentKind.EMAIL:
        # An empty email body; any PDF attachments are processed as their own documents.
        _log(db, doc, ProcessingStep.EXTRACT, f"{_describe(doc)} has no text to read")
        _finish(db, doc, ExtractionStatus.SUCCEEDED, started, now)
        return ProcessResult(document=doc, quote=None, created_quote=False)
    message = (
        f"{_describe(doc)} is scanned and no OCR is configured; enter the values by hand "
        "or configure the Claude extractor and reprocess"
    )
    _finish(db, doc, ExtractionStatus.NEEDS_MANUAL, started, now)
    _log(db, doc, ProcessingStep.EXTRACT, message, level=EventLevel.WARN, data={"reason": reason})
    quote = _attach_issue(
        db,
        trip,
        doc,
        flag_type=FlagType.OCR_UNAVAILABLE,
        message=message,
        now=now,
        quote_id=quote_id,
        operator_id=operator_id,
    )
    return ProcessResult(document=doc, quote=quote, created_quote=False)


def _failed(
    db: Session,
    trip: Trip,
    doc: SourceDocument,
    message: str,
    *,
    started: float,
    now: datetime,
    quote_id: uuid.UUID | None,
    operator_id: uuid.UUID | None,
) -> ProcessResult:
    doc.extraction_error = message[:2000]
    _finish(db, doc, ExtractionStatus.FAILED, started, now)
    _log(db, doc, ProcessingStep.EXTRACT, message, level=EventLevel.ERROR)
    quote = _attach_issue(
        db,
        trip,
        doc,
        flag_type=FlagType.EXTRACTION_FAILED,
        message=message,
        now=now,
        quote_id=quote_id,
        operator_id=operator_id,
    )
    return ProcessResult(document=doc, quote=quote, created_quote=False)


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
    with session_factory() as db:
        set_workspace(db, workspace_id)
        try:
            result = process_source_document(
                db, doc_id, settings=settings, storage=storage, extractor=extractor
            )
            children = db.scalars(
                select(SourceDocument)
                .where(
                    SourceDocument.parent_id == doc_id,
                    SourceDocument.extraction_status == ExtractionStatus.PENDING,
                )
                .order_by(SourceDocument.created_at, SourceDocument.id)
            ).all()
            for child in children:
                process_source_document(
                    db,
                    child.id,
                    settings=settings,
                    storage=storage,
                    extractor=extractor,
                    quote_id=child.quote_id or (result.quote.id if result.quote else None),
                )
            db.commit()
        except Exception as exc:
            log.exception("background processing of %s failed", doc_id)
            db.rollback()
            doc = db.get(SourceDocument, doc_id)
            if doc is None:
                return
            doc.extraction_status = ExtractionStatus.FAILED
            doc.extraction_error = f"Processing failed: {type(exc).__name__}"
            _log(db, doc, ProcessingStep.EXTRACT, doc.extraction_error, level=EventLevel.ERROR)
            db.commit()


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
    if doc.workspace_id != ctx.workspace_id:
        raise NotFound("Source document not found")
    before = audit.snapshot(doc, _DOC_AUDITED)
    _log(db, doc, ProcessingStep.INGEST, f"Reprocessing {_describe(doc)}")
    result = process_source_document(
        db, doc.id, settings=settings, storage=storage, extractor=extractor
    )
    old, new = audit.diff(before, audit.snapshot(result.document, _DOC_AUDITED))
    audit.record(db, ctx, "document.reprocess", doc, old, new, trip_id=doc.trip_id)
    db.flush()
    return result


def _restore_previous(db: Session, removed: QuoteField) -> None:
    """Before deleting a row, make the value it replaced current again (if it was
    current) and repoint rows that referenced it."""
    older = list(
        db.scalars(
            select(QuoteField)
            .where(QuoteField.superseded_by_id == removed.id)
            .order_by(QuoteField.created_at.desc(), QuoteField.id)
        )
    )
    if not removed.is_current:
        for row in older:
            row.superseded_by_id = removed.superseded_by_id
        db.flush()
        return
    restored = next((r for r in older if r.source_document_id != removed.source_document_id), None)
    for row in older:
        row.superseded_by_id = None if row is restored else (restored.id if restored else None)
    removed.is_current = False
    db.flush()
    if restored is not None:
        restored.is_current = True
        db.flush()


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
    if doc.workspace_id != ctx.workspace_id:
        raise NotFound("Source document not found")
    if (quote_id is None) == (operator_id is None):
        raise Unprocessable("Pass exactly one of quote_id or operator_id", code="invalid_input")
    trip = db.get(Trip, doc.trip_id)
    if trip is None:  # pragma: no cover
        raise NotFound("Trip not found")
    before = audit.snapshot(doc, _DOC_AUDITED)
    now = utcnow()
    target: Quote | None = merge.explicit_quote(db, trip, quote_id) if quote_id else None
    operator = (
        db.get(Operator, target.operator_id)
        if target is not None
        else merge.explicit_operator(db, trip, operator_id)  # type: ignore[arg-type]
    )
    if operator is None:  # pragma: no cover
        raise NotFound("Operator not found")
    if target is not None and target.id == doc.quote_id:
        return doc

    old_quote_id = doc.quote_id
    rows = list(db.scalars(select(QuoteField).where(QuoteField.source_document_id == doc.id)))
    locked = [r.key for r in rows if r.locked]
    for row in rows:
        _restore_previous(db, row)
    for row in rows:
        db.delete(row)
    db.flush()

    doc.quote_id = target.id if target is not None else None
    doc.operator_id = operator.id
    db.flush()
    if doc.extraction_result:
        result = ExtractionResult.model_validate(doc.extraction_result)
        workspace = db.get(Workspace, trip.workspace_id)
        threshold = workspace.review_threshold if workspace else settings.default_review_threshold
        resolution = merge.resolve_quote(
            db,
            trip,
            doc,
            result,
            quote_id=target.id if target is not None else None,
            operator_id=operator.id,
            now=now,
        )
        if resolution.quote is not None:
            doc.quote_id = resolution.quote.id
            merge.merge_result(
                db, resolution.quote, doc, result, review_threshold=threshold, now=now
            )
    elif target is None:
        target = _quote_without_extraction(db, trip, doc, quote_id=None, operator_id=operator.id)
        doc.quote_id = target.id if target is not None else None
    if old_quote_id is not None and old_quote_id != doc.quote_id:
        _withdraw_if_empty(db, old_quote_id)
    db.flush()
    after = audit.snapshot(doc, _DOC_AUDITED)
    old, new = audit.diff(before, after)
    if locked:
        new["discarded_reviews"] = locked
    audit.record(db, ctx, "document.move", doc, old, new, trip_id=trip.id)
    _log(
        db,
        doc,
        ProcessingStep.NORMALIZE,
        f"Moved {_describe(doc)} to {operator.name}",
        quote_id=doc.quote_id,
    )
    recompute.recompute_trip(db, trip, now=now, ctx=ctx)
    return doc


def _withdraw_if_empty(db: Session, quote_id: uuid.UUID) -> None:
    quote = db.get(Quote, quote_id)
    if quote is None:
        return
    has_docs = db.scalars(
        select(SourceDocument.id).where(SourceDocument.quote_id == quote_id)
    ).first()
    has_fields = db.scalars(select(QuoteField.id).where(QuoteField.quote_id == quote_id)).first()
    if has_docs is None and has_fields is None and quote.status is QuoteStatus.ACTIVE:
        quote.status = QuoteStatus.WITHDRAWN
