"""Helpers for the proposal, analytics and audit-query service tests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Operator, Quote, Trip, Workspace
from app.models.enums import AircraftCategory, QuoteStatus, Role
from app.permissions import RequestContext
from tests import factories

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


def make_ctx(db: Session, workspace: Workspace, role: Role = Role.BROKER) -> RequestContext:
    user = factories.make_user(db, workspace, role)
    return RequestContext(
        user=user, workspace=workspace, role=role, request_id="req-test", ip="203.0.113.9"
    )


def make_ready_quote(
    db: Session,
    trip: Trip,
    operator: Operator,
    *,
    known_total_cents: int = 4_283_000,
    **kw: Any,
) -> Quote:
    """A quote the engine would call proposal-ready: priced, no flags, seats the pax."""
    defaults: dict[str, Any] = {
        "status": QuoteStatus.ACTIVE,
        "headline_cents": known_total_cents - 300_000,
        "known_total_cents": known_total_cents,
        "upper_total_cents": known_total_cents,
        "is_fully_priced": True,
        "open_blocking_flags": 0,
        "quote_confidence": 92,
        "seats": 8,
        "wifi": True,
        "flight_time_minutes": 165,
        "aircraft_model": "Citation Latitude",
        "aircraft_category": AircraftCategory.MIDSIZE,
        "tail_number": "N684AC",
        "first_received_at": NOW,
    }
    defaults.update(kw)
    return factories.make_quote(db, trip, operator, **defaults)


def p5_settings() -> Settings:
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        secret_key="test-secret-key-that-is-long-enough-0123456789",  # noqa: S106
        public_app_url="https://app.example.test",
    )
