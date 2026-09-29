"""Row factories for tests. Every factory flushes and returns the ORM object."""

from __future__ import annotations

import itertools
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.config import Settings
from app.models import (
    Flag,
    Operator,
    Proposal,
    Quote,
    QuoteField,
    SourceDocument,
    Trip,
    TripLeg,
    TripOperator,
    User,
    Workspace,
)
from app.models.enums import (
    DocumentChannel,
    DocumentKind,
    ExtractorKind,
    FieldGroup,
    FlagSeverity,
    FlagType,
    Role,
    ValueType,
)
from app.security.passwords import hash_password
from app.security.tokens import create_access_token
from app.services.operators import normalize_operator_name

DEFAULT_PASSWORD = "correct-horse-battery"
_seq = itertools.count(1)

# One hash for every factory user keeps the suite fast (argon2 is deliberately slow).
_PASSWORD_HASH: str | None = None


def _password_hash(password: str) -> str:
    global _PASSWORD_HASH
    if password != DEFAULT_PASSWORD:
        return hash_password(password)
    if _PASSWORD_HASH is None:
        _PASSWORD_HASH = hash_password(DEFAULT_PASSWORD)
    return _PASSWORD_HASH


def now() -> datetime:
    return datetime.now(UTC)


def make_workspace(db: Session, name: str | None = None, **kw: Any) -> Workspace:
    n = next(_seq)
    ws = Workspace(name=name or f"Brokerage {n}", slug=kw.pop("slug", f"brokerage-{n}"), **kw)
    db.add(ws)
    db.flush()
    return ws


def make_user(
    db: Session,
    workspace: Workspace,
    role: Role = Role.ADMIN,
    *,
    email: str | None = None,
    password: str = DEFAULT_PASSWORD,
    **kw: Any,
) -> User:
    user = User(
        workspace_id=workspace.id,
        email=email or f"{role.value}{next(_seq)}@example.com",
        full_name=kw.pop("full_name", f"{role.value.title()} User"),
        password_hash=_password_hash(password),
        role=role,
        **kw,
    )
    db.add(user)
    db.flush()
    return user


def make_operator(
    db: Session, workspace: Workspace, name: str | None = None, **kw: Any
) -> Operator:
    name = name or f"Operator {next(_seq)}"
    op = Operator(
        workspace_id=workspace.id, name=name, normalized_name=normalize_operator_name(name), **kw
    )
    db.add(op)
    db.flush()
    return op


def make_trip(
    db: Session,
    workspace: Workspace,
    *,
    reference: str | None = None,
    pax: int = 7,
    legs: Sequence[tuple[str, str, datetime]] = (("KTEB", "KOPF", datetime(2026, 10, 18, 9, 0)),),
    **kw: Any,
) -> Trip:
    trip = Trip(
        workspace_id=workspace.id,
        reference=reference or f"JS{next(_seq) + 100}",
        pax=pax,
        preferences=kw.pop("preferences", {"wifi_required": True}),
        **kw,
    )
    trip.legs = [
        TripLeg(
            workspace_id=workspace.id,
            seq=i,
            origin_icao=o,
            destination_icao=d,
            depart_local=t,
            depart_tz="America/New_York",
        )
        for i, (o, d, t) in enumerate(legs, start=1)
    ]
    db.add(trip)
    db.flush()
    return trip


def make_trip_operator(db: Session, trip: Trip, operator: Operator, **kw: Any) -> TripOperator:
    row = TripOperator(
        workspace_id=trip.workspace_id,
        trip_id=trip.id,
        operator_id=operator.id,
        requested_at=kw.pop("requested_at", now()),
        **kw,
    )
    db.add(row)
    db.flush()
    return row


def make_quote(db: Session, trip: Trip, operator: Operator, **kw: Any) -> Quote:
    quote = Quote(workspace_id=trip.workspace_id, trip_id=trip.id, operator_id=operator.id, **kw)
    db.add(quote)
    db.flush()
    return quote


def make_document(db: Session, trip: Trip, **kw: Any) -> SourceDocument:
    doc = SourceDocument(
        workspace_id=trip.workspace_id,
        trip_id=trip.id,
        kind=kw.pop("kind", DocumentKind.TEXT),
        channel=kw.pop("channel", DocumentChannel.PASTE),
        media_type=kw.pop("media_type", "text/plain"),
        storage_key=kw.pop("storage_key", f"{trip.workspace_id}/2026/10/{uuid.uuid4().hex}.txt"),
        size_bytes=kw.pop("size_bytes", 0),
        sha256=kw.pop("sha256", uuid.uuid4().hex * 2),
        **kw,
    )
    db.add(doc)
    db.flush()
    return doc


def make_field(
    db: Session, quote: Quote, key: str = "seats", value: Any = 8, **kw: Any
) -> QuoteField:
    field = QuoteField(
        workspace_id=quote.workspace_id,
        quote_id=quote.id,
        key=key,
        group=kw.pop("group", FieldGroup.FEE if key.startswith("fee.") else FieldGroup.SCALAR),
        value_type=kw.pop("value_type", ValueType.INT),
        original_value=value,
        current_value=value,
        confidence=kw.pop("confidence", 90),
        extractor=kw.pop("extractor", ExtractorKind.RULES),
        **kw,
    )
    db.add(field)
    db.flush()
    return field


def make_flag(db: Session, quote: Quote, **kw: Any) -> Flag:
    flag_type = kw.pop("type", FlagType.AMBIGUOUS_CHARGE)
    flag = Flag(
        workspace_id=quote.workspace_id,
        trip_id=quote.trip_id,
        quote_id=quote.id,
        type=flag_type,
        severity=kw.pop("severity", FlagSeverity.WARNING),
        blocking=kw.pop("blocking", True),
        fingerprint=kw.pop("fingerprint", f"{flag_type.value}:{next(_seq)}"),
        data_hash=kw.pop("data_hash", "0" * 64),
        message=kw.pop("message", "Fuel surcharge not stated"),
        **kw,
    )
    db.add(flag)
    db.flush()
    return flag


def make_proposal(db: Session, trip: Trip, **kw: Any) -> Proposal:
    proposal = Proposal(
        workspace_id=trip.workspace_id,
        trip_id=trip.id,
        title=kw.pop("title", f"{trip.reference} options"),
        **kw,
    )
    db.add(proposal)
    db.flush()
    return proposal


def bearer_token(settings: Settings, user: User) -> str:
    token, _ = create_access_token(
        settings,
        user_id=user.id,
        workspace_id=user.workspace_id,
        token_version=user.token_version,
    )
    return token
