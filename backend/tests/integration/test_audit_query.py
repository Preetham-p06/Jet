"""Audit log reads: filters, ordering, paging and workspace scoping."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.schemas.audit import AuditFilters
from app.services import audit
from app.services.audit_query import list_audit_events
from tests import factories
from tests.factories_p5 import make_ctx


def test_filters_order_and_scope(db: Session) -> None:
    ws = factories.make_workspace(db)
    ctx = make_ctx(db, ws)
    other_ctx = make_ctx(db, factories.make_workspace(db))
    trip = factories.make_trip(db, ws)
    other_trip = factories.make_trip(db, ws)

    def rec(action: str, day: int, trip_id: object = None) -> None:
        e = audit.record(db, ctx, action, trip, {"a": 1}, {"a": 2}, trip_id=trip.id)
        e.created_at = datetime(2026, 10, day, tzinfo=UTC)
        if trip_id is not None:
            e.trip_id = trip_id  # type: ignore[assignment]

    rec("proposal.create", 1)
    rec("proposal.send", 2)
    rec("field.verify", 3)
    rec("trip.update", 4, trip_id=other_trip.id)
    audit.record(db, other_ctx, "proposal.create", None)
    db.commit()

    events, total = list_audit_events(db, ctx, AuditFilters())
    assert total == 4
    assert [e.action for e in events] == [
        "trip.update",
        "field.verify",
        "proposal.send",
        "proposal.create",
    ]

    events, total = list_audit_events(db, ctx, AuditFilters(trip_id=trip.id))
    assert total == 3

    events, total = list_audit_events(db, ctx, AuditFilters(action="proposal"))
    assert {e.action for e in events} == {"proposal.create", "proposal.send"}
    events, total = list_audit_events(db, ctx, AuditFilters(action="proposal.send"))
    assert total == 1

    events, total = list_audit_events(
        db,
        ctx,
        AuditFilters(
            date_from=datetime(2026, 10, 2, tzinfo=UTC), date_to=datetime(2026, 10, 3, tzinfo=UTC)
        ),
    )
    assert [e.action for e in events] == ["field.verify", "proposal.send"]

    events, total = list_audit_events(
        db, ctx, AuditFilters(entity_type="trip", entity_id=trip.id, actor_user_id=ctx.user_id)
    )
    assert total == 4

    events, total = list_audit_events(db, ctx, AuditFilters(limit=2, offset=1))
    assert total == 4 and [e.action for e in events] == ["field.verify", "proposal.send"]

    events, total = list_audit_events(db, other_ctx, AuditFilters())
    assert total == 1
