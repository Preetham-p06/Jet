"""The public client view: whitelisted fields, privacy headers, link states,
acceptance and rate limiting."""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import AuditEvent, Proposal
from app.models.enums import AircraftCategory, AmountStatus, FeeCategory, Role
from tests import factories
from tests.api.seed import add_fee_line
from tests.conftest import WEB_HEADERS, ClientFactory
from tests.factories_p5 import make_ready_quote

V = "/api/v1"
TOP_KEYS = {
    "title",
    "prepared_for",
    "prepared_by",
    "legs",
    "date",
    "pax",
    "message",
    "options",
    "disclaimer",
    "status",
    "accepted_option_id",
    "expires_at",
}
OPTION_KEYS = {
    "option_id",
    "aircraft",
    "category",
    "client_total_cents",
    "seats",
    "pax",
    "wifi",
    "flight_time_minutes",
    "recommended",
}
LEG_KEYS = {"origin_code", "origin_city", "destination_code", "destination_city", "departure_local"}
FORBIDDEN = ("Atlas", "Positioning", "N684AC", "confidence", "markup", "atlas_quote_01")
PRIVACY = {
    "cache-control": "no-store",
    "x-robots-tag": "noindex, nofollow",
    "referrer-policy": "no-referrer",
}


@pytest.fixture
def broker(client_as: ClientFactory) -> TestClient:
    return client_as(Role.BROKER)


@pytest.fixture
def draft(broker: TestClient, db: Session) -> dict[str, Any]:
    """A draft proposal with two options, built through the API."""
    ws = broker.user.workspace  # type: ignore[attr-defined]
    trip = factories.make_trip(db, ws, reference="JS184", client_name="Private client")
    atlas = factories.make_operator(db, ws, "Atlas Air Charter", aliases=["Atlas Jets"])
    skybridge = factories.make_operator(db, ws, "SkyBridge Aviation")
    q1 = make_ready_quote(
        db, trip, atlas, known_total_cents=4_482_000, is_recommended=True, fit_score=96
    )
    add_fee_line(db, q1, FeeCategory.POSITIONING, AmountStatus.STATED, 120_000, confidence=97)
    factories.make_document(db, trip, quote_id=q1.id, original_filename="atlas_quote_01.pdf")
    q2 = make_ready_quote(
        db,
        trip,
        skybridge,
        known_total_cents=4_720_000,
        aircraft_model="Atlas Challenger 350",  # operator tokens must be stripped
        aircraft_category=AircraftCategory.SUPER_MIDSIZE,
        tail_number="N350SB",
        seats=9,
    )
    db.commit()
    res = broker.post(
        f"{V}/trips/{trip.id}/proposals",
        json={"quote_ids": [str(q1.id), str(q2.id)], "markup_pct": 5, "message": "Two options"},
    )
    assert res.status_code == 201, res.text
    return dict(res.json())


def _send(broker: TestClient, proposal_id: str) -> str:
    res = broker.post(f"{V}/proposals/{proposal_id}/send")
    assert res.status_code == 200, res.text
    return str(res.json()["share_url"].rsplit("/", 1)[1])


def _assert_private(res: Any) -> None:
    for header, value in PRIVACY.items():
        assert res.headers[header] == value, header


def test_whitelist_and_no_broker_details(
    broker: TestClient, client: TestClient, draft: dict[str, Any]
) -> None:
    token = _send(broker, draft["id"])
    res = client.get(f"{V}/public/proposals/{token}")
    assert res.status_code == 200, res.text
    _assert_private(res)
    body = res.json()
    assert set(body) == TOP_KEYS
    assert all(set(o) == OPTION_KEYS for o in body["options"])
    assert all(set(leg) == LEG_KEYS for leg in body["legs"])
    for word in FORBIDDEN:
        assert word.lower() not in res.text.lower(), word
    assert "N350SB" not in res.text

    first, second = body["options"]
    assert first["client_total_cents"] == 4_706_100  # 44,820 x 1.05
    assert first["recommended"] is True
    assert first["aircraft"] == "Cessna Citation Latitude"
    assert "Challenger 350" in second["aircraft"]
    assert body["prepared_for"] == "Private client"
    assert body["legs"][0]["origin_code"] in {"TEB", "KTEB"}
    assert body["status"] == "sent"


def test_public_aircraft_label_hides_operator_and_tail(
    broker: TestClient, client: TestClient, db: Session
) -> None:
    ws = broker.user.workspace  # type: ignore[attr-defined]
    trip = factories.make_trip(db, ws, reference="JS900")
    op = factories.make_operator(db, ws, "Wheels Up")
    q = make_ready_quote(
        db,
        trip,
        op,
        known_total_cents=4_000_000,
        aircraft_model="Gulfstream G-IV SP - Wheels-Up fleet (N-684AC)",
        aircraft_category=AircraftCategory.HEAVY,
        tail_number="N684AC",
        seats=12,
    )
    db.commit()
    res = broker.post(f"{V}/trips/{trip.id}/proposals", json={"quote_ids": [str(q.id)]})
    assert res.status_code == 201, res.text
    token = _send(broker, res.json()["id"])
    public = client.get(f"{V}/public/proposals/{token}")
    aircraft = public.json()["options"][0]["aircraft"]
    assert aircraft == "Gulfstream G450"
    for word in ("wheels", "684"):
        assert word not in public.text.lower(), word


def test_views_are_counted_and_the_first_is_audited(
    broker: TestClient, client: TestClient, draft: dict[str, Any], db: Session
) -> None:
    token = _send(broker, draft["id"])
    for _ in range(3):
        assert client.get(f"{V}/public/proposals/{token}").status_code == 200
    detail = broker.get(f"{V}/proposals/{draft['id']}").json()
    assert detail["view_count"] == 3
    assert detail["first_viewed_at"] is not None
    views = db.scalars(select(AuditEvent).where(AuditEvent.action == "public.proposal_view")).all()
    assert len(views) == 1
    assert views[0].actor_kind.value == "public"


def test_client_preview_matches_the_public_payload(
    broker: TestClient, client: TestClient, draft: dict[str, Any]
) -> None:
    preview = broker.get(f"{V}/proposals/{draft['id']}/client-preview")
    assert preview.status_code == 200
    assert set(preview.json()) == TOP_KEYS
    for word in FORBIDDEN:
        assert word.lower() not in preview.text.lower(), word
    token = _send(broker, draft["id"])
    sent_preview = broker.get(f"{V}/proposals/{draft['id']}/client-preview").json()
    public = client.get(f"{V}/public/proposals/{token}").json()
    assert sent_preview["options"] == public["options"]
    assert sent_preview["legs"] == public["legs"]


def test_link_states(
    broker: TestClient, client: TestClient, draft: dict[str, Any], db: Session
) -> None:
    unknown = client.get(f"{V}/public/proposals/{'u' * 43}")
    assert unknown.status_code == 404
    _assert_private(unknown)

    # A draft is never public, even with a token on the row.
    row = db.get(Proposal, uuid.UUID(draft["id"]))
    assert row is not None
    row.share_token = "d" * 43
    row.share_enabled = True
    row.share_expires_at = factories.now() + timedelta(days=1)
    db.commit()
    as_draft = client.get(f"{V}/public/proposals/{'d' * 43}")
    assert as_draft.status_code == 404
    assert as_draft.json() == unknown.json()  # indistinguishable from unknown

    token = _send(broker, draft["id"])
    assert client.get(f"{V}/public/proposals/{token}").status_code == 200

    # Rotating invalidates the old token.
    rotated = broker.post(f"{V}/proposals/{draft['id']}/rotate-link").json()
    new_token = rotated["share_url"].rsplit("/", 1)[1]
    assert new_token != token
    assert client.get(f"{V}/public/proposals/{token}").status_code == 404
    assert client.get(f"{V}/public/proposals/{new_token}").status_code == 200

    # Revoked.
    revoked = broker.post(f"{V}/proposals/{draft['id']}/revoke-link").json()
    assert revoked["share_url"] is None
    res = client.get(f"{V}/public/proposals/{new_token}")
    assert res.status_code == 404
    assert res.json() == unknown.json()

    # Expired.
    newest = broker.post(f"{V}/proposals/{draft['id']}/rotate-link").json()
    newest_token = newest["share_url"].rsplit("/", 1)[1]
    db.expire_all()
    row = db.get(Proposal, uuid.UUID(draft["id"]))
    assert row is not None
    row.share_expires_at = factories.now() - timedelta(minutes=1)
    db.commit()
    assert client.get(f"{V}/public/proposals/{newest_token}").status_code == 404


def test_superseded_link_is_gone(
    broker: TestClient, client: TestClient, draft: dict[str, Any]
) -> None:
    token = _send(broker, draft["id"])
    revised = broker.post(f"{V}/proposals/{draft['id']}/revise")
    assert revised.status_code == 201
    assert revised.json()["status"] == "draft"
    assert revised.json()["supersedes_id"] == draft["id"]
    res = client.get(f"{V}/public/proposals/{token}")
    assert res.status_code == 410
    assert res.json()["code"] == "superseded"
    _assert_private(res)
    assert broker.get(f"{V}/proposals/{draft['id']}").json()["status"] == "superseded"


def test_cancelled_link_is_not_found(
    broker: TestClient, client: TestClient, draft: dict[str, Any]
) -> None:
    token = _send(broker, draft["id"])
    assert broker.post(f"{V}/proposals/{draft['id']}/cancel").json()["status"] == "cancelled"
    assert client.get(f"{V}/public/proposals/{token}").status_code == 404


def test_public_accept(broker: TestClient, client: TestClient, draft: dict[str, Any]) -> None:
    token = _send(broker, draft["id"])
    option_id = client.get(f"{V}/public/proposals/{token}").json()["options"][0]["option_id"]
    other_id = draft["options"][1]["id"]
    url = f"{V}/public/proposals/{token}/accept"
    body = {"option_id": option_id, "name": "Pat Client"}

    assert client.post(url, json=body).status_code == 403  # CSRF header required
    bad = client.post(url, json={**body, "option_id": draft["trip_id"]}, headers=WEB_HEADERS)
    assert bad.status_code == 422
    ok = client.post(url, json=body, headers=WEB_HEADERS)
    assert ok.status_code == 200, ok.text
    _assert_private(ok)
    assert ok.json()["status"] == "accepted"
    assert ok.json()["accepted_option_id"] == option_id
    assert "markup" not in ok.text.lower()
    # Repeating the same click is harmless; switching options is not.
    assert client.post(url, json=body, headers=WEB_HEADERS).status_code == 200
    switch = client.post(url, json={**body, "option_id": other_id}, headers=WEB_HEADERS)
    assert switch.status_code == 409

    detail = broker.get(f"{V}/proposals/{draft['id']}").json()
    assert detail["status"] == "accepted"
    assert detail["accepted_by_name"] == "Pat Client"


def test_public_endpoints_are_rate_limited(
    broker: TestClient, client: TestClient, draft: dict[str, Any], settings: Settings
) -> None:
    token = _send(broker, draft["id"])
    settings.public_rate_limit = 2
    codes = [client.get(f"{V}/public/proposals/{token}").status_code for _ in range(3)]
    assert codes == [200, 200, 429]
    limited = client.get(f"{V}/public/proposals/{token}")
    assert limited.status_code == 429
    assert int(limited.headers["retry-after"]) > 0
    _assert_private(limited)
