"""`recompute_trip`: derived columns, fee lines, flag reconciliation, observations and
the recommendation row (spec §4-5)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AuditEvent,
    FeeLine,
    FeeObservation,
    Flag,
    Quote,
    Recommendation,
    Trip,
    Workspace,
)
from app.models.enums import (
    FieldGroup,
    FlagResolution,
    FlagSeverity,
    FlagStatus,
    FlagType,
    QuoteStatus,
    ValueType,
)
from app.services import recompute
from app.services.contracts import FlagSpec, flag_fingerprint
from tests import factories

pytestmark = pytest.mark.integration

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


def usd(dollars: int) -> dict[str, Any]:
    return {"amount_minor": dollars * 100, "currency": "USD"}


def fee_value(category: str, status: str, dollars: int | None = None, **kw: Any) -> dict[str, Any]:
    return {
        "category": category,
        "label": kw.pop("label", category),
        "status": status,
        "amount": usd(dollars) if dollars is not None else None,
        "unit": "flat",
        "quantity": None,
        "percent": kw.pop("percent", None),
        "explicitly_extra": kw.pop("explicitly_extra", False),
        "hedged": kw.pop("hedged", False),
    }


def add_fee(
    db: Session, quote: Quote, category: str, status: str, dollars: int | None, **kw: Any
) -> Any:
    confidence = kw.pop("confidence", 95)
    return factories.make_field(
        db,
        quote,
        f"fee.{category}",
        fee_value(category, status, dollars, **kw),
        value_type=ValueType.FEE,
        group=FieldGroup.FEE,
        label=category,
        confidence=confidence,
        snippet_verified=True,
    )


def make_quote(
    db: Session, trip: Trip, name: str, *, headline: int, seats: int = 9, **kw: Any
) -> Quote:
    workspace = db.get(Workspace, trip.workspace_id)
    assert workspace is not None
    operator = factories.make_operator(db, workspace, name)
    quote = factories.make_quote(db, trip, operator, created_at=NOW)
    scalars: dict[str, tuple[Any, ValueType]] = {
        "headline_price": (usd(headline), ValueType.MONEY),
        "aircraft_model": (kw.pop("model", "Bombardier Challenger 350"), ValueType.TEXT),
        "aircraft_category": (kw.pop("category", "super_midsize"), ValueType.TEXT),
        "seats": (seats, ValueType.INT),
        "wifi": (kw.pop("wifi", True), ValueType.BOOL),
        "flight_time_minutes": (kw.pop("flight_time", 170), ValueType.DURATION),
        "departure_local": ("2026-10-18T09:00", ValueType.DATETIME),
        "availability": ("available", ValueType.TEXT),
    }
    for key, (value, vtype) in scalars.items():
        factories.make_field(
            db, quote, key, value, value_type=vtype, confidence=92, snippet_verified=True
        )
    add_fee(db, quote, "fet", "included", None)
    add_fee(db, quote, "segment_fees", "included", None)
    return quote


@pytest.fixture
def trip(db: Session) -> Trip:
    ws = factories.make_workspace(db, "Recompute Brokerage")
    return factories.make_trip(db, ws, reference="JS184")


def flags(db: Session, quote: Quote) -> dict[str, Flag]:
    return {f.fingerprint: f for f in db.scalars(select(Flag).where(Flag.quote_id == quote.id))}


def test_no_quotes_returns_none(db: Session, trip: Trip) -> None:
    assert recompute.recompute_trip(db, trip, now=NOW) is None


def test_derived_columns_fee_lines_and_recommendation(db: Session, trip: Trip) -> None:
    a = make_quote(db, trip, "Alpha", headline=40_000)
    add_fee(db, a, "positioning", "stated", 1_000)
    b = make_quote(db, trip, "Bravo", headline=45_000)
    result = recompute.recompute_trip(db, trip, now=NOW)
    assert result is not None and result.recommended_quote_id == a.id

    assert a.headline_cents == 4_000_000 and a.known_total_cents == 4_100_000
    assert a.upper_total_cents == 4_100_000 and a.is_fully_priced
    assert a.seats == 9 and a.wifi is True and a.aircraft_model == "Bombardier Challenger 350"
    assert a.departure_local == datetime(2026, 10, 18, 9, 0)
    assert a.quote_confidence == 92 and a.computed_at == NOW and a.calc_version == "calc-1"
    assert a.is_recommended and not b.is_recommended
    assert a.eligible_for_proposal and a.eligibility_reasons == []

    lines = db.scalars(select(FeeLine).where(FeeLine.quote_id == a.id)).all()
    assert {ln.category.value for ln in lines} >= {"positioning", "fet", "segment_fees"}
    # Rebuilding does not accumulate lines.
    recompute.recompute_trip(db, trip, now=NOW)
    assert len(db.scalars(select(FeeLine).where(FeeLine.quote_id == a.id)).all()) == len(lines)

    fb = a.fit_breakdown
    assert fb is not None and set(fb) == {"fit", "signals", "schedule_subscore"}
    assert {s["key"] for s in fb["signals"]} >= {"pricing", "fees", "routing"}
    assert set(fb["signals"][0]) == {
        "key",
        "weight",
        "raw",
        "value",
        "imputed",
        "dropped",
        "detail",
    }

    rec = db.scalars(select(Recommendation).order_by(Recommendation.computed_at.desc())).first()
    assert rec is not None and rec.recommended_quote_id == a.id
    assert rec.weights["pricing"] == 30
    assert set(rec.ranking) == {"ranking", "checks"}
    entry = rec.ranking["ranking"][0]
    assert set(entry) == {"quote_id", "rank", "fit", "eligible", "reasons", "signals"}
    assert entry["quote_id"] == str(a.id) and entry["rank"] == 1
    assert {c["key"] for c in rec.ranking["checks"]} == {
        "schedule",
        "lowest_cost",
        "wifi",
        "seats",
        "no_crew_overnight",
    }
    obs = db.scalars(select(FeeObservation).where(FeeObservation.quote_id == a.id)).all()
    assert obs and {o.airport_icao for o in obs} == {"KTEB", "KOPF"}


def test_blocking_flag_keeps_quote_not_fully_priced(db: Session, trip: Trip) -> None:
    q = make_quote(db, trip, "Summit", headline=38_900)
    add_fee(db, q, "fuel_surcharge", "estimated", 850, hedged=True, confidence=61)
    recompute.recompute_trip(db, trip, now=NOW)
    fuel = flags(db, q)["ambiguous_charge:fuel_surcharge"]
    assert fuel.blocking and fuel.status is FlagStatus.OPEN
    assert fuel.severity is FlagSeverity.WARNING
    assert q.open_blocking_flags == 1 and not q.is_fully_priced
    assert q.quote_confidence == 61 and q.pending_review_count == 1
    assert not q.eligible_for_proposal
    codes = {r["code"] for r in q.eligibility_reasons}
    assert {"blocking_flags", "not_fully_priced", "unreviewed_low_confidence"} <= codes


def test_capacity_flag_blocks_even_when_priced(db: Session, trip: Trip) -> None:
    q = make_quote(db, trip, "Tiny", headline=20_000, seats=5)
    recompute.recompute_trip(db, trip, now=NOW)
    assert flags(db, q)["capacity_insufficient"].blocking
    assert not q.is_fully_priced  # an open blocking flag keeps the "+"
    assert q.known_total_cents == q.upper_total_cents


def test_reconcile_update_autoclear_keep_and_reopen(db: Session, trip: Trip) -> None:
    q = make_quote(db, trip, "Recon", headline=10_000)
    recompute.recompute_trip(db, trip, now=NOW)

    def spec(message: str, **details: Any) -> FlagSpec:
        return FlagSpec(
            type=FlagType.TOTAL_MISMATCH,
            severity=FlagSeverity.WARNING,
            fingerprint=flag_fingerprint(FlagType.TOTAL_MISMATCH),
            message=message,
            details=details,
        )

    rep = recompute.reconcile_flags(db, q, [spec("first", d=1)], now=NOW)
    assert len(rep.created) == 1
    flag = rep.created[0]
    assert flag.status is FlagStatus.OPEN and flag.blocking

    rep = recompute.reconcile_flags(db, q, [spec("second", d=2)], now=NOW)
    assert rep.updated == [flag] and flag.message == "second"

    # Resolved by a human: kept while the data is unchanged ...
    flag.status, flag.resolution = FlagStatus.RESOLVED, FlagResolution.ACKNOWLEDGED
    rep = recompute.reconcile_flags(db, q, [spec("second", d=2)], now=NOW)
    assert flag.status is FlagStatus.RESOLVED and not rep.reopened
    # ... and reopened (audited) when it changes.
    rep = recompute.reconcile_flags(db, q, [spec("third", d=3)], now=NOW)
    assert rep.reopened == [flag] and flag.status is FlagStatus.OPEN
    assert flag.resolution is None
    audit_row = db.scalars(select(AuditEvent).where(AuditEvent.action == "flag.auto_reopen")).one()
    assert audit_row.entity_id == flag.id and audit_row.before["status"] == "resolved"

    # Condition gone: auto-cleared; it comes back without an audit entry.
    rep = recompute.reconcile_flags(db, q, [], now=NOW)
    assert rep.auto_cleared == [flag]
    assert flag.status is FlagStatus.RESOLVED and flag.resolution is FlagResolution.AUTO_CLEARED
    rep = recompute.reconcile_flags(db, q, [spec("third", d=3)], now=NOW)
    assert rep.reopened == [flag] and flag.status is FlagStatus.OPEN
    assert (
        len(db.scalars(select(AuditEvent).where(AuditEvent.action == "flag.auto_reopen")).all())
        == 1
    )

    # A dismissed flag with unchanged data stays dismissed.
    flag.status, flag.resolution = FlagStatus.DISMISSED, FlagResolution.DISMISSED
    recompute.reconcile_flags(db, q, [spec("third", d=3)], now=NOW)
    assert flag.status is FlagStatus.DISMISSED


def test_withdrawn_quotes_are_not_recommended_or_observed(db: Session, trip: Trip) -> None:
    a = make_quote(db, trip, "Alpha", headline=30_000)
    b = make_quote(db, trip, "Bravo", headline=45_000)
    a.status = QuoteStatus.WITHDRAWN
    result = recompute.recompute_trip(db, trip, now=NOW)
    assert result is not None and result.recommended_quote_id == b.id
    assert not a.eligible_for_proposal
    assert db.scalars(select(FeeObservation).where(FeeObservation.quote_id == a.id)).all() == []


def test_parse_helpers() -> None:
    assert recompute.parse_valid_until("2026-10-10") == datetime(
        2026, 10, 10, 23, 59, 59, tzinfo=UTC
    )
    assert recompute.parse_valid_until("2026-10-10T08:00") == datetime(2026, 10, 10, 8, tzinfo=UTC)
    assert recompute.parse_valid_until("soon") is None
    assert recompute.parse_local_datetime("2026-10-18T09:30") == datetime(2026, 10, 18, 9, 30)
