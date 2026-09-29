"""The role matrix (spec §8): every route's gate matches the table, disallowed
roles get 403 `forbidden_role`, allowed roles get past the gate."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.models.enums import Role
from tests.api.routes import api_routes
from tests.conftest import WEB_HEADERS, ClientFactory

V = "/api/v1"
A, B, S = Role.ADMIN, Role.BROKER, Role.ASSISTANT
ANY = frozenset({A, B, S})
REVIEW = frozenset({A, B})
ADMIN = frozenset({A})
PUBLIC: frozenset[Role] = frozenset()

#: (method, path) -> roles allowed. PUBLIC means no authentication at all.
ROLES: dict[tuple[str, str], frozenset[Role]] = {
    ("GET", "/health"): PUBLIC,
    ("POST", "/auth/signup"): PUBLIC,
    ("POST", "/auth/login"): PUBLIC,
    ("POST", "/auth/token"): PUBLIC,
    ("POST", "/auth/invites/accept"): PUBLIC,
    ("POST", "/auth/logout"): ANY,
    ("GET", "/auth/me"): ANY,
    ("POST", "/auth/change-password"): ANY,
    ("GET", "/workspace"): ANY,
    ("PATCH", "/workspace"): ADMIN,
    ("GET", "/users"): ADMIN,
    ("PATCH", "/users/{user_id}"): ADMIN,
    ("GET", "/invites"): ADMIN,
    ("POST", "/invites"): ADMIN,
    ("DELETE", "/invites/{invite_id}"): ADMIN,
    ("GET", "/operators"): ANY,
    ("POST", "/operators"): ANY,
    ("GET", "/operators/{operator_id}"): ANY,
    ("PATCH", "/operators/{operator_id}"): REVIEW,
    ("DELETE", "/operators/{operator_id}"): ADMIN,
    ("GET", "/trips"): ANY,
    ("POST", "/trips"): ANY,
    ("GET", "/trips/{trip_id}"): ANY,
    ("PATCH", "/trips/{trip_id}"): ANY,
    ("DELETE", "/trips/{trip_id}"): ADMIN,
    ("POST", "/trips/{trip_id}/recompute"): ANY,
    ("GET", "/trips/{trip_id}/events"): ANY,
    ("GET", "/trips/{trip_id}/operators"): ANY,
    ("POST", "/trips/{trip_id}/operators"): ANY,
    ("PATCH", "/trips/{trip_id}/operators/{trip_operator_id}"): ANY,
    ("DELETE", "/trips/{trip_id}/operators/{trip_operator_id}"): REVIEW,
    ("POST", "/trips/{trip_id}/quotes/ingest"): ANY,
    ("GET", "/trips/{trip_id}/source-documents"): ANY,
    ("GET", "/source-documents/{document_id}"): ANY,
    ("GET", "/source-documents/{document_id}/file"): ANY,
    ("POST", "/source-documents/{document_id}/reprocess"): REVIEW,
    ("POST", "/source-documents/{document_id}/move"): REVIEW,
    ("GET", "/trips/{trip_id}/quotes"): ANY,
    ("GET", "/trips/{trip_id}/comparison"): ANY,
    ("GET", "/quotes/{quote_id}"): ANY,
    ("PATCH", "/quotes/{quote_id}"): REVIEW,
    ("POST", "/quotes/{quote_id}/fields"): REVIEW,
    ("GET", "/trips/{trip_id}/review-queue"): ANY,
    ("GET", "/fields/{field_id}/history"): ANY,
    ("POST", "/fields/{field_id}/verify"): REVIEW,
    ("POST", "/fields/{field_id}/accept"): REVIEW,
    ("PATCH", "/fields/{field_id}"): REVIEW,
    ("POST", "/fields/{field_id}/reset"): REVIEW,
    ("GET", "/trips/{trip_id}/flags"): ANY,
    ("POST", "/flags/{flag_id}/resolve"): REVIEW,
    ("POST", "/flags/{flag_id}/reopen"): REVIEW,
    ("GET", "/trips/{trip_id}/recommendation"): ANY,
    ("GET", "/proposals"): REVIEW,
    ("GET", "/trips/{trip_id}/proposals"): REVIEW,
    ("POST", "/trips/{trip_id}/proposals"): REVIEW,
    ("GET", "/proposals/{proposal_id}"): REVIEW,
    ("GET", "/proposals/{proposal_id}/client-preview"): REVIEW,
    ("PATCH", "/proposals/{proposal_id}"): REVIEW,
    ("POST", "/proposals/{proposal_id}/send"): REVIEW,
    ("POST", "/proposals/{proposal_id}/rotate-link"): REVIEW,
    ("POST", "/proposals/{proposal_id}/revoke-link"): REVIEW,
    ("POST", "/proposals/{proposal_id}/mark-accepted"): REVIEW,
    ("POST", "/proposals/{proposal_id}/mark-booked"): REVIEW,
    ("POST", "/proposals/{proposal_id}/decline"): REVIEW,
    ("POST", "/proposals/{proposal_id}/cancel"): REVIEW,
    ("POST", "/proposals/{proposal_id}/revise"): REVIEW,
    ("GET", "/public/proposals/{token}"): PUBLIC,
    ("POST", "/public/proposals/{token}/accept"): PUBLIC,
    ("GET", "/analytics/overview"): REVIEW,
    ("GET", "/analytics/{metric}"): REVIEW,
    ("GET", "/audit-events"): REVIEW,  # brokers additionally need trip_id
    ("GET", "/meta/vocabulary"): ANY,
    ("GET", "/meta/airports"): ANY,
}

GATED = sorted(k for k, roles in ROLES.items() if roles)


def _url(path: str) -> str:
    filled = path.replace("{metric}", "funnel").replace("{token}", "t" * 43)
    while "{" in filled:
        start = filled.index("{")
        filled = filled[:start] + str(uuid.uuid4()) + filled[filled.index("}") + 1 :]
    return V + filled


def _call(client: TestClient, method: str, path: str) -> Any:
    kwargs: dict[str, Any] = {"headers": WEB_HEADERS}
    if path.endswith("/ingest"):
        kwargs["data"] = {"text": "Quote: $1"}
    elif method in {"POST", "PATCH"}:
        kwargs["json"] = {}
    return client.request(method, _url(path), **kwargs)


def test_table_matches_every_route(app: FastAPI) -> None:
    routes = api_routes(app)
    actual = {r.key: r for r in routes}
    keys = {(m, p.removeprefix(V)) for m, p in actual}
    assert sorted(keys - ROLES.keys()) == [], "new route: add it to the role table"
    assert sorted(ROLES.keys() - keys) == [], "the table lists a route that is gone"
    for (method, path), roles in ROLES.items():
        gate = actual[(method, V + path)].roles()
        if roles:
            assert gate == roles, f"{method} {path}: gate {gate} != table {roles}"
        else:
            assert gate is None, f"{method} {path} is public but has a gate"


def test_every_non_public_route_has_a_role_dependency(app: FastAPI) -> None:
    public = {k for k, roles in ROLES.items() if not roles}
    ungated = [
        r.key
        for r in api_routes(app)
        if (r.method, r.path.removeprefix(V)) not in public and r.roles() is None
    ]
    assert ungated == []


@pytest.mark.parametrize(("method", "path"), GATED)
def test_role_matrix(client_as: ClientFactory, client: TestClient, method: str, path: str) -> None:
    allowed = ROLES[(method, path)]
    for role in Role:
        res = _call(client_as(role), method, path)
        if role in allowed:
            assert res.status_code != 403 or res.json()["code"] == "trip_required", (
                role,
                res.text,
            )
        else:
            assert res.status_code == 403, (role, res.status_code, res.text)
            assert res.json()["code"] == "forbidden_role"
    # Anonymous callers are never let through.
    assert _call(client, method, path).status_code == 401


@pytest.mark.parametrize(("method", "path"), sorted(k for k, r in ROLES.items() if not r))
def test_public_routes_need_no_session(client: TestClient, method: str, path: str) -> None:
    res = _call(client, method, path)
    assert res.status_code != 401, res.text


def test_broker_needs_trip_id_for_the_audit_log(client_as: ClientFactory) -> None:
    broker = client_as(B)
    res = broker.get(f"{V}/audit-events")
    assert res.status_code == 403
    assert res.json()["code"] == "trip_required"
    trip = broker.post(
        f"{V}/trips",
        json={
            "pax": 2,
            "legs": [
                {
                    "origin_icao": "KTEB",
                    "destination_icao": "KOPF",
                    "depart_local": "2026-10-18T09:00:00",
                }
            ],
        },
    ).json()
    res = broker.get(f"{V}/audit-events", params={"trip_id": trip["id"]})
    assert res.status_code == 200
    assert [e["action"] for e in res.json()["items"]] == ["trip.create"]
    assert client_as(A).get(f"{V}/audit-events").status_code == 200


@pytest.mark.parametrize(
    ("role", "capability", "has"),
    [
        (S, "ingest", True),
        (S, "field.review", False),
        (S, "proposal.manage", False),
        (S, "analytics.view", False),
        (B, "field.review", True),
        (B, "workspace.admin", False),
        (A, "users.admin", True),
    ],
)
def test_capabilities_follow_the_role(
    client_as: ClientFactory, role: Role, capability: str, has: bool
) -> None:
    caps = client_as(role).get(f"{V}/auth/me").json()["capabilities"]
    assert (capability in caps) is has
