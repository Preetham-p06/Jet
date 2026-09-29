"""Reading the audit log. Admins see everything in the workspace; brokers only
one trip at a time (the route enforces `trip_id` for brokers)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.audit import AuditEvent
from app.permissions import RequestContext
from app.schemas.audit import AuditFilters


def list_audit_events(
    db: Session, ctx: RequestContext, filters: AuditFilters
) -> tuple[list[AuditEvent], int]:
    """Newest first; returns (page, total)."""
    raise NotImplementedError
