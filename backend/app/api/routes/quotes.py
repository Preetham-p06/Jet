"""Quotes and the trip comparison."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from fastapi import APIRouter, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.params import PageParams
from app.deps import AnyUser, DbSession, Reviewer
from app.errors import not_implemented
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

router = APIRouter(tags=["quotes"])


def quote_summaries(db: Session, quotes: Sequence[Quote]) -> list[QuoteSummaryOut]:
    """Shared by list and detail views; adds `operator_name`."""
    if not quotes:
        return []
    names = dict(
        db.execute(
            select(Operator.id, Operator.name).where(
                Operator.id.in_({q.operator_id for q in quotes})
            )
        ).all()
    )
    return [QuoteSummaryOut.from_row(q, operator_name=names.get(q.operator_id, "")) for q in quotes]


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
    get_owned(db, Trip, trip_id, ctx)
    not_implemented("Trip comparison")


@router.get(
    "/quotes/{quote_id}",
    summary="Fields, fee lines, flags, sources, fit breakdown and eligibility",
)
def get_quote(quote_id: uuid.UUID, ctx: AnyUser, db: DbSession) -> QuoteDetailOut:
    get_owned(db, Quote, quote_id, ctx)
    not_implemented("Quote detail")


@router.patch("/quotes/{quote_id}", summary="Withdraw or reject a quote, or change its operator")
def update_quote(
    quote_id: uuid.UUID, body: QuotePatch, ctx: Reviewer, db: DbSession
) -> QuoteSummaryOut:
    get_owned(db, Quote, quote_id, ctx)
    not_implemented("Quote update")


@router.post(
    "/quotes/{quote_id}/fields",
    status_code=status.HTTP_201_CREATED,
    summary="Add a field or fee by hand (edited, locked)",
)
def add_quote_field(
    quote_id: uuid.UUID, body: ManualFieldIn, ctx: Reviewer, db: DbSession
) -> FieldOut:
    get_owned(db, Quote, quote_id, ctx)
    not_implemented("Manual fields")
