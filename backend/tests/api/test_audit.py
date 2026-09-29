"""The audit log: what gets written, and who may read it."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.models.enums import Role
from tests.conftest import WEB_HEADERS, ClientFactory, TwoWorkspaces

V = "/api/v1"
TRIP = {
    "pax": 4,
    "client_name": "Private client",
    "legs": [
        {"origin_icao": "KTEB", "destination_icao": "KOPF", "depart_local": "2026-10-18T09:00:00"}
    ],
}


def _trip(client: TestClient) -> str:
    res = client.post(f"{V}/trips", json=TRIP)
    assert res.status_code == 201, res.text
    return str(res.json()["id"])


def test_mutations_record_before_and_after(client_as: ClientFactory) -> None:
    admin = client_as(Role.ADMIN)
    trip_id = _trip(admin)
    assert admin.patch(f"{V}/trips/{trip_id}", json={"pax": 6}).status_code == 200
    events = admin.get(f"{V}/audit-events", params={"trip_id": trip_id}).json()["items"]
    update = next(e for e in events if e["action"] == "trip.update")
    assert update["before"] == {"pax": 4}
    assert update["after"] == {"pax": 6}
    assert update["actor_kind"] == "user"
    assert update["actor_user_id"] == str(admin.user.id)  # type: ignore[attr-defined]
    assert update["entity_type"] == "trip" and update["entity_id"] == trip_id
    assert update["request_id"]
    create = next(e for e in events if e["action"] == "trip.create")
    assert create["before"] is None and create["after"]["pax"] == 4
    # Newest first.
    assert [e["action"] for e in events][:2] == ["trip.update", "trip.create"]


def test_admin_sees_everything_broker_one_trip(client_as: ClientFactory) -> None:
    admin = client_as(Role.ADMIN)
    broker = client_as(Role.BROKER)
    t1, t2 = _trip(admin), _trip(broker)
    admin.post(f"{V}/operators", json={"name": "Atlas Air Charter"})

    everything = admin.get(f"{V}/audit-events").json()
    trip_ids = {e["trip_id"] for e in everything["items"]}
    assert {t1, t2} <= trip_ids
    assert any(e["entity_type"] == "operator" for e in everything["items"])

    refused = broker.get(f"{V}/audit-events")
    assert refused.status_code == 403
    assert refused.json()["code"] == "trip_required"
    one = broker.get(f"{V}/audit-events", params={"trip_id": t1}).json()
    assert one["total"] >= 1
    assert {e["trip_id"] for e in one["items"]} == {t1}

    assistant = client_as(Role.ASSISTANT)
    assert assistant.get(f"{V}/audit-events", params={"trip_id": t1}).status_code == 403


def test_filters_and_pagination(client_as: ClientFactory) -> None:
    admin = client_as(Role.ADMIN)
    broker = client_as(Role.BROKER)
    trip_id = _trip(admin)
    for pax in (5, 6, 7):
        admin.patch(f"{V}/trips/{trip_id}", json={"pax": pax})
    _trip(broker)

    def get(**params: str | int) -> dict:  # type: ignore[type-arg]
        res = admin.get(f"{V}/audit-events", params=params)
        assert res.status_code == 200, res.text
        return dict(res.json())

    assert get(action="trip.update")["total"] == 3
    assert get(action="trip")["total"] == 5  # prefix match: trip.*
    assert get(entity_type="trip", entity_id=trip_id)["total"] == 4
    mine = get(actor_user_id=str(broker.user.id))  # type: ignore[attr-defined]
    assert [e["action"] for e in mine["items"]] == ["trip.create"]
    page = get(action="trip", limit=2, offset=1)
    assert page["total"] == 5 and len(page["items"]) == 2
    assert get(date_from="2000-01-01T00:00:00Z", date_to="2000-01-02T00:00:00Z")["total"] == 0
    naive = admin.get(f"{V}/audit-events", params={"date_from": "2026-01-01T00:00:00"})
    assert naive.status_code == 422


def test_audit_log_is_workspace_scoped(two_workspaces: TwoWorkspaces) -> None:
    a, b = two_workspaces.a, two_workspaces.b
    a_trip = _trip(a.admin)
    _trip(b.admin)
    b_events = b.admin.get(f"{V}/audit-events").json()["items"]
    assert a_trip not in {e["trip_id"] for e in b_events}
    assert b.admin.get(f"{V}/audit-events", params={"trip_id": a_trip}).status_code == 404
    assert b.broker.get(f"{V}/audit-events", params={"trip_id": a_trip}).status_code == 404
    assert (
        b.admin.get(f"{V}/audit-events", params={"trip_id": str(uuid.uuid4())}).status_code == 404
    )


def test_login_and_secrets_never_leak_into_the_log(client: TestClient) -> None:
    signup = {
        "workspace_name": "Skyline",
        "full_name": "Dana",
        "email": "dana@example.com",
        "password": "super-secret-password",
    }
    assert client.post(f"{V}/auth/signup", json=signup, headers=WEB_HEADERS).status_code == 201
    invite = client.post(
        f"{V}/invites", json={"email": "new@example.com", "role": "broker"}, headers=WEB_HEADERS
    )
    assert invite.status_code == 201
    token = invite.json()["invite_url"].rsplit("/", 1)[1]
    log = client.get(f"{V}/audit-events", params={"limit": 200})
    assert log.status_code == 200
    assert "super-secret-password" not in log.text
    assert token not in log.text
    assert "password_hash" not in log.text
