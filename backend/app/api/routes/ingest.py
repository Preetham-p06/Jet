"""Quote ingest and source documents."""

from __future__ import annotations

import re
import uuid
from typing import Annotated

from fastapi import APIRouter, File, Form, Response, UploadFile, status
from pydantic import AwareDatetime
from sqlalchemy import func, select

from app.api.params import PageParams
from app.deps import AnyUser, DbSession, Reviewer, StorageDep
from app.errors import NotFound, not_implemented
from app.models.document import SourceDocument
from app.models.enums import DocumentChannel
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
from app.services.storage import StorageError

router = APIRouter(tags=["ingest"])

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
    file: Annotated[UploadFile | None, File(description="PDF, .eml, .txt, PNG or JPEG")] = None,
    text: Annotated[str | None, Form(max_length=200_000)] = None,
    channel: Annotated[DocumentChannel | None, Form()] = None,
    sender: Annotated[str | None, Form(max_length=320)] = None,
    subject: Annotated[str | None, Form(max_length=500)] = None,
    received_at: Annotated[AwareDatetime | None, Form()] = None,
    operator_id: Annotated[uuid.UUID | None, Form()] = None,
    quote_id: Annotated[uuid.UUID | None, Form()] = None,
) -> IngestOut:
    get_owned(db, Trip, trip_id, ctx)
    not_implemented("Quote ingest")


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
    document_id: uuid.UUID, ctx: Reviewer, db: DbSession
) -> SourceDocumentOut:
    get_owned(db, SourceDocument, document_id, ctx)
    not_implemented("Document reprocess")


@router.post(
    "/source-documents/{document_id}/move",
    summary="Reattach a document to another quote or operator; recomputes both",
)
def move_source_document(
    document_id: uuid.UUID, body: DocumentMoveIn, ctx: Reviewer, db: DbSession
) -> SourceDocumentOut:
    get_owned(db, SourceDocument, document_id, ctx)
    not_implemented("Document move")
