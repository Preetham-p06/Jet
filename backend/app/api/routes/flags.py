"""Flags: list, resolve, reopen."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.api.params import PageParams
from app.deps import AnyUser, DbSession, Reviewer
from app.errors import not_implemented
from app.models.enums import FLAG_RESOLUTIONS, FlagStatus
from app.models.flag import Flag
from app.models.trip import Trip
from app.permissions import get_owned, scoped
from app.schemas.common import Page
from app.schemas.flag import FlagOut, FlagResolveIn

router = APIRouter(tags=["flags"])


def flag_out(flag: Flag) -> FlagOut:
    return FlagOut.from_row(flag, allowed_resolutions=list(FLAG_RESOLUTIONS.get(flag.type, ())))


@router.get("/trips/{trip_id}/flags", summary="Flags for a trip")
def list_flags(
    trip_id: uuid.UUID,
    ctx: AnyUser,
    db: DbSession,
    page: PageParams,
    status_filter: Annotated[FlagStatus | None, Query(alias="status")] = None,
    quote_id: uuid.UUID | None = None,
) -> Page[FlagOut]:
    trip = get_owned(db, Trip, trip_id, ctx)
    stmt = scoped(select(Flag), ctx).where(Flag.trip_id == trip.id)
    if status_filter is not None:
        stmt = stmt.where(Flag.status == status_filter)
    if quote_id is not None:
        stmt = stmt.where(Flag.quote_id == quote_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(Flag.blocking.desc(), Flag.created_at, Flag.id)
        .limit(page.limit)
        .offset(page.offset)
    )
    return Page(items=[flag_out(f) for f in rows], total=total)


@router.post(
    "/flags/{flag_id}/resolve", summary="Resolve a flag; money resolutions write the field"
)
def resolve_flag(flag_id: uuid.UUID, body: FlagResolveIn, ctx: Reviewer, db: DbSession) -> FlagOut:
    get_owned(db, Flag, flag_id, ctx)
    not_implemented("Flag resolve")


@router.post("/flags/{flag_id}/reopen", summary="Reopen a resolved or dismissed flag")
def reopen_flag(flag_id: uuid.UUID, ctx: Reviewer, db: DbSession) -> FlagOut:
    get_owned(db, Flag, flag_id, ctx)
    not_implemented("Flag reopen")
