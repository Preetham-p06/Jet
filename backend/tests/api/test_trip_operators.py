"""RFQ tracking: which operators were asked, and how they answered."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Operator, Trip
from app.models.audit import AuditEvent
from app.models.enums import Role
from tests import factories
from tests.conftest import ClientFactory

V = "/api/v1"
T0 = datetime.now(UTC).replace(microsecond=0) - timedelta(days=1)


def _setup(client_as: ClientFactory, db: Session) -> tuple[object, object, Trip]:
    assistant = client_as(Role.ASSISTANT)
    broker = client_as(Role.BROKER)
    trip = factories.make_trip(db, assistant.user.workspace, reference="JS300")  # type: ignore[attr-defined]
    db.commit()
    return assistant, broker, trip


def test_bulk_add_reuses_operators_and_starts_sourcing(
    client_as: ClientFactory, db: Session
) -> None:
    assistant, _broker, trip = _setup(client_as, db)
    existing = assistant.post(f"{V}/operators", json={"name": "Atlas Air Charter"}).json()  # type: ignore[attr-defined]

    res = assistant.post(  # type: ignore[attr-defined]
        f"{V}/trips/{trip.id}/operators",
        json={
            "operator_ids": [existing["id"], existing["id"]],
            "new_operators": [{"name": "atlas air charter"}, {"name": "Summit Executive Aviation"}],
            "channel": "email",
            "requested_at": T0.isoformat(),
        },
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["total"] == 2
    assert sorted(r["operator_name"] for r in body["items"]) == [
        "Atlas Air Charter",
        "Summit Executive Aviation",
    ]
    assert all(r["status"] == "requested" for r in body["items"])
    ws_id = trip.workspace_id
    names = db.scalars(select(Operator.name).where(Operator.workspace_id == ws_id)).all()
    assert sorted(names) == ["Atlas Air Charter", "Summit Executive Aviation"]

    db.expire_all()
    assert db.get(Trip, trip.id).status.value == "sourcing"  # type: ignore[union-attr]

    # Adding again keeps the existing entries.
    again = assistant.post(  # type: ignore[attr-defined]
        f"{V}/trips/{trip.id}/operators", json={"operator_ids": [existing["id"]]}
    )
    assert again.json()["total"] == 2
    actions = db.scalars(select(AuditEvent.action).where(AuditEvent.trip_id == trip.id)).all()
    assert actions.count("rfq.create") == 2

    empty = assistant.post(f"{V}/trips/{trip.id}/operators", json={})  # type: ignore[attr-defined]
    assert empty.status_code == 422
    assert empty.json()["code"] == "nothing_to_add"


def test_responses_quote_decline_and_timing(client_as: ClientFactory, db: Session) -> None:
    assistant, _broker, trip = _setup(client_as, db)
    rows = assistant.post(  # type: ignore[attr-defined]
        f"{V}/trips/{trip.id}/operators",
        json={
            "new_operators": [{"name": "Atlas"}, {"name": "Harbor Jet Group"}],
            "requested_at": T0.isoformat(),
        },
    ).json()["items"]
    atlas = next(r for r in rows if r["operator_name"] == "Atlas")
    harbor = next(r for r in rows if r["operator_name"] == "Harbor Jet Group")

    quoted = assistant.patch(  # type: ignore[attr-defined]
        f"{V}/trips/{trip.id}/operators/{atlas['id']}",
        json={"status": "quoted", "responded_at": (T0 + timedelta(minutes=84)).isoformat()},
    )
    assert quoted.status_code == 200
    assert quoted.json()["response_minutes"] == 84

    declined = assistant.patch(  # type: ignore[attr-defined]
        f"{V}/trips/{trip.id}/operators/{harbor['id']}",
        json={"status": "declined", "declined_reason": "No aircraft available"},
    )
    assert declined.status_code == 200
    assert declined.json()["responded_at"] is not None  # filled in on response
    assert declined.json()["declined_reason"] == "No aircraft available"

    early = assistant.patch(  # type: ignore[attr-defined]
        f"{V}/trips/{trip.id}/operators/{atlas['id']}",
        json={"responded_at": (T0 - timedelta(hours=1)).isoformat()},
    )
    assert early.status_code == 422
    assert early.json()["code"] == "invalid_response_time"

    detail = assistant.get(f"{V}/trips/{trip.id}").json()  # type: ignore[attr-defined]
    assert detail["counts"]["operators_requested"] == 2
    assert detail["counts"]["operators_quoted"] == 1
    assert detail["counts"]["operators_declined"] == 1


def test_entries_belong_to_their_trip(client_as: ClientFactory, db: Session) -> None:
    assistant, broker, trip = _setup(client_as, db)
    other = factories.make_trip(db, assistant.user.workspace, reference="JS301")  # type: ignore[attr-defined]
    db.commit()
    row = assistant.post(  # type: ignore[attr-defined]
        f"{V}/trips/{trip.id}/operators", json={"new_operators": [{"name": "Atlas"}]}
    ).json()["items"][0]

    # The same workspace, but addressed through another trip: 404.
    res = assistant.patch(  # type: ignore[attr-defined]
        f"{V}/trips/{other.id}/operators/{row['id']}", json={"notes": "x"}
    )
    assert res.status_code == 404
    assert broker.delete(f"{V}/trips/{other.id}/operators/{row['id']}").status_code == 404  # type: ignore[attr-defined]

    # Assistants cannot remove entries; brokers can.
    assert assistant.delete(f"{V}/trips/{trip.id}/operators/{row['id']}").status_code == 403  # type: ignore[attr-defined]
    assert broker.delete(f"{V}/trips/{trip.id}/operators/{row['id']}").status_code == 204  # type: ignore[attr-defined]
    assert assistant.get(f"{V}/trips/{trip.id}/operators").json()["total"] == 0  # type: ignore[attr-defined]


def test_list_links_the_active_quote_and_paginates(client_as: ClientFactory, db: Session) -> None:
    assistant, _broker, trip = _setup(client_as, db)
    ws = assistant.user.workspace  # type: ignore[attr-defined]
    ops = [factories.make_operator(db, ws, f"Operator {i}") for i in range(3)]
    rfqs = [
        factories.make_trip_operator(db, trip, op, requested_at=T0 + timedelta(minutes=i))
        for i, op in enumerate(ops)
    ]
    quote = factories.make_quote(db, trip, ops[0], trip_operator_id=rfqs[0].id)
    db.commit()

    page = assistant.get(f"{V}/trips/{trip.id}/operators", params={"limit": 2}).json()  # type: ignore[attr-defined]
    assert page["total"] == 3
    assert len(page["items"]) == 2
    assert page["items"][0]["quote_id"] == str(quote.id)
    assert page["items"][1]["quote_id"] is None
    rest = assistant.get(  # type: ignore[attr-defined]
        f"{V}/trips/{trip.id}/operators", params={"limit": 2, "offset": 2}
    ).json()
    assert [r["operator_name"] for r in rest["items"]] == ["Operator 2"]
