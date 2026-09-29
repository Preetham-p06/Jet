"""Quotes and the trip comparison."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, status
from sqlalchemy import func, select

from app.api.params import PageParams
from app.api.routes._views import comparison, field_out, quote_detail, quote_summaries
from app.deps import AnyUser, DbSession, Reviewer
from app.models.operator import Operator
from app.models.quote import Quote
from app.models.trip import Trip
from app.permissions import get_owned, scoped
from app.schemas.common import Page
from app.schemas.quote import (
    ComparisonOut,
    FieldOut,
    ManualFieldIn,
    QuoteDetailOut,
    QuotePatch,
    QuoteSummaryOut,
)
from app.services import audit, recompute, review

router = APIRouter(tags=["quotes"])

__all__ = ["quote_summaries", "router"]

_AUDITED = ("status", "operator_id")


@router.get("/trips/{trip_id}/quotes", summary="Quote summaries for a trip")
def list_quotes(
    trip_id: uuid.UUID, ctx: AnyUser, db: DbSession, page: PageParams
) -> Page[QuoteSummaryOut]:
    trip = get_owned(db, Trip, trip_id, ctx)
    stmt = scoped(select(Quote), ctx).where(Quote.trip_id == trip.id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    quotes = db.scalars(
        stmt.order_by(Quote.created_at, Quote.id).limit(page.limit).offset(page.offset)
    ).all()
    return Page(items=quote_summaries(db, quotes), total=total)


@router.get(
    "/trips/{trip_id}/comparison",
    summary="Side-by-side fees by category, true cost, confidence, fit and flags",
)
def get_comparison(trip_id: uuid.UUID, ctx: AnyUser, db: DbSession) -> ComparisonOut:
    return comparison(db, ctx, get_owned(db, Trip, trip_id, ctx))


@router.get(
    "/quotes/{quote_id}",
    summary="Fields, fee lines, flags, sources, fit breakdown and eligibility",
)
def get_quote(quote_id: uuid.UUID, ctx: AnyUser, db: DbSession) -> QuoteDetailOut:
    return quote_detail(db, get_owned(db, Quote, quote_id, ctx))


@router.patch("/quotes/{quote_id}", summary="Withdraw or reject a quote, or change its operator")
def update_quote(
    quote_id: uuid.UUID, body: QuotePatch, ctx: Reviewer, db: DbSession
) -> QuoteSummaryOut:
    quote = get_owned(db, Quote, quote_id, ctx)
    before = audit.snapshot(quote, _AUDITED)
    if body.status is not None:
        quote.status = body.status
    if body.operator_id is not None:
        quote.operator_id = get_owned(db, Operator, body.operator_id, ctx).id
    db.flush()
    old, new = audit.diff(before, audit.snapshot(quote, _AUDITED))
    if new:
        audit.record(db, ctx, "quote.update", quote, old, new, trip_id=quote.trip_id)
        recompute.recompute_trip(db, get_owned(db, Trip, quote.trip_id, ctx), ctx=ctx)
    db.commit()
    db.refresh(quote)
    return quote_summaries(db, [quote])[0]


@router.post(
    "/quotes/{quote_id}/fields",
    status_code=status.HTTP_201_CREATED,
    summary="Add a field or fee by hand (edited, locked)",
)
def add_quote_field(
    quote_id: uuid.UUID, body: ManualFieldIn, ctx: Reviewer, db: DbSession
) -> FieldOut:
    quote = get_owned(db, Quote, quote_id, ctx)
    field = review.add_manual_field(
        db, ctx, quote, key=body.key, value=body.value, label=body.label, note=body.note
    )
    db.commit()
    db.refresh(field)
    return field_out(field)
