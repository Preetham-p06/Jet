"""Foundation smoke tests: health, auth and CSRF, trip CRUD, isolation and roles."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.models.enums import Role
from tests.api.routes import api_routes
from tests.conftest import WEB_HEADERS, ClientFactory, TwoWorkspaces

SIGNUP = {
    "workspace_name": "Skyline Charter Brokers",
    "full_name": "Dana Broker",
    "email": "Dana@Example.com",
    "password": "a-long-enough-password",
}

TRIP = {
    "reference": "JS184",
    "pax": 7,
    "client_name": "Private client",
    "preferences": {"wifi_required": True},
    "legs": [
        {
            "origin_icao": "kteb",
            "destination_icao": "KOPF",
            "depart_local": "2026-10-18T09:00:00",
            "depart_tz": "America/New_York",
        }
    ],
}


def test_health(client: TestClient) -> None:
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "db": "ok", "extractor": "rules", "version": "0.1.0"}
    assert res.headers["x-content-type-options"] == "nosniff"
    assert res.headers["x-request-id"]


def test_trailing_slash_is_not_redirected(client: TestClient) -> None:
    res = client.get("/api/v1/health/", follow_redirects=False)
    assert res.status_code == 404
    assert res.json()["code"] == "not_found"


def test_signup_login_me_logout(client: TestClient) -> None:
    res = client.post("/api/v1/auth/signup", json=SIGNUP, headers=WEB_HEADERS)
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["role"] == "admin"
    assert body["user"]["email"] == "dana@example.com"
    assert "workspace.admin" in body["capabilities"]

    cookie = res.headers["set-cookie"]
    assert cookie.startswith("js_session=")
    assert "HttpOnly" in cookie
    assert "samesite=lax" in cookie.lower()
    assert "Path=/" in cookie

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["workspace"]["name"] == "Skyline Charter Brokers"

    # Cookie-authenticated unsafe request without the client header: CSRF refusal.
    no_header = client.post("/api/v1/auth/logout")
    assert no_header.status_code == 403
    assert no_header.json()["code"] == "csrf_failed"

    out = client.post("/api/v1/auth/logout", headers=WEB_HEADERS)
    assert out.status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401

    bad = client.post(
        "/api/v1/auth/login",
        json={"email": SIGNUP["email"], "password": "wrong-password"},
        headers=WEB_HEADERS,
    )
    assert bad.status_code == 401
    assert bad.json() == {"detail": "Invalid email or password", "code": "invalid_credentials"}

    ok = client.post(
        "/api/v1/auth/login",
        json={"email": SIGNUP["email"], "password": SIGNUP["password"]},
        headers=WEB_HEADERS,
    )
    assert ok.status_code == 200
    assert client.get("/api/v1/auth/me").json()["user"]["full_name"] == "Dana Broker"


def test_login_requires_client_header(client: TestClient) -> None:
    res = client.post("/api/v1/auth/login", json={"email": "a@b.co", "password": "x"})
    assert res.status_code == 403


def test_bearer_token_is_csrf_exempt(client: TestClient) -> None:
    client.post("/api/v1/auth/signup", json=SIGNUP, headers=WEB_HEADERS)
    client.cookies.clear()
    token = client.post(
        "/api/v1/auth/token",
        data={"username": SIGNUP["email"], "password": SIGNUP["password"]},
    ).json()["access_token"]
    res = client.post("/api/v1/trips", json=TRIP, headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 201, res.text


def test_trip_crud_round_trip(browser_as: ClientFactory) -> None:
    web = browser_as(Role.ADMIN)
    created = web.post("/api/v1/trips", json=TRIP)
    assert created.status_code == 201, created.text
    trip = created.json()
    assert trip["reference"] == "JS184"
    assert trip["status"] == "draft"
    assert trip["legs"][0]["origin_icao"] == "KTEB"
    assert trip["preferences"]["wifi_required"] is True

    duplicate = web.post("/api/v1/trips", json=TRIP)
    assert duplicate.status_code == 409

    auto = web.post("/api/v1/trips", json={**TRIP, "reference": None})
    assert auto.json()["reference"] == "JS185"  # continues after JS184

    listed = web.get("/api/v1/trips")
    assert listed.json()["total"] == 2

    patched = web.patch(f"/api/v1/trips/{trip['id']}", json={"pax": 8, "status": "sourcing"})
    assert patched.status_code == 200
    assert patched.json()["pax"] == 8
    assert patched.json()["status"] == "sourcing"

    fetched = web.get(f"/api/v1/trips/{trip['id']}")
    assert fetched.json()["pax"] == 8

    assert web.delete(f"/api/v1/trips/{trip['id']}").status_code == 204
    assert web.get(f"/api/v1/trips/{trip['id']}").status_code == 404


def test_other_workspace_gets_404(two_workspaces: TwoWorkspaces) -> None:
    a, b = two_workspaces.a, two_workspaces.b
    assert a.admin.get(f"/api/v1/trips/{a.trip.id}").status_code == 200

    res = b.admin.get(f"/api/v1/trips/{a.trip.id}")
    assert res.status_code == 404
    assert res.json()["code"] == "not_found"
    assert b.admin.patch(f"/api/v1/trips/{a.trip.id}", json={"pax": 2}).status_code == 404

    b_trips = b.admin.get("/api/v1/trips").json()
    assert [t["id"] for t in b_trips["items"]] == [str(b.trip.id)]


def test_assistant_cannot_patch_workspace(client_as: ClientFactory) -> None:
    assistant = client_as(Role.ASSISTANT)
    res = assistant.patch("/api/v1/workspace", json={"review_threshold": 80})
    assert res.status_code == 403
    assert res.json()["code"] == "forbidden_role"
    assert assistant.get("/api/v1/workspace").status_code == 200

    admin = client_as(Role.ADMIN)
    ok = admin.patch("/api/v1/workspace", json={"review_threshold": 80})
    assert ok.status_code == 200
    assert ok.json()["review_threshold"] == 80


def test_every_route_declares_a_role_gate(app: FastAPI) -> None:
    public = {
        "/api/v1/health",
        "/api/v1/auth/signup",
        "/api/v1/auth/login",
        "/api/v1/auth/token",
        "/api/v1/auth/invites/accept",
        "/api/v1/public/proposals/{token}",
        "/api/v1/public/proposals/{token}/accept",
    }
    routes = api_routes(app)
    assert len(routes) > 60  # the walker must see the nested routers
    ungated = [f"{r.method} {r.path}" for r in routes if r.path not in public and not r.roles()]
    assert ungated == []
    assert all(not r.path.endswith("/") for r in routes)


def test_public_errors_keep_privacy_headers(client: TestClient) -> None:
    res = client.get("/api/v1/public/proposals/" + "x" * 43)
    assert res.status_code == 404
    assert res.headers["referrer-policy"] == "no-referrer"
    assert res.headers["x-robots-tag"] == "noindex, nofollow"
    assert res.headers["cache-control"] == "no-store"
