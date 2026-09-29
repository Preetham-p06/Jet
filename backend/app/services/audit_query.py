"""Reading the audit log. Admins see everything in the workspace; brokers only
one trip at a time (the route enforces `trip_id` for brokers)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.audit import AuditEvent
from app.permissions import RequestContext, scoped
from app.schemas.audit import AuditFilters


def list_audit_events(
    db: Session, ctx: RequestContext, filters: AuditFilters
) -> tuple[list[AuditEvent], int]:
    """Newest first; returns (page, total)."""
    stmt = scoped(select(AuditEvent), ctx)
    if filters.trip_id is not None:
        stmt = stmt.where(AuditEvent.trip_id == filters.trip_id)
    if filters.entity_type is not None:
        stmt = stmt.where(AuditEvent.entity_type == filters.entity_type)
    if filters.entity_id is not None:
        stmt = stmt.where(AuditEvent.entity_id == filters.entity_id)
    if filters.actor_user_id is not None:
        stmt = stmt.where(AuditEvent.actor_user_id == filters.actor_user_id)
    if filters.action is not None:
        # "proposal" matches every proposal.* action; "proposal.send" matches exactly.
        action = filters.action
        if "." in action:
            stmt = stmt.where(AuditEvent.action == action)
        else:
            stmt = stmt.where(
                (AuditEvent.action == action) | AuditEvent.action.startswith(f"{action}.")
            )
    if filters.date_from is not None:
        stmt = stmt.where(AuditEvent.created_at >= filters.date_from)
    if filters.date_to is not None:
        stmt = stmt.where(AuditEvent.created_at <= filters.date_to)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    page = db.scalars(
        stmt.order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        .limit(filters.limit)
        .offset(filters.offset)
    )
    return list(page), total
