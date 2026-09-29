"""Quote ingest and source documents."""

from __future__ import annotations

import re
import uuid
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    Request,
    Response,
    UploadFile,
    status,
)
from pydantic import AwareDatetime
from sqlalchemy import func, select

from app.api.params import PageParams
from app.api.routes._views import quote_summaries
from app.deps import AnyUser, AppSettings, DbSession, Reviewer, StorageDep, get_extractor
from app.errors import NotFound, PayloadTooLarge, Unprocessable
from app.extraction.base import Extractor
from app.models.document import SourceDocument
from app.models.enums import DocumentChannel
from app.models.operator import Operator
from app.models.quote import Quote
from app.models.trip import Trip
from app.permissions import get_owned, scoped
from app.schemas.common import Page
from app.schemas.document import (
    DocumentMoveIn,
    IngestOut,
    SourceDocumentDetailOut,
    SourceDocumentOut,
    TextPage,
)
from app.services import pipeline
from app.services.storage import StorageError

router = APIRouter(tags=["ingest"])

ExtractorDep = Annotated[Extractor, Depends(get_extractor)]

_UNSAFE_FILENAME = re.compile(r"[^A-Za-z0-9._ -]+")


@router.post(
    "/trips/{trip_id}/quotes/ingest",
    status_code=status.HTTP_201_CREATED,
    responses={202: {"model": IngestOut, "description": "Queued (PIPELINE_MODE=background)"}},
    summary="Upload a quote file or paste text; 201 inline, 202 when queued",
)
def ingest_quote(
    trip_id: uuid.UUID,
    ctx: AnyUser,
    db: DbSession,
    request: Request,
    response: Response,
    background: BackgroundTasks,
    settings: AppSettings,
    storage: StorageDep,
    extractor: ExtractorDep,
    file: Annotated[UploadFile | None, File(description="PDF, .eml, .txt, PNG or JPEG")] = None,
    text: Annotated[str | None, Form(max_length=200_000)] = None,
    channel: Annotated[DocumentChannel | None, Form()] = None,
    sender: Annotated[str | None, Form(max_length=320)] = None,
    subject: Annotated[str | None, Form(max_length=500)] = None,
    received_at: Annotated[AwareDatetime | None, Form()] = None,
    operator_id: Annotated[uuid.UUID | None, Form()] = None,
    quote_id: Annotated[uuid.UUID | None, Form()] = None,
) -> IngestOut:
    trip = get_owned(db, Trip, trip_id, ctx)
    upload = file if file is not None and (file.filename or file.size) else None
    has_text = text is not None and text.strip() != ""
    if (upload is None) == (not has_text):
        raise Unprocessable(
            "Send exactly one of a file or pasted text",
            code="invalid_input",
            fields={"file": "file or text required, not both"},
        )
    # Explicit targets must be the caller's own rows (404 otherwise, never 403).
    if quote_id is not None:
        quote = get_owned(db, Quote, quote_id, ctx)
        if quote.trip_id != trip.id:
            raise NotFound("Quote not found")
    if operator_id is not None:
        get_owned(db, Operator, operator_id, ctx)

    data: bytes | None = None
    if upload is not None:
        limit = settings.max_upload_bytes
        data = upload.file.read(limit + 1)
        if len(data) > limit:
            raise PayloadTooLarge(f"Files are limited to {settings.max_upload_mb} MB")
        if not data:
            raise Unprocessable("The upload is empty", code="empty_document")

    cmd = pipeline.IngestCommand(
        data=data,
        filename=upload.filename if upload is not None else None,
        declared_media_type=upload.content_type if upload is not None else None,
        text=text if has_text else None,
        channel=channel,
        sender=sender,
        subject=subject,
        received_at=received_at,
        operator_id=operator_id,
        quote_id=quote_id,
    )
    outcome = pipeline.ingest(
        db, ctx, trip, cmd, settings=settings, storage=storage, extractor=extractor
    )
    db.commit()
    if outcome.queued:
        # PIPELINE_MODE=background: the same function runs after the response,
        # with its own session; the dashboard polls `extraction_status`.
        response.status_code = status.HTTP_202_ACCEPTED
        background.add_task(
            pipeline.run_in_background,
            request.app.state.session_factory,
            ctx.workspace_id,
            outcome.document.id,
            settings=settings,
            storage=storage,
            extractor=extractor,
        )
    db.refresh(outcome.document)
    quote_out = None
    if outcome.quote is not None:
        db.refresh(outcome.quote)
        quote_out = quote_summaries(db, [outcome.quote])[0]
    return IngestOut(
        source_document=SourceDocumentOut.model_validate(outcome.document),
        quote=quote_out,
        created_quote=outcome.created_quote,
        duplicate=outcome.duplicate,
    )


@router.get("/trips/{trip_id}/source-documents", summary="Documents uploaded for a trip")
def list_source_documents(
    trip_id: uuid.UUID, ctx: AnyUser, db: DbSession, page: PageParams
) -> Page[SourceDocumentOut]:
    trip = get_owned(db, Trip, trip_id, ctx)
    stmt = scoped(select(SourceDocument), ctx).where(SourceDocument.trip_id == trip.id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(SourceDocument.created_at, SourceDocument.id)
        .limit(page.limit)
        .offset(page.offset)
    )
    return Page(items=[SourceDocumentOut.model_validate(d) for d in rows], total=total)


@router.get(
    "/source-documents/{document_id}",
    summary="Document detail for status polling, with page texts",
)
def get_source_document(
    document_id: uuid.UUID, ctx: AnyUser, db: DbSession
) -> SourceDocumentDetailOut:
    doc = get_owned(db, SourceDocument, document_id, ctx)
    children = db.scalars(
        scoped(select(SourceDocument), ctx)
        .where(SourceDocument.parent_id == doc.id)
        .order_by(SourceDocument.created_at)
    )
    base = SourceDocumentOut.model_validate(doc).model_dump()
    return SourceDocumentDetailOut(
        **base,
        text_pages=[TextPage.model_validate(p) for p in doc.text_pages or []],
        extraction_usage=doc.extraction_usage,
        children=[SourceDocumentOut.model_validate(c) for c in children],
    )


@router.get(
    "/source-documents/{document_id}/file",
    response_class=Response,
    responses={200: {"content": {"application/octet-stream": {}}}},
    summary="Original bytes, served inline",
)
def get_source_document_file(
    document_id: uuid.UUID, ctx: AnyUser, db: DbSession, storage: StorageDep
) -> Response:
    doc = get_owned(db, SourceDocument, document_id, ctx)
    try:
        data = storage.open(doc.storage_key, workspace_id=ctx.workspace_id)
    except StorageError:
        raise NotFound("File not found") from None
    filename = _UNSAFE_FILENAME.sub("_", doc.original_filename or "document")[:120]
    headers = {
        "Content-Disposition": f'inline; filename="{filename}"',
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, no-store",
    }
    if doc.media_type != "application/pdf":
        # Never let an uploaded file run script in our origin. (Chrome refuses to
        # render PDFs under a sandbox CSP, and a PDF cannot run page script.)
        headers["Content-Security-Policy"] = "sandbox; default-src 'none'"
    return Response(content=data, media_type=doc.media_type, headers=headers)


@router.post("/source-documents/{document_id}/reprocess", summary="Re-extract a document")
def reprocess_source_document(
    document_id: uuid.UUID,
    ctx: Reviewer,
    db: DbSession,
    settings: AppSettings,
    storage: StorageDep,
    extractor: ExtractorDep,
) -> SourceDocumentOut:
    doc = get_owned(db, SourceDocument, document_id, ctx)
    result = pipeline.reprocess_document(
        db, ctx, doc, settings=settings, storage=storage, extractor=extractor
    )
    db.commit()
    db.refresh(result.document)
    return SourceDocumentOut.model_validate(result.document)


@router.post(
    "/source-documents/{document_id}/move",
    summary="Reattach a document to another quote or operator; recomputes both",
)
def move_source_document(
    document_id: uuid.UUID,
    body: DocumentMoveIn,
    ctx: Reviewer,
    db: DbSession,
    settings: AppSettings,
) -> SourceDocumentOut:
    doc = get_owned(db, SourceDocument, document_id, ctx)
    if body.quote_id is not None:
        target = get_owned(db, Quote, body.quote_id, ctx)
        if target.trip_id != doc.trip_id:
            raise NotFound("Quote not found")
    if body.operator_id is not None:
        get_owned(db, Operator, body.operator_id, ctx)
    moved = pipeline.move_document(
        db,
        ctx,
        doc,
        quote_id=body.quote_id,
        operator_id=body.operator_id,
        settings=settings,
    )
    db.commit()
    db.refresh(moved)
    return SourceDocumentOut.model_validate(moved)
