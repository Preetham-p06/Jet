"""Analytics service: the six metrics of spec §7, workspace-scoped with a date range."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.models import FeeLine, Quote, Workspace
from app.models.enums import (
    AircraftCategory,
    AmountStatus,
    FeeCategory,
    IncludedBy,
    ProposalStatus,
    QuoteStatus,
    TripStatus,
)
from app.permissions import RequestContext
from app.schemas.analytics import AnalyticsMetric
from app.services import analytics
from app.services.analytics import DateRange
from tests import factories
from tests.factories_p5 import make_ctx, make_ready_quote

RNG = DateRange(date(2026, 8, 1), date(2026, 10, 31))


def at(month: int, day: int = 10, hour: int = 12) -> datetime:
    return datetime(2026, month, day, hour, tzinfo=UTC)


def fee(
    db: Session, quote: Quote, category: FeeCategory, status: AmountStatus, **kw: object
) -> None:
    field = None
    if kw.pop("synthetic", False) is False:
        field = factories.make_field(db, quote, key=f"fee.{category.value}", value=None)
    db.add(
        FeeLine(
            workspace_id=quote.workspace_id,
            quote_id=quote.id,
            field_id=field.id if field else None,
            category=category,
            label=category.value,
            amount_status=status,
            **kw,
        )
    )


@dataclass
class Env:
    ws: Workspace
    ctx: RequestContext
    quotes: list[Quote]


@pytest.fixture
def env(db: Session) -> Env:
    ws = factories.make_workspace(db)
    ctx = make_ctx(db, ws)
    op1 = factories.make_operator(db, ws, "Atlas Air")
    op2 = factories.make_operator(db, ws, "SkyBridge")

    t1 = factories.make_trip(db, ws, created_at=at(8, 1))
    t2 = factories.make_trip(db, ws, created_at=at(9, 1))
    t3 = factories.make_trip(db, ws, created_at=at(10, 1))
    factories.make_trip(db, ws, created_at=at(10, 2))  # never quoted
    factories.make_trip(db, ws, created_at=at(3, 1))  # out of range

    q1 = make_ready_quote(
        db, t1, op1, known_total_cents=4_283_000, first_received_at=at(8),
        aircraft_category=AircraftCategory.MIDSIZE,
    )  # fmt: skip
    q2 = make_ready_quote(
        db, t1, op2, known_total_cents=4_398_000, first_received_at=at(8, 20),
        aircraft_category=AircraftCategory.SUPER_MIDSIZE,
    )  # fmt: skip
    q3 = make_ready_quote(
        db, t2, op1, known_total_cents=5_100_000, first_received_at=at(10),
        is_fully_priced=False, aircraft_category=AircraftCategory.MIDSIZE,
    )  # fmt: skip
    q4 = make_ready_quote(
        db, t3, op2, known_total_cents=6_000_000, first_received_at=at(10, 15),
        aircraft_category=None,
    )  # fmt: skip
    # Excluded: withdrawn, out of range, other workspace.
    make_ready_quote(db, t2, op2, status=QuoteStatus.WITHDRAWN, first_received_at=at(9))
    make_ready_quote(db, t2, op1, first_received_at=at(3))
    other = factories.make_workspace(db)
    other_trip = factories.make_trip(db, other, created_at=at(9))
    make_ready_quote(db, other_trip, factories.make_operator(db, other), first_received_at=at(9))

    fee(db, q1, FeeCategory.FUEL_SURCHARGE, AmountStatus.STATED, amount_cents=100)
    fee(db, q1, FeeCategory.CATERING, AmountStatus.INCLUDED)
    fee(db, q2, FeeCategory.FUEL_SURCHARGE, AmountStatus.NOT_STATED)
    fee(
        db,
        q2,
        FeeCategory.FET,
        AmountStatus.INCLUDED,
        included_by=IncludedBy.ALL_IN,
        synthetic=True,
    )
    fee(db, q3, FeeCategory.DEICING, AmountStatus.NOT_STATED, synthetic=True)
    fee(db, q3, FeeCategory.CATERING, AmountStatus.ESTIMATED)
    fee(db, q4, FeeCategory.LANDING, AmountStatus.WAIVED)

    factories.make_trip_operator(
        db, t1, op1, requested_at=at(8, 1, 8), responded_at=at(8, 1, 10)
    )  # 2h
    factories.make_trip_operator(
        db, t1, op2, requested_at=at(8, 1, 8), responded_at=at(8, 1, 14)
    )  # 6h
    factories.make_trip_operator(
        db, t2, op1, requested_at=at(9, 1, 8), responded_at=at(9, 1, 12)
    )  # 4h
    factories.make_trip_operator(db, t3, op1, requested_at=at(10, 1, 8))  # no response
    factories.make_trip_operator(
        db, t3, op2, requested_at=at(3, 1, 8), responded_at=at(3, 1, 9)
    )  # out of range

    factories.make_proposal(db, t1, status=ProposalStatus.BOOKED, sent_at=at(8, 5))
    factories.make_proposal(db, t2, status=ProposalStatus.SENT, sent_at=at(9, 5))
    factories.make_proposal(db, t3)  # draft: not sent
    t1.status = TripStatus.BOOKED
    t1.booked_quote_id = q1.id
    t1.booked_at = at(8, 6)
    db.commit()
    return Env(ws, ctx, [q1, q2, q3, q4])


def test_quote_volume(db: Session, env: Env) -> None:
    out = analytics.quote_volume(db, env.ctx, RNG)
    assert [(m.month, m.count) for m in out.items] == [
        ("2026-08", 2),
        ("2026-09", 0),
        ("2026-10", 2),
    ]


def test_response_times(db: Session, env: Env) -> None:
    out = analytics.response_times(db, env.ctx, RNG)
    assert out.n == 3 and out.median_hours == 4.0
    by_name = {o.operator_name: (o.median_hours, o.n) for o in out.operators}
    assert by_name == {"Atlas Air": (3.0, 2), "SkyBridge": (6.0, 1)}
    assert out.operators[0].operator_name == "Atlas Air"


def test_true_cost_distribution(db: Session, env: Env) -> None:
    out = analytics.true_cost_distribution(db, env.ctx, RNG)
    assert out.n == 4
    assert [(b.lower_cents, b.count, b.lower_bound_count) for b in out.bins] == [
        (4_000_000, 2, 0),
        (4_500_000, 0, 0),
        (5_000_000, 1, 1),
        (5_500_000, 0, 0),
        (6_000_000, 1, 0),
    ]
    assert out.median_cents == 4_749_000
    assert out.p25_cents == 4_369_250
    assert out.p75_cents == 5_325_000


def test_fee_types(db: Session, env: Env) -> None:
    out = analytics.fee_types(db, env.ctx, RNG)
    assert out.n_quotes == 4
    shares = {i.category: (i.count, i.share_pct) for i in out.items}
    assert shares == {
        FeeCategory.FUEL_SURCHARGE: (2, 50.0),
        FeeCategory.CATERING: (1, 25.0),
    }
    assert out.items[0].label


def test_aircraft_mix(db: Session, env: Env) -> None:
    out = analytics.aircraft_mix(db, env.ctx, RNG)
    assert out.n_quotes == 4
    mix = {i.category: (i.count, i.share_pct) for i in out.items}
    assert mix == {"midsize": (2, 50.0), "super_midsize": (1, 25.0), "unknown": (1, 25.0)}
    assert out.items[0].category == "midsize"


def test_funnel_only_narrows(db: Session, env: Env) -> None:
    out = analytics.funnel(db, env.ctx, RNG)
    assert (out.created, out.quoted, out.proposal_sent, out.booked) == (4, 3, 2, 1)


def test_overview_and_compute_metric(db: Session, env: Env) -> None:
    ov = analytics.overview(db, env.ctx, RNG)
    assert ov.date_from == RNG.date_from and ov.funnel.created == 4
    for metric in AnalyticsMetric:
        out = analytics.compute_metric(db, env.ctx, metric, RNG)
        assert out.metric == metric.value


def test_empty_workspace(db: Session) -> None:
    ws = factories.make_workspace(db)
    ctx = make_ctx(db, ws)
    db.commit()
    rng = DateRange(date(2026, 10, 1), date(2026, 10, 1) + timedelta(days=5))
    tc = analytics.true_cost_distribution(db, ctx, rng)
    assert tc.bins == [] and tc.median_cents is None
    rt = analytics.response_times(db, ctx, rng)
    assert rt.median_hours is None and rt.operators == []
    assert analytics.fee_types(db, ctx, rng).items == []
    assert analytics.funnel(db, ctx, rng).created == 0
