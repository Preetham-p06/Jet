"""Trips: CRUD, recompute and the processing log."""

from __future__ import annotations

import re
import uuid
from collections.abc import Sequence
from typing import Annotated, Any

from fastapi import APIRouter, Query, Response, status
from pydantic import AwareDatetime
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.params import PageParams
from app.api.routes._views import recommendation
from app.deps import Admin, AnyUser, DbSession
from app.errors import Conflict, Unprocessable
from app.models.document import ProcessingEvent, SourceDocument
from app.models.enums import FlagStatus, QuoteStatus, TripOperatorStatus, TripStatus
from app.models.flag import Flag
from app.models.operator import Operator
from app.models.quote import Quote
from app.models.trip import Trip, TripLeg, TripOperator
from app.permissions import RequestContext, get_owned, scoped
from app.schemas.common import Page
from app.schemas.recommendation import RecommendationOut
from app.schemas.trip import (
    LegIn,
    LegOut,
    ProcessingEventOut,
    RecommendationSummary,
    TripCounts,
    TripCreate,
    TripOut,
    TripPatch,
    TripPreferences,
    TripSummaryOut,
)
from app.services import airports, audit, recompute

router = APIRouter(prefix="/trips", tags=["trips"])

_AUDITED = (
    "reference",
    "status",
    "trip_type",
    "pax",
    "client_name",
    "client_email",
    "preferences",
    "notes",
)
_LEG_AUDITED = ("seq", "origin_icao", "destination_icao", "depart_local", "depart_tz")
_AUTO_REF = re.compile(r"^JS(\d+)$")


def _next_reference(db: Session, ctx: RequestContext) -> str:
    refs = db.scalars(
        scoped(select(Trip.reference), ctx, Trip).where(Trip.reference.like("JS%"))
    ).all()
    numbers = [int(m.group(1)) for r in refs if (m := _AUTO_REF.match(r))]
    return f"JS{max([99, *numbers]) + 1:03d}"


def _ensure_unique_reference(
    db: Session, ctx: RequestContext, reference: str, exclude: uuid.UUID | None = None
) -> None:
    stmt = scoped(select(Trip.id), ctx, Trip).where(Trip.reference == reference)
    if exclude is not None:
        stmt = stmt.where(Trip.id != exclude)
    if db.scalar(stmt) is not None:
        raise Conflict(f"Trip {reference} already exists", code="reference_taken")


def _build_legs(ctx: RequestContext, legs: Sequence[LegIn]) -> list[TripLeg]:
    built = []
    for seq, leg in enumerate(legs, start=1):
        tz = leg.depart_tz or airports.timezone_for(leg.origin_icao)
        if tz is None:
            raise Unprocessable(
                f"Unknown airport {leg.origin_icao}; pass depart_tz",
                code="unknown_airport",
                fields={f"legs.{seq - 1}.depart_tz": "required for this airport"},
            )
        built.append(
            TripLeg(
                workspace_id=ctx.workspace_id,
                seq=seq,
                origin_icao=leg.origin_icao,
                destination_icao=leg.destination_icao,
                depart_local=leg.depart_local,
                depart_tz=tz,
            )
        )
    return built


def _count_by_trip(db: Session, stmt: Any) -> dict[uuid.UUID, int]:
    return {trip_id: count for trip_id, count in db.execute(stmt).all()}


def _summaries(db: Session, trips: Sequence[Trip]) -> list[TripSummaryOut]:
    ids = [t.id for t in trips]
    if not ids:
        return []
    quote_counts = _count_by_trip(
        db,
        select(Quote.trip_id, func.count())
        .where(Quote.trip_id.in_(ids), Quote.status == QuoteStatus.ACTIVE)
        .group_by(Quote.trip_id),
    )
    flag_counts = _count_by_trip(
        db,
        select(Flag.trip_id, func.count())
        .where(Flag.trip_id.in_(ids), Flag.status == FlagStatus.OPEN)
        .group_by(Flag.trip_id),
    )
    blocking_counts = _count_by_trip(
        db,
        select(Flag.trip_id, func.count())
        .where(Flag.trip_id.in_(ids), Flag.status == FlagStatus.OPEN, Flag.blocking.is_(True))
        .group_by(Flag.trip_id),
    )
    recommended = {
        q.trip_id: q
        for q in db.scalars(
            select(Quote).where(Quote.trip_id.in_(ids), Quote.is_recommended.is_(True))
        )
    }
    out = []
    for trip in trips:
        rec = recommended.get(trip.id)
        out.append(
            TripSummaryOut(
                id=trip.id,
                reference=trip.reference,
                status=trip.status,
                trip_type=trip.trip_type,
                pax=trip.pax,
                client_name=trip.client_name,
                legs=[LegOut.model_validate(leg) for leg in trip.legs],
                quote_count=quote_counts.get(trip.id, 0),
                open_flag_count=flag_counts.get(trip.id, 0),
                open_blocking_flag_count=blocking_counts.get(trip.id, 0),
                recommended_quote_id=rec.id if rec else None,
                recommended_total_cents=rec.known_total_cents if rec else None,
                is_fully_priced=rec.is_fully_priced if rec else None,
                created_at=trip.created_at,
                updated_at=trip.updated_at,
            )
        )
    return out


def _trip_out(db: Session, trip: Trip) -> TripOut:
    summary = _summaries(db, [trip])[0]
    rfq = _count_by_trip_status(db, trip.id)
    quotes = db.scalars(
        select(Quote).where(Quote.trip_id == trip.id, Quote.status == QuoteStatus.ACTIVE)
    ).all()
    documents = db.scalar(
        select(func.count()).select_from(SourceDocument).where(SourceDocument.trip_id == trip.id)
    )
    counts = TripCounts(
        operators_requested=sum(rfq.values()),
        operators_quoted=rfq.get(TripOperatorStatus.QUOTED, 0),
        operators_declined=rfq.get(TripOperatorStatus.DECLINED, 0),
        quotes=len(quotes),
        documents=documents or 0,
        open_blocking_flags=sum(q.open_blocking_flags for q in quotes),
        pending_review=sum(q.pending_review_count for q in quotes),
    )
    recommendation = None
    rec = next((q for q in quotes if q.is_recommended), None)
    if rec is not None:
        operator = db.get(Operator, rec.operator_id)
        recommendation = RecommendationSummary(
            quote_id=rec.id,
            operator_name=operator.name if operator else "",
            fit_score=rec.fit_score,
            known_total_cents=rec.known_total_cents,
            is_fully_priced=rec.is_fully_priced,
        )
    return TripOut(
        **summary.model_dump(),
        client_email=trip.client_email,
        preferences=TripPreferences.model_validate(trip.preferences or {}),
        notes=trip.notes,
        created_by_id=trip.created_by_id,
        booked_quote_id=trip.booked_quote_id,
        booked_at=trip.booked_at,
        counts=counts,
        recommendation=recommendation,
    )


def _count_by_trip_status(db: Session, trip_id: uuid.UUID) -> dict[TripOperatorStatus, int]:
    rows = db.execute(
        select(TripOperator.status, func.count())
        .where(TripOperator.trip_id == trip_id)
        .group_by(TripOperator.status)
    ).all()
    return dict(rows)


def _has_quotes(db: Session, trip: Trip) -> bool:
    return db.scalar(select(Quote.id).where(Quote.trip_id == trip.id).limit(1)) is not None


@router.get("", summary="List trips")
def list_trips(
    ctx: AnyUser,
    db: DbSession,
    page: PageParams,
    status_filter: Annotated[TripStatus | None, Query(alias="status")] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> Page[TripSummaryOut]:
    stmt = scoped(select(Trip), ctx)
    if status_filter is not None:
        stmt = stmt.where(Trip.status == status_filter)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Trip.reference.ilike(like), Trip.client_name.ilike(like)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    trips = db.scalars(
        stmt.order_by(Trip.created_at.desc(), Trip.id).limit(page.limit).offset(page.offset)
    ).all()
    return Page(items=_summaries(db, trips), total=total)


@router.post("", status_code=status.HTTP_201_CREATED, summary="Create a trip with its legs")
def create_trip(body: TripCreate, ctx: AnyUser, db: DbSession) -> TripOut:
    reference = body.reference or _next_reference(db, ctx)
    _ensure_unique_reference(db, ctx, reference)
    trip = Trip(
        workspace_id=ctx.workspace_id,
        reference=reference,
        trip_type=body.trip_type,
        pax=body.pax,
        client_name=body.client_name,
        client_email=str(body.client_email).lower() if body.client_email else None,
        preferences=body.preferences.model_dump(mode="json"),
        notes=body.notes,
        created_by_id=ctx.user_id,
        legs=_build_legs(ctx, body.legs),
    )
    db.add(trip)
    db.flush()
    audit.record(
        db, ctx, "trip.create", trip, after=audit.snapshot(trip, _AUDITED), trip_id=trip.id
    )
    db.commit()
    return _trip_out(db, trip)


@router.get("/{trip_id}", summary="Trip with legs, counts and recommendation summary")
def get_trip(trip_id: uuid.UUID, ctx: AnyUser, db: DbSession) -> TripOut:
    return _trip_out(db, get_owned(db, Trip, trip_id, ctx))


@router.patch("/{trip_id}", summary="Update a trip (recomputes its quotes)")
def update_trip(trip_id: uuid.UUID, body: TripPatch, ctx: AnyUser, db: DbSession) -> TripOut:
    trip = get_owned(db, Trip, trip_id, ctx)
    before = audit.snapshot(trip, _AUDITED)
    before_legs = [audit.snapshot(leg, _LEG_AUDITED) for leg in trip.legs]
    changes = body.model_dump(exclude_unset=True, exclude={"legs", "preferences", "client_email"})
    if body.reference is not None and body.reference != trip.reference:
        _ensure_unique_reference(db, ctx, body.reference, exclude=trip.id)
    for key, value in changes.items():
        if value is None and key in {"reference", "status", "trip_type", "pax"}:
            continue  # required columns cannot be cleared
        setattr(trip, key, value)
    if "preferences" in body.model_fields_set and body.preferences is not None:
        trip.preferences = body.preferences.model_dump(mode="json")
    if "client_email" in body.model_fields_set:
        trip.client_email = str(body.client_email).lower() if body.client_email else None
    if body.legs is not None:
        trip.legs.clear()
        db.flush()  # delete old legs before reusing their (trip_id, seq)
        trip.legs.extend(_build_legs(ctx, body.legs))
    db.flush()

    old, new = audit.diff(before, audit.snapshot(trip, _AUDITED))
    if body.legs is not None:
        old["legs"] = before_legs
        new["legs"] = [audit.snapshot(leg, _LEG_AUDITED) for leg in trip.legs]
    if new:
        audit.record(db, ctx, "trip.update", trip, old, new, trip_id=trip.id)
    if _has_quotes(db, trip):
        recompute.recompute_trip(db, trip, ctx=ctx)
    db.commit()
    return _trip_out(db, trip)


@router.delete("/{trip_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a trip")
def delete_trip(trip_id: uuid.UUID, ctx: Admin, db: DbSession) -> Response:
    trip = get_owned(db, Trip, trip_id, ctx)
    audit.record(db, ctx, "trip.delete", trip, before=audit.snapshot(trip, _AUDITED))
    db.delete(trip)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{trip_id}/recompute", summary="Re-run normalize, validate and score")
def recompute_trip(trip_id: uuid.UUID, ctx: AnyUser, db: DbSession) -> RecommendationOut:
    trip = get_owned(db, Trip, trip_id, ctx)
    recompute.recompute_trip(db, trip, ctx=ctx)
    db.commit()
    return recommendation(db, ctx, trip)


@router.get("/{trip_id}/events", summary="Processing log, oldest first")
def list_events(
    trip_id: uuid.UUID,
    ctx: AnyUser,
    db: DbSession,
    page: PageParams,
    since: AwareDatetime | None = None,
) -> Page[ProcessingEventOut]:
    trip = get_owned(db, Trip, trip_id, ctx)
    stmt = scoped(select(ProcessingEvent), ctx).where(ProcessingEvent.trip_id == trip.id)
    if since is not None:
        stmt = stmt.where(ProcessingEvent.created_at > since)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(ProcessingEvent.created_at, ProcessingEvent.id)
        .limit(page.limit)
        .offset(page.offset)
    )
    return Page(items=[ProcessingEventOut.model_validate(e) for e in rows], total=total)
