"""Foundation CRUD: users, invites, operators, RFQ tracking, documents, flags, meta, 501s."""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.enums import Role
from app.services.storage import LocalStorage
from tests import factories
from tests.conftest import WEB_HEADERS, ClientFactory, TwoWorkspaces


def test_invite_flow_and_last_admin_guard(client_as: ClientFactory, client: TestClient) -> None:
    admin = client_as(Role.ADMIN)
    created = admin.post("/api/v1/invites", json={"email": "New@Example.com", "role": "broker"})
    assert created.status_code == 201, created.text
    token = created.json()["invite_url"].rsplit("/", 1)[1]
    assert admin.get("/api/v1/invites").json()["items"][0]["state"] == "pending"

    accepted = client.post(
        "/api/v1/auth/invites/accept",
        json={"token": token, "full_name": "New Broker", "password": "another-long-password"},
        headers=WEB_HEADERS,
    )
    assert accepted.status_code == 201, accepted.text
    assert accepted.json()["role"] == "broker"
    again = client.post(
        "/api/v1/auth/invites/accept",
        json={"token": token, "full_name": "X", "password": "another-long-password"},
        headers=WEB_HEADERS,
    )
    assert again.status_code == 404

    users = admin.get("/api/v1/users").json()
    assert users["total"] == 2
    me = admin.user.id  # type: ignore[attr-defined]
    res = admin.patch(f"/api/v1/users/{me}", json={"role": "broker"})
    assert res.status_code == 409 and res.json()["code"] == "last_admin"


def test_deactivation_and_password_change_revoke_sessions(browser_as: ClientFactory) -> None:
    web = browser_as(Role.BROKER)
    res = web.post(
        "/api/v1/auth/change-password",
        json={"current_password": factories.DEFAULT_PASSWORD, "new_password": "brand-new-password"},
    )
    assert res.status_code == 200
    # The response re-issued the cookie, so this client is still signed in.
    assert web.get("/api/v1/auth/me").status_code == 200

    stale = browser_as(Role.ADMIN)
    admin_id = stale.user.id  # type: ignore[attr-defined]
    other = browser_as(Role.ADMIN)
    assert other.patch(f"/api/v1/users/{admin_id}", json={"is_active": False}).status_code == 200
    assert stale.get("/api/v1/auth/me").status_code == 401


def test_operators_and_rfq_tracking(client_as: ClientFactory, db: Session) -> None:
    assistant = client_as(Role.ASSISTANT)
    broker = client_as(Role.BROKER)
    trip = factories.make_trip(db, assistant.user.workspace, reference="JS200")  # type: ignore[attr-defined]
    db.commit()

    atlas = assistant.post(
        "/api/v1/operators", json={"name": "Atlas Jets", "email": "ops@atlasjets.com"}
    )
    assert atlas.status_code == 201
    assert atlas.json()["email_domain"] == "atlasjets.com"
    dup = assistant.post("/api/v1/operators", json={"name": "atlas  jets"})
    assert dup.status_code == 409
    assert (
        assistant.patch(f"/api/v1/operators/{atlas.json()['id']}", json={"notes": "x"}).status_code
        == 403
    )

    added = assistant.post(
        f"/api/v1/trips/{trip.id}/operators",
        json={
            "operator_ids": [atlas.json()["id"]],
            "new_operators": [{"name": "Summit Aviation"}, {"name": "Atlas Jets"}],
            "channel": "email",
        },
    )
    assert added.status_code == 201, added.text
    rows = added.json()["items"]
    assert sorted(r["operator_name"] for r in rows) == ["Atlas Jets", "Summit Aviation"]

    row = rows[0]
    responded = datetime.fromisoformat(row["requested_at"]) + timedelta(minutes=84)
    patched = assistant.patch(
        f"/api/v1/trips/{trip.id}/operators/{row['id']}",
        json={"status": "quoted", "responded_at": responded.isoformat()},
    )
    assert patched.status_code == 200
    assert patched.json()["response_minutes"] == 84

    detail = assistant.get(f"/api/v1/operators/{row['operator_id']}").json()
    assert detail["stats"]["median_response_hours"] == 1.4

    assert assistant.get(f"/api/v1/trips/{trip.id}").json()["status"] == "sourcing"
    assert assistant.delete(f"/api/v1/trips/{trip.id}/operators/{row['id']}").status_code == 403
    assert broker.delete(f"/api/v1/trips/{trip.id}/operators/{row['id']}").status_code == 204


def test_documents_flags_and_quotes_reads(
    app: FastAPI, two_workspaces: TwoWorkspaces, db: Session
) -> None:
    a, b = two_workspaces.a, two_workspaces.b
    storage: LocalStorage = app.state.storage
    stored = storage.put(
        a.workspace.id, b"%PDF-1.7 demo", suffix=".pdf", content_type="application/pdf"
    )
    op = factories.make_operator(db, a.workspace, "Atlas Jets")
    quote = factories.make_quote(db, a.trip, op, known_total_cents=4482000)
    doc = factories.make_document(
        db,
        a.trip,
        storage_key=stored.key,
        media_type="application/pdf",
        original_filename="atlas_quote_01.pdf",
        quote_id=quote.id,
    )
    factories.make_flag(db, quote)
    db.commit()

    assert a.assistant.get(f"/api/v1/trips/{a.trip.id}/source-documents").json()["total"] == 1
    file = a.assistant.get(f"/api/v1/source-documents/{doc.id}/file")
    assert file.status_code == 200 and file.content == b"%PDF-1.7 demo"
    assert file.headers["content-type"] == "application/pdf"
    assert b.admin.get(f"/api/v1/source-documents/{doc.id}/file").status_code == 404

    flags = a.broker.get(f"/api/v1/trips/{a.trip.id}/flags").json()
    assert flags["total"] == 1
    assert "accepted_estimate" in flags["items"][0]["allowed_resolutions"]

    quotes = a.broker.get(f"/api/v1/trips/{a.trip.id}/quotes").json()
    assert quotes["items"][0]["operator_name"] == "Atlas Jets"
    assert b.admin.get(f"/api/v1/quotes/{quote.id}").status_code == 404
    assert a.admin.get(f"/api/v1/quotes/{quote.id}").status_code == 501


def test_meta_vocabulary_and_not_implemented(client_as: ClientFactory) -> None:
    assistant = client_as(Role.ASSISTANT)
    vocab = assistant.get("/api/v1/meta/vocabulary").json()
    assert vocab["fee_categories"][0] == {
        "value": "positioning",
        "label": "Positioning",
        "order": 0,
    }
    res = assistant.get("/api/v1/analytics/overview")
    assert res.status_code == 403
    broker = client_as(Role.BROKER)
    res = broker.get("/api/v1/analytics/overview")
    assert res.status_code == 501
    assert res.json()["code"] == "not_implemented"
    assert broker.get("/api/v1/audit-events").status_code == 403
