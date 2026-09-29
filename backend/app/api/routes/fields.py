"""Field review: verify, accept, edit, reset (all optimistic-locked), history and queue."""

from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.deps import AnyUser, DbSession, Reviewer
from app.errors import not_implemented
from app.models.quote import QuoteField
from app.models.trip import Trip
from app.permissions import get_owned
from app.schemas.common import Page
from app.schemas.quote import (
    FieldAcceptIn,
    FieldEditIn,
    FieldOut,
    FieldVersionIn,
    ReviewQueueItemOut,
)

router = APIRouter(tags=["review"])


@router.get(
    "/trips/{trip_id}/review-queue",
    summary="Low-confidence unlocked fields and blocking flags, by money impact",
)
def get_review_queue(trip_id: uuid.UUID, ctx: AnyUser, db: DbSession) -> Page[ReviewQueueItemOut]:
    get_owned(db, Trip, trip_id, ctx)
    not_implemented("Review queue")


@router.get("/fields/{field_id}/history", summary="Every revision of the field, newest first")
def get_field_history(field_id: uuid.UUID, ctx: AnyUser, db: DbSession) -> Page[FieldOut]:
    get_owned(db, QuoteField, field_id, ctx)
    not_implemented("Field history")


@router.post("/fields/{field_id}/verify", summary="Mark verified and lock (409 on stale version)")
def verify_field(
    field_id: uuid.UUID, body: FieldVersionIn, ctx: Reviewer, db: DbSession
) -> FieldOut:
    get_owned(db, QuoteField, field_id, ctx)
    not_implemented("Field verify")


@router.post("/fields/{field_id}/accept", summary="Accept as-is and lock (409 on stale version)")
def accept_field(
    field_id: uuid.UUID, body: FieldAcceptIn, ctx: Reviewer, db: DbSession
) -> FieldOut:
    get_owned(db, QuoteField, field_id, ctx)
    not_implemented("Field accept")


@router.patch("/fields/{field_id}", summary="Edit the value and lock (409 on stale version)")
def edit_field(field_id: uuid.UUID, body: FieldEditIn, ctx: Reviewer, db: DbSession) -> FieldOut:
    get_owned(db, QuoteField, field_id, ctx)
    not_implemented("Field edit")


@router.post("/fields/{field_id}/reset", summary="Back to the extracted value, unlocked")
def reset_field(
    field_id: uuid.UUID, body: FieldVersionIn, ctx: Reviewer, db: DbSession
) -> FieldOut:
    get_owned(db, QuoteField, field_id, ctx)
    not_implemented("Field reset")
