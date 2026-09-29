"""Shared fixtures: a fresh SQLite file and storage dir per test, the app, and
authenticated clients per role.

* `client`: an anonymous TestClient (sends no CSRF header by default).
* `client_as(role)`: a Bearer-authenticated client for a user of that role in
  the default workspace (or in `workspace=`).
* `browser_as(role)`: cookie-authenticated with the `X-JetStream-Client` header,
  like the dashboard.
* `two_workspaces`: workspaces A and B, each with one user per role and a trip.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.config import Environment, ExtractorChoice, Settings
from app.main import create_app
from app.models import Base, Trip, User, Workspace
from app.models.enums import Role
from app.security.csrf import CLIENT_HEADER, CLIENT_HEADER_VALUE
from app.security.ratelimit import InMemoryRateLimiter
from app.services.storage import LocalStorage
from tests import factories
from tests.fakes import FakeExtractor

WEB_HEADERS = {CLIENT_HEADER: CLIENT_HEADER_VALUE}
TEST_SECRET = "test-secret-key-that-is-long-enough-0123456789"  # noqa: S105


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    # TEST_DATABASE_URL lets the suite run against Postgres; SQLite file otherwise.
    url = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{tmp_path / 'test.db'}"
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        env=Environment.TEST,
        database_url=url,
        storage_dir=tmp_path / "storage",
        secret_key=TEST_SECRET,
        extractor=ExtractorChoice.RULES,
        anthropic_api_key=None,
        public_app_url="http://localhost:3001",
    )


@pytest.fixture
def fake_extractor() -> FakeExtractor:
    return FakeExtractor()


@pytest.fixture
def app(settings: Settings, fake_extractor: FakeExtractor) -> Iterator[FastAPI]:
    application = create_app(
        settings,
        storage=LocalStorage(settings.storage_dir),
        rate_limiter=InMemoryRateLimiter(),
    )
    application.state.extractor = fake_extractor
    engine = application.state.engine
    Base.metadata.create_all(engine)
    yield application
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def session_factory(app: FastAPI) -> sessionmaker[Session]:
    factory: sessionmaker[Session] = app.state.session_factory
    return factory


@pytest.fixture
def db(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    """An unscoped session for arranging data; commit before calling the API."""
    with session_factory() as session:
        yield session


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@dataclass
class Tenant:
    workspace: Workspace
    users: dict[Role, User]
    trip: Trip
    clients: dict[Role, TestClient] = field(default_factory=dict)

    @property
    def admin(self) -> TestClient:
        return self.clients[Role.ADMIN]

    @property
    def broker(self) -> TestClient:
        return self.clients[Role.BROKER]

    @property
    def assistant(self) -> TestClient:
        return self.clients[Role.ASSISTANT]


def _bearer_client(app: FastAPI, settings: Settings, user: User) -> TestClient:
    token = factories.bearer_token(settings, user)
    return TestClient(app, headers={"Authorization": f"Bearer {token}"})


def _make_tenant(app: FastAPI, settings: Settings, db: Session, name: str) -> Tenant:
    ws = factories.make_workspace(db, name)
    users = {role: factories.make_user(db, ws, role) for role in Role}
    trip = factories.make_trip(db, ws, reference="JS184")
    db.commit()
    tenant = Tenant(workspace=ws, users=users, trip=trip)
    tenant.clients = {role: _bearer_client(app, settings, u) for role, u in users.items()}
    return tenant


@pytest.fixture
def workspace(db: Session) -> Workspace:
    ws = factories.make_workspace(db, "JetStream Test Brokerage")
    db.commit()
    return ws


ClientFactory = Callable[..., TestClient]


@pytest.fixture
def client_as(
    app: FastAPI, settings: Settings, db: Session, workspace: Workspace
) -> Iterator[ClientFactory]:
    """`client_as(Role.BROKER)` -> a Bearer client; `.user` holds the user."""
    opened: list[TestClient] = []

    def make(role: Role | str, *, ws: Workspace | None = None) -> TestClient:
        user = factories.make_user(db, ws or workspace, Role(role))
        db.commit()
        test_client = _bearer_client(app, settings, user)
        test_client.user = user  # type: ignore[attr-defined]
        opened.append(test_client)
        return test_client

    yield make
    for c in opened:
        c.close()


@pytest.fixture
def browser_as(
    app: FastAPI, settings: Settings, db: Session, workspace: Workspace
) -> ClientFactory:
    """A cookie-authenticated client that sends the CSRF header, like the dashboard."""

    def make(role: Role | str, *, ws: Workspace | None = None) -> TestClient:
        user = factories.make_user(db, ws or workspace, Role(role))
        db.commit()
        test_client = TestClient(app, headers=WEB_HEADERS)
        test_client.cookies.set(settings.cookie_name, factories.bearer_token(settings, user))
        test_client.user = user  # type: ignore[attr-defined]
        return test_client

    return make


@dataclass
class TwoWorkspaces:
    a: Tenant
    b: Tenant


@pytest.fixture
def two_workspaces(app: FastAPI, settings: Settings, db: Session) -> TwoWorkspaces:
    """Workspaces A and B, each with admin/broker/assistant clients and a trip JS184."""
    return TwoWorkspaces(
        a=_make_tenant(app, settings, db, "Workspace A"),
        b=_make_tenant(app, settings, db, "Workspace B"),
    )
