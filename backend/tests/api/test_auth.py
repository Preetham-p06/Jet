"""Authentication, sessions and CSRF."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import Request
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.orm import Session

from app.config import Settings
from app.deps import client_ip
from app.models import User
from app.models.enums import Role
from app.security.ratelimit import InMemoryRateLimiter
from app.security.tokens import create_access_token
from tests import factories
from tests.conftest import WEB_HEADERS, ClientFactory

V = "/api/v1"
SIGNUP = {
    "workspace_name": "Skyline Charter Brokers",
    "full_name": "Dana Broker",
    "email": "Dana@Example.com",
    "password": "a-long-enough-password",
}
TRIP = {
    "pax": 4,
    "legs": [
        {"origin_icao": "KTEB", "destination_icao": "KOPF", "depart_local": "2026-10-18T09:00:00"}
    ],
}


def _signup(client: TestClient) -> None:
    res = client.post(f"{V}/auth/signup", json=SIGNUP, headers=WEB_HEADERS)
    assert res.status_code == 201, res.text


def test_signup_sets_a_hardened_cookie(client: TestClient) -> None:
    res = client.post(f"{V}/auth/signup", json=SIGNUP, headers=WEB_HEADERS)
    assert res.status_code == 201
    cookie = res.headers["set-cookie"]
    assert cookie.startswith("js_session=")
    for attr in ("HttpOnly", "Path=/"):
        assert attr in cookie
    assert "samesite=lax" in cookie.lower()
    body = res.json()
    assert body["role"] == "admin"
    assert body["workspace"]["name"] == SIGNUP["workspace_name"]
    assert "users.admin" in body["capabilities"]


def test_signup_rejects_duplicates_and_needs_the_client_header(client: TestClient) -> None:
    assert client.post(f"{V}/auth/signup", json=SIGNUP).status_code == 403
    _signup(client)
    again = client.post(
        f"{V}/auth/signup", json={**SIGNUP, "email": "dana@example.com"}, headers=WEB_HEADERS
    )
    assert again.status_code == 409
    assert again.json()["code"] == "email_taken"


def test_login_failures_are_generic(client: TestClient) -> None:
    _signup(client)
    client.cookies.clear()
    wrong = client.post(
        f"{V}/auth/login",
        json={"email": SIGNUP["email"], "password": "not-the-password"},
        headers=WEB_HEADERS,
    )
    unknown = client.post(
        f"{V}/auth/login",
        json={"email": "nobody@example.com", "password": "not-the-password"},
        headers=WEB_HEADERS,
    )
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()
    assert "set-cookie" not in wrong.headers
    assert client.get(f"{V}/auth/me").status_code == 401


def test_login_me_logout(client: TestClient) -> None:
    _signup(client)
    client.cookies.clear()
    ok = client.post(
        f"{V}/auth/login",
        json={"email": SIGNUP["email"], "password": SIGNUP["password"]},
        headers=WEB_HEADERS,
    )
    assert ok.status_code == 200
    me = client.get(f"{V}/auth/me")
    assert me.status_code == 200
    assert me.json()["user"]["email"] == "dana@example.com"
    assert client.post(f"{V}/auth/logout", headers=WEB_HEADERS).status_code == 204
    assert client.get(f"{V}/auth/me").status_code == 401


def test_login_is_rate_limited(client: TestClient, settings: Settings) -> None:
    settings.login_rate_limit = 3
    body = {"email": "x@example.com", "password": "whatever-password"}
    codes = [
        client.post(f"{V}/auth/login", json=body, headers=WEB_HEADERS).status_code for _ in range(4)
    ]
    assert codes == [401, 401, 401, 429]
    last = client.post(f"{V}/auth/login", json=body, headers=WEB_HEADERS)
    assert int(last.headers["retry-after"]) > 0


def _login(app: Any, email: str, password: str, ip: str, via: str = "127.0.0.1") -> Any:
    """A login through a proxy at `via` for a client at `ip`."""
    c = TestClient(app, headers={**WEB_HEADERS, "X-Forwarded-For": ip}, client=(via, 1234))
    return c.post(f"{V}/auth/login", json={"email": email, "password": password})


def test_client_ip_trusts_forwarded_for_only_from_trusted_proxies(settings: Settings) -> None:
    def ip(peer: str, xff: str | None) -> str | None:
        headers = [(b"x-forwarded-for", xff.encode())] if xff is not None else []
        scope = {"type": "http", "client": (peer, 1), "headers": headers, "app": None}
        request = Request(scope)
        return client_ip(request, settings)

    assert ip("127.0.0.1", "203.0.113.9") == "203.0.113.9"
    assert ip("::1", "203.0.113.9") == "203.0.113.9"
    assert ip("127.0.0.1", "198.51.100.1, 203.0.113.9") == "203.0.113.9"  # rightmost untrusted
    assert ip("127.0.0.1", "203.0.113.9, 127.0.0.1") == "203.0.113.9"
    assert ip("127.0.0.1", "garbage") == "127.0.0.1"
    assert ip("127.0.0.1", None) == "127.0.0.1"
    assert ip("198.51.100.7", "203.0.113.9") == "198.51.100.7"  # spoofed: peer not trusted
    settings.trusted_proxies = ["10.0.0.0/8"]
    assert ip("10.1.2.3", "203.0.113.9") == "203.0.113.9"
    assert ip("127.0.0.1", "203.0.113.9") == "127.0.0.1"


def test_attacker_behind_the_proxy_cannot_lock_out_the_victim(
    app: Any, db: Session, workspace: Any, settings: Settings
) -> None:
    factories.make_user(db, workspace, Role.BROKER, email="victim@example.com")
    db.commit()
    clock = [0.0]
    app.state.rate_limiter = InMemoryRateLimiter(clock=lambda: clock[0])
    codes = [
        _login(app, "victim@example.com", "wrong-password", "203.0.113.66").status_code
        for _ in range(12)
    ]
    assert codes[:5] == [401] * 5 and 429 in codes  # the attacker is slowed down
    # The victim, behind the same proxy, is delayed by a short backoff at most.
    victim = _login(app, "victim@example.com", factories.DEFAULT_PASSWORD, "198.51.100.5")
    if victim.status_code == 429:
        wait = int(victim.headers["retry-after"])
        assert 0 < wait <= settings.login_backoff_max_s
        clock[0] += wait
        victim = _login(app, "victim@example.com", factories.DEFAULT_PASSWORD, "198.51.100.5")
    assert victim.status_code == 200, victim.text


def test_login_rate_limit_is_per_client_ip(app: Any, settings: Settings) -> None:
    settings.login_rate_limit = 3
    codes = [
        _login(app, f"u{i}@example.com", "wrong-password", "203.0.113.66").status_code
        for i in range(4)
    ]
    assert codes == [401, 401, 401, 429]
    other = _login(app, "u9@example.com", "wrong-password", "198.51.100.5")
    assert other.status_code == 401


def test_logout_revokes_the_session_token(app: Any, db: Session, workspace: Any) -> None:
    factories.make_user(db, workspace, Role.BROKER, email="leaver@example.com")
    db.commit()
    browser = TestClient(app, headers=WEB_HEADERS)
    res = browser.post(
        f"{V}/auth/login",
        json={"email": "leaver@example.com", "password": factories.DEFAULT_PASSWORD},
    )
    assert res.status_code == 200
    stolen = browser.cookies.get("js_session")
    other_device = TestClient(app).post(
        f"{V}/auth/token",
        data={"username": "leaver@example.com", "password": factories.DEFAULT_PASSWORD},
    )
    other_token = other_device.json()["access_token"]
    assert browser.post(f"{V}/auth/logout").status_code == 204
    for token in (stolen, other_token):  # logout ends every session of the user
        res = TestClient(app).get(f"{V}/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 401


def test_bearer_token_from_the_password_flow(client: TestClient) -> None:
    _signup(client)
    client.cookies.clear()
    res = client.post(
        f"{V}/auth/token", data={"username": SIGNUP["email"], "password": SIGNUP["password"]}
    )
    assert res.status_code == 200
    token = res.json()["access_token"]
    auth = {"Authorization": f"Bearer {token}"}
    assert client.get(f"{V}/auth/me", headers=auth).status_code == 200
    # Bearer requests are CSRF-exempt: no client header needed for a POST.
    assert client.post(f"{V}/trips", json=TRIP, headers=auth).status_code == 201
    bad = client.post(f"{V}/auth/token", data={"username": SIGNUP["email"], "password": "nope"})
    assert bad.status_code == 401


def test_csrf_header_is_required_for_cookie_writes(
    client: TestClient, db: Session, settings: Settings, workspace: object
) -> None:
    user = factories.make_user(db, workspace, Role.BROKER)  # type: ignore[arg-type]
    trip = factories.make_trip(db, workspace)  # type: ignore[arg-type]
    db.commit()
    client.cookies.set(settings.cookie_name, factories.bearer_token(settings, user))

    # Reads are fine without the header.
    assert client.get(f"{V}/trips").status_code == 200
    # JSON and multipart ("simple" request) writes are refused without it.
    res = client.post(f"{V}/trips", json=TRIP)
    assert res.status_code == 403
    assert res.json()["code"] == "csrf_failed"
    res = client.post(f"{V}/trips/{trip.id}/quotes/ingest", files={"file": ("q.txt", b"x")})
    assert res.status_code == 403
    assert res.json()["code"] == "csrf_failed"
    assert client.patch(f"{V}/trips/{trip.id}", json={"pax": 2}).status_code == 403
    assert client.delete(f"{V}/trips/{trip.id}").status_code == 403
    # With the header the same write succeeds.
    assert client.post(f"{V}/trips", json=TRIP, headers=WEB_HEADERS).status_code == 201


def test_deactivation_and_token_version_revoke_access(
    client_as: ClientFactory, db: Session
) -> None:
    broker = client_as(Role.BROKER)
    assert broker.get(f"{V}/auth/me").status_code == 200
    user = db.get(User, broker.user.id)  # type: ignore[attr-defined]
    assert user is not None
    user.token_version += 1
    db.commit()
    res = broker.get(f"{V}/auth/me")
    assert res.status_code == 401
    assert res.json()["code"] == "invalid_token"

    assistant = client_as(Role.ASSISTANT)
    admin = client_as(Role.ADMIN)
    uid = assistant.user.id  # type: ignore[attr-defined]
    assert admin.patch(f"{V}/users/{uid}", json={"is_active": False}).status_code == 200
    assert assistant.get(f"{V}/trips").status_code == 401


def test_role_changes_apply_immediately(client_as: ClientFactory) -> None:
    broker = client_as(Role.BROKER)
    admin = client_as(Role.ADMIN)
    assert broker.get(f"{V}/analytics/funnel").status_code == 200
    uid = broker.user.id  # type: ignore[attr-defined]
    assert admin.patch(f"{V}/users/{uid}", json={"role": "assistant"}).status_code == 200
    assert broker.get(f"{V}/analytics/funnel").status_code == 403


def test_forged_and_expired_tokens_are_rejected(
    client: TestClient, client_as: ClientFactory, settings: Settings
) -> None:
    broker = client_as(Role.BROKER)
    user = broker.user  # type: ignore[attr-defined]
    other = settings.model_copy(
        update={"secret_key": SecretStr("another-secret-key-that-is-long-enough-xx")}
    )
    forged, _ = create_access_token(
        other, user_id=user.id, workspace_id=user.workspace_id, token_version=user.token_version
    )
    res = client.get(f"{V}/auth/me", headers={"Authorization": f"Bearer {forged}"})
    assert res.status_code == 401

    expired, _ = create_access_token(
        settings,
        user_id=user.id,
        workspace_id=user.workspace_id,
        token_version=user.token_version,
        now=datetime.now(UTC) - timedelta(minutes=settings.access_token_ttl_min + 1),
    )
    res = client.get(f"{V}/auth/me", headers={"Authorization": f"Bearer {expired}"})
    assert res.status_code == 401
    assert client.get(f"{V}/auth/me", headers={"Authorization": "Bearer junk"}).status_code == 401


def test_change_password_reissues_the_cookie(browser_as: ClientFactory) -> None:
    web = browser_as(Role.BROKER)
    bad = web.post(
        f"{V}/auth/change-password",
        json={"current_password": "wrong-password!", "new_password": "brand-new-password"},
    )
    assert bad.status_code in {400, 401, 422}
    ok = web.post(
        f"{V}/auth/change-password",
        json={"current_password": factories.DEFAULT_PASSWORD, "new_password": "brand-new-password"},
    )
    assert ok.status_code == 200
    assert "js_session=" in ok.headers["set-cookie"]
    assert web.get(f"{V}/auth/me").status_code == 200
