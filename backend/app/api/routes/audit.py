"""Audit log reads: admins see the workspace; brokers one trip at a time."""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from pydantic import AwareDatetime

from app.api.params import PageParams
from app.deps import DbSession, Reviewer
from app.errors import Forbidden
from app.models.enums import Role
from app.models.trip import Trip
from app.permissions import get_owned
from app.schemas.audit import AuditEventOut, AuditFilters
from app.schemas.common import Page
from app.services import audit_query

router = APIRouter(tags=["audit"])


@router.get("/audit-events", summary="Audit log (brokers must filter by trip_id)")
def list_audit_events(
    ctx: Reviewer,
    db: DbSession,
    page: PageParams,
    trip_id: uuid.UUID | None = None,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
    action: str | None = None,
    date_from: AwareDatetime | None = None,
    date_to: AwareDatetime | None = None,
) -> Page[AuditEventOut]:
    if ctx.role is not Role.ADMIN and trip_id is None:
        raise Forbidden("Brokers can only view the audit log of one trip", code="trip_required")
    if trip_id is not None:
        get_owned(db, Trip, trip_id, ctx)
    filters = AuditFilters(
        trip_id=trip_id,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_user_id=actor_user_id,
        action=action,
        date_from=date_from,
        date_to=date_to,
        limit=page.limit,
        offset=page.offset,
    )
    rows, total = audit_query.list_audit_events(db, ctx, filters)
    return Page(items=[AuditEventOut.model_validate(r) for r in rows], total=total)
