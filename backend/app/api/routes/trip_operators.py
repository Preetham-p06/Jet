"""RFQ tracking: which operators were asked to quote a trip, and how they answered."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.params import PageParams
from app.api.routes.operators import create_operator
from app.deps import AnyUser, DbSession, Reviewer
from app.errors import NotFound, Unprocessable
from app.models.enums import QuoteStatus, TripOperatorStatus, TripStatus
from app.models.operator import Operator
from app.models.quote import Quote
from app.models.trip import Trip, TripOperator
from app.permissions import RequestContext, get_owned, scoped
from app.schemas.common import Page
from app.schemas.trip import TripOperatorOut, TripOperatorPatch, TripOperatorsAdd
from app.services import audit
from app.services.operators import normalize_operator_name

router = APIRouter(prefix="/trips/{trip_id}/operators", tags=["rfq"])

_AUDITED = ("status", "channel", "requested_at", "responded_at", "declined_reason", "notes")


def _out(db: Session, rows: list[TripOperator]) -> list[TripOperatorOut]:
    if not rows:
        return []
    names = dict(
        db.execute(
            select(Operator.id, Operator.name).where(Operator.id.in_({r.operator_id for r in rows}))
        ).all()
    )
    quotes = dict(
        db.execute(
            select(Quote.trip_operator_id, Quote.id).where(
                Quote.trip_operator_id.in_([r.id for r in rows]),
                Quote.status == QuoteStatus.ACTIVE,
            )
        ).all()
    )
    out = []
    for r in rows:
        minutes = None
        if r.responded_at is not None:
            minutes = int((r.responded_at - r.requested_at).total_seconds() // 60)
        out.append(
            TripOperatorOut(
                id=r.id,
                trip_id=r.trip_id,
                operator_id=r.operator_id,
                operator_name=names.get(r.operator_id, ""),
                status=r.status,
                channel=r.channel,
                requested_at=r.requested_at,
                responded_at=r.responded_at,
                response_minutes=minutes,
                declined_reason=r.declined_reason,
                notes=r.notes,
                quote_id=quotes.get(r.id),
                created_at=r.created_at,
            )
        )
    return out


def _rows(db: Session, ctx: RequestContext, trip: Trip) -> list[TripOperator]:
    stmt = (
        scoped(select(TripOperator), ctx)
        .where(TripOperator.trip_id == trip.id)
        .order_by(TripOperator.requested_at, TripOperator.created_at)
    )
    return list(db.scalars(stmt))


def _owned_trip_operator(
    db: Session, ctx: RequestContext, trip: Trip, trip_operator_id: uuid.UUID
) -> TripOperator:
    row = get_owned(db, TripOperator, trip_operator_id, ctx)
    if row.trip_id != trip.id:
        raise NotFound("TripOperator not found")
    return row


@router.get("", summary="Operators asked to quote this trip")
def list_trip_operators(
    trip_id: uuid.UUID, ctx: AnyUser, db: DbSession, page: PageParams
) -> Page[TripOperatorOut]:
    trip = get_owned(db, Trip, trip_id, ctx)
    rows = _rows(db, ctx, trip)
    return Page(items=_out(db, rows[page.offset : page.offset + page.limit]), total=len(rows))


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Log requests to existing and/or new operators (existing entries are kept)",
)
def add_trip_operators(
    trip_id: uuid.UUID, body: TripOperatorsAdd, ctx: AnyUser, db: DbSession
) -> Page[TripOperatorOut]:
    trip = get_owned(db, Trip, trip_id, ctx)
    if not body.operator_ids and not body.new_operators:
        raise Unprocessable("Give operator_ids or new_operators", code="nothing_to_add")
    requested_at = body.requested_at or datetime.now(UTC)

    operators = [get_owned(db, Operator, oid, ctx) for oid in dict.fromkeys(body.operator_ids)]
    for new in body.new_operators:
        existing = db.scalar(
            scoped(select(Operator), ctx).where(
                Operator.normalized_name == normalize_operator_name(new.name)
            )
        )
        operators.append(existing or create_operator(db, ctx, new))

    already = {r.operator_id for r in _rows(db, ctx, trip)}
    for operator in operators:
        if operator.id in already:
            continue
        already.add(operator.id)
        row = TripOperator(
            workspace_id=ctx.workspace_id,
            trip_id=trip.id,
            operator_id=operator.id,
            channel=body.channel,
            requested_at=requested_at,
            created_by_id=ctx.user_id,
        )
        db.add(row)
        db.flush()
        audit.record(
            db,
            ctx,
            "rfq.create",
            row,
            after={"operator": operator.name, "channel": body.channel.value},
            trip_id=trip.id,
        )
    if trip.status is TripStatus.DRAFT:
        trip.status = TripStatus.SOURCING
    db.commit()
    rows = _rows(db, ctx, trip)
    return Page(items=_out(db, rows), total=len(rows))


@router.patch("/{trip_operator_id}", summary="Update status, response time or notes")
def update_trip_operator(
    trip_id: uuid.UUID,
    trip_operator_id: uuid.UUID,
    body: TripOperatorPatch,
    ctx: AnyUser,
    db: DbSession,
) -> TripOperatorOut:
    trip = get_owned(db, Trip, trip_id, ctx)
    row = _owned_trip_operator(db, ctx, trip, trip_operator_id)
    before = audit.snapshot(row, _AUDITED)
    changes = body.model_dump(exclude_unset=True)
    for key in ("status", "channel", "requested_at"):
        if key in changes and changes[key] is None:
            del changes[key]  # required columns cannot be cleared
    for key, value in changes.items():
        setattr(row, key, value)
    if row.status is not TripOperatorStatus.REQUESTED and row.responded_at is None:
        row.responded_at = datetime.now(UTC)
    if row.responded_at is not None and row.responded_at < row.requested_at:
        raise Unprocessable("responded_at is before requested_at", code="invalid_response_time")
    old, new = audit.diff(before, audit.snapshot(row, _AUDITED))
    if new:
        audit.record(db, ctx, "rfq.update", row, old, new, trip_id=trip.id)
    db.commit()
    return _out(db, [row])[0]


@router.delete(
    "/{trip_operator_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove an operator from the RFQ list",
)
def delete_trip_operator(
    trip_id: uuid.UUID, trip_operator_id: uuid.UUID, ctx: Reviewer, db: DbSession
) -> Response:
    trip = get_owned(db, Trip, trip_id, ctx)
    row = _owned_trip_operator(db, ctx, trip, trip_operator_id)
    audit.record(db, ctx, "rfq.delete", row, before=audit.snapshot(row, _AUDITED), trip_id=trip.id)
    db.delete(row)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
