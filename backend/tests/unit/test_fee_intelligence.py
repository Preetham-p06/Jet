"""Learned fee stats (pure) plus the thin observe/load round trip."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import AirportRole, AmountStatus, FeeCategory, ObservationSource
from app.models.intelligence import FeeObservation
from app.models.workspace import Workspace
from app.services.contracts import FeeObservationPoint, LearnedStat
from app.services.fee_intelligence import is_outlier, learned_stats, load_learned, observe_quote
from app.services.fee_rules import expected_fees
from app.services.fx import load_fx_table
from app.services.normalization import normalize_quote
from tests import factories
from tests.unit.demo_js184 import line, make_trip, state

F = FeeCategory
P = FeeObservationPoint


def test_learned_stats_frequency_and_quartiles() -> None:
    rows = [P(F.LANDING, True, a) for a in (10_000, 20_000, 30_000, 40_000)]
    rows += [P(F.LANDING, True, None), P(F.LANDING, False)]
    stat = learned_stats(rows)[F.LANDING]
    assert (stat.n, stat.n_amounts) == (6, 4)
    assert stat.frequency == 5 / 6
    assert (stat.p25_cents, stat.median_cents, stat.p75_cents) == (17_500, 25_000, 32_500)
    assert stat.iqr_cents == 15_000


def test_learned_stats_without_amounts() -> None:
    stat = learned_stats([P(F.DEICING, False), P(F.DEICING, False)])[F.DEICING]
    assert stat.frequency == 0 and stat.median_cents is None and stat.iqr_cents is None
    assert learned_stats([]) == {}
    single = learned_stats([P(F.CATERING, True, 12_345)])[F.CATERING]
    assert single.median_cents == single.p25_cents == single.p75_cents == 12_345


def test_is_outlier_needs_eight_amounts() -> None:
    stat = LearnedStat(
        n=10, frequency=1, median_cents=500, p25_cents=400, p75_cents=600, n_amounts=8
    )
    assert is_outlier(1_201, stat)
    assert not is_outlier(1_200, stat)
    assert not is_outlier(5_000, replace(stat, n_amounts=7))


def test_observe_and_load_round_trip(db: Session, workspace: Workspace) -> None:
    trip_row = factories.make_trip(db, workspace)
    op = factories.make_operator(db, workspace, "Atlas Jets")
    now = datetime(2026, 10, 1, tzinfo=UTC)
    trip = make_trip(workspace_id=workspace.id)
    fx = load_fx_table()
    quotes = []
    for i, ramp in enumerate((40_000, 45_000, 50_000)):
        q = factories.make_quote(db, trip_row, op)
        fees = [line(F.RAMP_HANDLING, AmountStatus.STATED, ramp)]
        if i == 0:
            fees.append(line(F.CATERING, AmountStatus.INCLUDED))
        s = state(tuple(fees), quote_id=q.id)
        tc = normalize_quote(s, trip, fx, expected_fees(s, trip))
        written = observe_quote(db, q, trip, tc, now=now)
        assert written == 2 * len(FeeCategory)  # KTEB departure + KOPF arrival
        quotes.append(q)
    # Re-observing replaces rather than duplicates.
    s = state((line(F.RAMP_HANDLING, AmountStatus.STATED, 40_000),), quote_id=quotes[0].id)
    observe_quote(db, quotes[0], trip, normalize_quote(s, trip, fx, []), now=now)
    rows = db.scalars(select(FeeObservation).where(FeeObservation.quote_id == quotes[0].id)).all()
    assert len(rows) == 2 * len(FeeCategory)
    ramp_row = next(
        r
        for r in rows
        if r.fee_category is F.RAMP_HANDLING and r.airport_role is AirportRole.DEPARTURE
    )
    assert (ramp_row.present, ramp_row.amount_cents, ramp_row.month) == (True, 40_000, 10)
    assert ramp_row.source is ObservationSource.EXTRACTED

    stats = load_learned(db, workspace.id, "KTEB", 10, exclude_quote_id=quotes[2].id)
    assert stats[F.RAMP_HANDLING].n == 2
    assert stats[F.RAMP_HANDLING].median_cents == 42_500
    assert stats[F.CATERING].frequency == 0
    # FET was synthetic (rule), so it is not an observation of the operator.
    assert stats[F.FET].frequency == 0
    assert load_learned(db, workspace.id, "KTEB", 7, exclude_quote_id=None) == {}
    widened = load_learned(db, workspace.id, "KTEB", 11, exclude_quote_id=None, month_window=1)
    assert widened[F.RAMP_HANDLING].n == 3
    other_ws = factories.make_workspace(db)
    assert load_learned(db, other_ws.id, "KTEB", 10, exclude_quote_id=None) == {}
