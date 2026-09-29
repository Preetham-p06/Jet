"""Field review: verify, accept, edit, reset (all optimistic-locked), history and queue."""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from sqlalchemy.orm import Session

from app.api.routes._views import field_out
from app.deps import AnyUser, DbSession, Reviewer
from app.errors import Conflict
from app.models.quote import QuoteField
from app.models.trip import Trip
from app.permissions import RequestContext, get_owned
from app.schemas.common import Page
from app.schemas.quote import (
    FieldAcceptIn,
    FieldEditIn,
    FieldOut,
    FieldVersionIn,
    ReviewQueueItemOut,
)
from app.services import review

router = APIRouter(tags=["review"])


def _load(db: Session, field_id: uuid.UUID, ctx: RequestContext, version: int) -> QuoteField:
    """The field, with the optimistic-lock check done before any service call."""
    field = get_owned(db, QuoteField, field_id, ctx)
    if field.version != version:
        raise Conflict("This record was changed by someone else; reload", code="stale_version")
    return field


def _done(db: Session, field: QuoteField) -> FieldOut:
    db.commit()
    db.refresh(field)
    return field_out(field)


@router.get(
    "/trips/{trip_id}/review-queue",
    summary="Low-confidence unlocked fields and blocking flags, by money impact",
)
def get_review_queue(trip_id: uuid.UUID, ctx: AnyUser, db: DbSession) -> Page[ReviewQueueItemOut]:
    items = review.review_queue(db, ctx, get_owned(db, Trip, trip_id, ctx))
    return Page(items=items, total=len(items))


@router.get("/fields/{field_id}/history", summary="Every revision of the field, newest first")
def get_field_history(field_id: uuid.UUID, ctx: AnyUser, db: DbSession) -> Page[FieldOut]:
    rows = review.field_history(db, get_owned(db, QuoteField, field_id, ctx))
    return Page(items=[field_out(f) for f in rows], total=len(rows))


@router.post("/fields/{field_id}/verify", summary="Mark verified and lock (409 on stale version)")
def verify_field(
    field_id: uuid.UUID, body: FieldVersionIn, ctx: Reviewer, db: DbSession
) -> FieldOut:
    field = _load(db, field_id, ctx, body.version)
    return _done(db, review.verify_field(db, ctx, field, version=body.version))


@router.post("/fields/{field_id}/accept", summary="Accept as-is and lock (409 on stale version)")
def accept_field(
    field_id: uuid.UUID, body: FieldAcceptIn, ctx: Reviewer, db: DbSession
) -> FieldOut:
    field = _load(db, field_id, ctx, body.version)
    return _done(db, review.accept_field(db, ctx, field, version=body.version, note=body.note))


@router.patch("/fields/{field_id}", summary="Edit the value and lock (409 on stale version)")
def edit_field(field_id: uuid.UUID, body: FieldEditIn, ctx: Reviewer, db: DbSession) -> FieldOut:
    field = _load(db, field_id, ctx, body.version)
    updated = review.edit_field(
        db, ctx, field, version=body.version, value=body.value, note=body.note
    )
    return _done(db, updated)


@router.post("/fields/{field_id}/reset", summary="Back to the extracted value, unlocked")
def reset_field(
    field_id: uuid.UUID, body: FieldVersionIn, ctx: Reviewer, db: DbSession
) -> FieldOut:
    field = _load(db, field_id, ctx, body.version)
    return _done(db, review.reset_field(db, ctx, field, version=body.version))
