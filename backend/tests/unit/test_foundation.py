"""Unit checks for foundation helpers: tenant guard, storage, money, tokens, rate limits."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import TenantViolation, set_workspace
from app.models import Operator, Trip
from app.security.ratelimit import InMemoryRateLimiter
from app.security.tokens import InvalidToken, create_access_token, decode_access_token
from app.services import money
from app.services.storage import LocalStorage, StorageError
from tests import factories


def test_tenant_guard_filters_reads_and_blocks_foreign_writes(db: Session) -> None:
    a = factories.make_workspace(db)
    b = factories.make_workspace(db)
    trip_b = factories.make_trip(db, b)
    factories.make_trip(db, a)
    db.commit()
    trip_b_id = trip_b.id
    db.expunge_all()

    set_workspace(db, a.id)
    assert {t.workspace_id for t in db.scalars(select(Trip))} == {a.id}
    assert db.get(Trip, trip_b_id) is None

    op = Operator(name="Atlas", normalized_name="atlas")
    db.add(op)
    db.flush()
    assert op.workspace_id == a.id  # filled in from the session

    db.add(Operator(workspace_id=b.id, name="Rogue", normalized_name="rogue"))
    with pytest.raises(TenantViolation):
        db.flush()


def test_storage_is_namespaced_and_traversal_safe(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path / "files")
    ws, other = uuid.uuid4(), uuid.uuid4()
    obj = storage.put(ws, b"%PDF-1.7", suffix=".pdf", content_type="application/pdf")
    assert obj.key.startswith(f"{ws}/")
    assert obj.size == 8
    assert storage.open(obj.key, workspace_id=ws) == b"%PDF-1.7"

    with pytest.raises(StorageError):
        storage.open(obj.key, workspace_id=other)
    with pytest.raises(StorageError):
        storage.open(f"{ws}/../../etc/passwd", workspace_id=ws)
    with pytest.raises(StorageError):
        storage.put(ws, b"x", suffix="/../x", content_type="text/plain")


def test_money_rounding() -> None:
    assert money.dollars_to_cents("41800.005") == 4180001
    assert money.percent_of(4180000, Decimal("7.5")) == 313500
    assert money.apply_markup(4482000, Decimal("5")) == 4706100  # 47,061.00
    assert money.minor_to_decimal(3250000, "EUR") == Decimal("32500.00")
    assert money.format_usd(4482000) == "$44,820"


def test_token_round_trip_and_expiry(settings: Settings) -> None:
    uid, wid = uuid.uuid4(), uuid.uuid4()
    token, _ = create_access_token(settings, user_id=uid, workspace_id=wid, token_version=3)
    claims = decode_access_token(settings, token)
    assert (claims.user_id, claims.workspace_id, claims.token_version) == (uid, wid, 3)

    old = datetime.now(UTC) - timedelta(days=2)
    expired, _ = create_access_token(
        settings, user_id=uid, workspace_id=wid, token_version=0, now=old
    )
    with pytest.raises(InvalidToken):
        decode_access_token(settings, expired)


def test_sliding_window_rate_limiter() -> None:
    clock = [0.0]
    limiter = InMemoryRateLimiter(clock=lambda: clock[0])
    assert all(limiter.hit("k", limit=2, window_s=10).allowed for _ in range(2))
    denied = limiter.hit("k", limit=2, window_s=10)
    assert not denied.allowed and denied.retry_after_s > 0
    clock[0] = 10.5
    assert limiter.hit("k", limit=2, window_s=10).allowed


def test_prod_settings_reject_default_secret() -> None:
    with pytest.raises(ValueError, match="SECRET_KEY"):
        Settings(_env_file=None, env="prod")  # type: ignore[call-arg]
    with pytest.raises(ValueError, match="SECRET_KEY"):
        Settings(_env_file=None, env="prod", secret_key="short")  # type: ignore[call-arg]


def test_quote_field_version_and_lock_constraint(db: Session) -> None:
    ws = factories.make_workspace(db)
    trip = factories.make_trip(db, ws)
    quote = factories.make_quote(db, trip, factories.make_operator(db, ws))
    field = factories.make_field(db, quote)
    assert field.version == 1
    field.confidence = 95
    db.flush()
    assert field.version == 2

    field.locked = True  # locked while still "extracted" violates the CHECK
    with pytest.raises(IntegrityError):
        db.flush()
