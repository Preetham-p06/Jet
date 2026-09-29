"""Workspace analytics (spec §7), aggregated in Python for portability.

Default range: the 12 months up to `now`.
"""

from __future__ import annotations

import statistics
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import (
    FEE_CATEGORY_ORDER,
    AircraftCategory,
    AmountStatus,
    FeeCategory,
    QuoteStatus,
)
from app.models.operator import Operator
from app.models.proposal import Proposal
from app.models.quote import FeeLine, Quote
from app.models.trip import Trip, TripOperator
from app.permissions import RequestContext, scoped
from app.schemas.analytics import (
    AircraftMixOut,
    AnalyticsMetric,
    AnalyticsMetricOut,
    AnalyticsOverviewOut,
    CategoryShare,
    CostBin,
    FeeShare,
    FeeTypesOut,
    FunnelOut,
    MonthCount,
    OperatorResponseTime,
    QuoteVolumeOut,
    ResponseTimesOut,
    TrueCostDistributionOut,
)
from app.schemas.meta import AIRCRAFT_CATEGORY_LABELS, FEE_CATEGORY_LABELS
from app.services.money import round_half_up

TRUE_COST_BIN_CENTS = 500_000  # $5k

#: Fee line statuses that count as the quote "carrying" the fee.
_FEE_PRESENT = frozenset({AmountStatus.STATED, AmountStatus.ESTIMATED, AmountStatus.NOT_STATED})


@dataclass(frozen=True, slots=True)
class DateRange:
    date_from: date
    date_to: date  # inclusive

    @property
    def start(self) -> datetime:
        return datetime.combine(self.date_from, time.min, tzinfo=UTC)

    @property
    def end(self) -> datetime:
        """Exclusive upper bound."""
        return datetime.combine(self.date_to + timedelta(days=1), time.min, tzinfo=UTC)


def _add_months(d: date, months: int) -> date:
    idx = d.year * 12 + (d.month - 1) + months
    return date(idx // 12, idx % 12 + 1, 1)


def default_range(today: date) -> DateRange:
    """Twelve calendar months ending with the current one."""
    return DateRange(date_from=_add_months(today.replace(day=1), -11), date_to=today)


# --------------------------------------------------------------------------- helpers


def _quote_time(q: Quote) -> datetime:
    return q.first_received_at or q.created_at


def _active_quotes(db: Session, ctx: RequestContext, rng: DateRange) -> list[Quote]:
    stmt = scoped(select(Quote).where(Quote.status == QuoteStatus.ACTIVE), ctx)
    return [q for q in db.scalars(stmt) if rng.start <= _quote_time(q) < rng.end]


def _pct(count: int, n: int) -> float:
    if n == 0:
        return 0.0
    return float(round_half_up(Decimal(count) * 100 / n, Decimal("0.1")))


def _hours(value: float) -> float:
    return float(round_half_up(Decimal(str(value)), Decimal("0.01")))


def percentile(sorted_values: list[int], p: float) -> int | None:
    """Linear interpolation between closest ranks, rounded half up to a cent."""
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return sorted_values[0]
    pos = Decimal(str(p)) * (len(sorted_values) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = pos - lo
    value = Decimal(sorted_values[lo]) + (sorted_values[hi] - sorted_values[lo]) * frac
    return int(round_half_up(value))


# --------------------------------------------------------------------------- metrics


def quote_volume(db: Session, ctx: RequestContext, rng: DateRange) -> QuoteVolumeOut:
    """Active quotes per month of `first_received_at`."""
    counts = Counter(_quote_time(q).strftime("%Y-%m") for q in _active_quotes(db, ctx, rng))
    items: list[MonthCount] = []
    month = rng.date_from.replace(day=1)
    while month <= rng.date_to:
        key = month.strftime("%Y-%m")
        items.append(MonthCount(month=key, count=counts.get(key, 0)))
        month = _add_months(month, 1)
    return QuoteVolumeOut(items=items)


def response_times(db: Session, ctx: RequestContext, rng: DateRange) -> ResponseTimesOut:
    """Median hours from requested_at to responded_at, overall and per operator."""
    stmt = scoped(
        select(TripOperator).where(
            TripOperator.responded_at.is_not(None),
            TripOperator.requested_at >= rng.start,
            TripOperator.requested_at < rng.end,
        ),
        ctx,
    )
    per_operator: dict[uuid.UUID, list[float]] = defaultdict(list)
    overall: list[float] = []
    for row in db.scalars(stmt):
        if row.responded_at is None:
            continue
        hours = (row.responded_at - row.requested_at).total_seconds() / 3600
        if hours < 0:
            continue
        overall.append(hours)
        per_operator[row.operator_id].append(hours)

    names = {
        op.id: op.name
        for op in db.scalars(
            scoped(select(Operator).where(Operator.id.in_(list(per_operator))), ctx)
        )
    }
    operators = [
        OperatorResponseTime(
            operator_id=op_id,
            operator_name=names.get(op_id, "Unknown operator"),
            median_hours=_hours(statistics.median(values)),
            n=len(values),
        )
        for op_id, values in per_operator.items()
    ]
    operators.sort(key=lambda o: (o.median_hours, o.operator_name))
    return ResponseTimesOut(
        median_hours=_hours(statistics.median(overall)) if overall else None,
        n=len(overall),
        operators=operators,
    )


def true_cost_distribution(
    db: Session, ctx: RequestContext, rng: DateRange
) -> TrueCostDistributionOut:
    """$5k bins of known_total over active quotes; lower-bound quotes counted per bin."""
    priced = [q for q in _active_quotes(db, ctx, rng) if q.known_total_cents is not None]
    values = sorted(q.known_total_cents for q in priced if q.known_total_cents is not None)
    bins: list[CostBin] = []
    if priced:
        size = TRUE_COST_BIN_CENTS
        counts: Counter[int] = Counter()
        lower: Counter[int] = Counter()
        for q in priced:
            b = (q.known_total_cents or 0) // size
            counts[b] += 1
            if not q.is_fully_priced:
                lower[b] += 1
        for b in range(min(counts), max(counts) + 1):
            bins.append(
                CostBin(
                    lower_cents=b * size,
                    upper_cents=(b + 1) * size,
                    count=counts.get(b, 0),
                    lower_bound_count=lower.get(b, 0),
                )
            )
    return TrueCostDistributionOut(
        bin_size_cents=TRUE_COST_BIN_CENTS,
        bins=bins,
        n=len(values),
        p25_cents=percentile(values, 0.25),
        median_cents=percentile(values, 0.5),
        p75_cents=percentile(values, 0.75),
    )


def fee_types(db: Session, ctx: RequestContext, rng: DateRange) -> FeeTypesOut:
    """Share of active quotes with a stated, estimated or not_stated line per category."""
    quotes = _active_quotes(db, ctx, rng)
    ids = [q.id for q in quotes]
    per_category: dict[FeeCategory, set[uuid.UUID]] = defaultdict(set)
    if ids:
        stmt = scoped(select(FeeLine).where(FeeLine.quote_id.in_(ids)), ctx)
        for line in db.scalars(stmt):
            # Synthetic lines (expected-fee rules, all-in coverage) are not on the quote.
            if line.field_id is None or line.amount_status not in _FEE_PRESENT:
                continue
            per_category[line.category].add(line.quote_id)
    n = len(quotes)
    items = [
        FeeShare(
            category=cat,
            label=FEE_CATEGORY_LABELS[cat],
            count=len(per_category[cat]),
            share_pct=_pct(len(per_category[cat]), n),
        )
        for cat in FEE_CATEGORY_ORDER
        if per_category.get(cat)
    ]
    items.sort(key=lambda i: -i.count)  # stable: ties keep display order
    return FeeTypesOut(n_quotes=n, items=items)


def aircraft_mix(db: Session, ctx: RequestContext, rng: DateRange) -> AircraftMixOut:
    quotes = _active_quotes(db, ctx, rng)
    counts = Counter(q.aircraft_category for q in quotes)
    n = len(quotes)
    items = [
        CategoryShare(
            category=cat.value,
            label=AIRCRAFT_CATEGORY_LABELS[cat],
            count=counts[cat],
            share_pct=_pct(counts[cat], n),
        )
        for cat in AircraftCategory
        if counts.get(cat)
    ]
    if counts.get(None):
        items.append(
            CategoryShare(
                category="unknown",
                label="Unknown",
                count=counts[None],
                share_pct=_pct(counts[None], n),
            )
        )
    items.sort(key=lambda i: -i.count)
    return AircraftMixOut(n_quotes=n, items=items)


def funnel(db: Session, ctx: RequestContext, rng: DateRange) -> FunnelOut:
    """Trips created -> with a quote -> with a sent proposal -> booked."""
    trips = list(
        db.scalars(
            scoped(select(Trip).where(Trip.created_at >= rng.start, Trip.created_at < rng.end), ctx)
        )
    )
    created = {t.id for t in trips}
    if not created:
        return FunnelOut(created=0, quoted=0, proposal_sent=0, booked=0)
    ids = list(created)
    with_quote = set(
        db.scalars(scoped(select(Quote.trip_id).where(Quote.trip_id.in_(ids)), ctx, Quote))
    )
    quoted = created & with_quote
    with_sent = set(
        db.scalars(
            scoped(
                select(Proposal.trip_id).where(
                    Proposal.trip_id.in_(ids), Proposal.sent_at.is_not(None)
                ),
                ctx,
                Proposal,
            )
        )
    )
    sent = quoted & with_sent
    booked_ids = {t.id for t in trips if t.booked_quote_id is not None or t.booked_at is not None}
    booked = sent & booked_ids
    return FunnelOut(
        created=len(created), quoted=len(quoted), proposal_sent=len(sent), booked=len(booked)
    )


def compute_metric(
    db: Session, ctx: RequestContext, metric: AnalyticsMetric, rng: DateRange
) -> AnalyticsMetricOut:
    match metric:
        case AnalyticsMetric.QUOTE_VOLUME:
            return quote_volume(db, ctx, rng)
        case AnalyticsMetric.RESPONSE_TIMES:
            return response_times(db, ctx, rng)
        case AnalyticsMetric.TRUE_COST_DISTRIBUTION:
            return true_cost_distribution(db, ctx, rng)
        case AnalyticsMetric.FEE_TYPES:
            return fee_types(db, ctx, rng)
        case AnalyticsMetric.AIRCRAFT_MIX:
            return aircraft_mix(db, ctx, rng)
        case AnalyticsMetric.FUNNEL:
            return funnel(db, ctx, rng)


def overview(db: Session, ctx: RequestContext, rng: DateRange) -> AnalyticsOverviewOut:
    return AnalyticsOverviewOut(
        date_from=rng.date_from,
        date_to=rng.date_to,
        quote_volume=quote_volume(db, ctx, rng),
        response_times=response_times(db, ctx, rng),
        true_cost_distribution=true_cost_distribution(db, ctx, rng),
        fee_types=fee_types(db, ctx, rng),
        aircraft_mix=aircraft_mix(db, ctx, rng),
        funnel=funnel(db, ctx, rng),
    )
