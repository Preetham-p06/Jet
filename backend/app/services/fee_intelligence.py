"""Learned fee frequencies, scoped to one workspace (spec §4).

`observe_quote` deletes and re-inserts one `fee_observations` row per
(airport, role, canonical category), with `present` true or false.
Outliers: amount > p75 + 3 x IQR with n >= 8 -> info `fee_outlier`.

Only `observe_quote` and `load_learned` touch the database; `learned_stats`
and `is_outlier` are pure.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from typing import Final

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.enums import AirportRole, AmountStatus, FeeCategory, ObservationSource
from app.models.intelligence import FeeObservation
from app.models.quote import Quote
from app.services.contracts import (
    REVIEWED_STATUSES,
    FeeObservationPoint,
    LearnedStat,
    NormalizedFeeLine,
    TripContext,
    TrueCost,
)
from app.services.money import to_int_half_up

OUTLIER_MIN_N: Final = 8
OUTLIER_IQR_FACTOR: Final = 3

#: Statuses that mean the operator's quote carries the fee.
_PRESENT: Final = frozenset(
    {
        AmountStatus.STATED,
        AmountStatus.ESTIMATED,
        AmountStatus.INCLUDED,
        AmountStatus.WAIVED,
        AmountStatus.NOT_STATED,
    }
)


def _quantile(sorted_values: Sequence[int], q: Decimal) -> int:
    """Linear interpolation between closest ranks (numpy's default), half-up to cents."""
    if len(sorted_values) == 1:
        return sorted_values[0]
    pos = q * (len(sorted_values) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = pos - lo
    value = Decimal(sorted_values[lo]) + (Decimal(sorted_values[hi] - sorted_values[lo]) * frac)
    return to_int_half_up(value)


def learned_stats(rows: Sequence[FeeObservationPoint]) -> dict[FeeCategory, LearnedStat]:
    """Pure: frequency over all rows, amount quartiles over present rows with amounts."""
    by_cat: dict[FeeCategory, list[FeeObservationPoint]] = {}
    for row in rows:
        by_cat.setdefault(row.category, []).append(row)
    out: dict[FeeCategory, LearnedStat] = {}
    for cat, points in by_cat.items():
        n = len(points)
        present = [p for p in points if p.present]
        amounts = sorted(p.amount_cents for p in present if p.amount_cents is not None)
        out[cat] = LearnedStat(
            n=n,
            frequency=len(present) / n,
            median_cents=_quantile(amounts, Decimal("0.5")) if amounts else None,
            p25_cents=_quantile(amounts, Decimal("0.25")) if amounts else None,
            p75_cents=_quantile(amounts, Decimal("0.75")) if amounts else None,
            n_amounts=len(amounts),
        )
    return out


def is_outlier(amount_cents: int, stat: LearnedStat) -> bool:
    iqr = stat.iqr_cents
    if stat.n_amounts < OUTLIER_MIN_N or iqr is None or stat.p75_cents is None:
        return False
    return amount_cents > stat.p75_cents + OUTLIER_IQR_FACTOR * iqr


def _observation(
    lines: Sequence[NormalizedFeeLine],
) -> tuple[bool, AmountStatus | None, int | None, ObservationSource]:
    """(present, status, amount, source) of one category, from the operator's own lines."""
    own = [ln for ln in lines if not ln.is_synthetic and ln.amount_status in _PRESENT]
    if not own:
        return False, None, None, ObservationSource.EXTRACTED
    amounts = [ln.amount_cents if ln.amount_cents is not None else ln.estimate_cents for ln in own]
    known = [a for a in amounts if a is not None]
    reviewed = any(ln.review_status in REVIEWED_STATUSES for ln in own)
    return (
        True,
        own[0].amount_status,
        sum(known) if known else None,
        ObservationSource.VERIFIED if reviewed else ObservationSource.EXTRACTED,
    )


def observe_quote(
    db: Session, quote: Quote, trip: TripContext, true_cost: TrueCost, *, now: datetime
) -> int:
    """Rewrite this quote's observations; returns the number of rows written."""
    db.execute(
        delete(FeeObservation).where(
            FeeObservation.workspace_id == quote.workspace_id,
            FeeObservation.quote_id == quote.id,
        )
    )
    airports: dict[tuple[str, AirportRole], None] = {}
    for leg in trip.legs:
        airports[(leg.origin_icao.upper(), AirportRole.DEPARTURE)] = None
        airports[(leg.destination_icao.upper(), AirportRole.ARRIVAL)] = None
    by_cat: dict[FeeCategory, list[NormalizedFeeLine]] = {c: [] for c in FeeCategory}
    for ln in true_cost.lines:
        by_cat[ln.category].append(ln)
    month = trip.departure_month
    written = 0
    for icao, role in airports:
        for cat in FeeCategory:
            present, status, amount, source = _observation(by_cat[cat])
            db.add(
                FeeObservation(
                    workspace_id=quote.workspace_id,
                    quote_id=quote.id,
                    operator_id=quote.operator_id,
                    airport_icao=icao,
                    airport_role=role,
                    month=month,
                    aircraft_category=quote.aircraft_category,
                    fee_category=cat,
                    present=present,
                    amount_status=status,
                    amount_cents=amount,
                    source=source,
                    observed_at=now,
                )
            )
            written += 1
    db.flush()
    return written


def _months(month: int, window: int) -> set[int]:
    return {((month - 1 + d) % 12) + 1 for d in range(-window, window + 1)}


def load_learned(
    db: Session,
    workspace_id: uuid.UUID,
    airport_icao: str,
    month: int,
    *,
    exclude_quote_id: uuid.UUID | None,
    month_window: int = 0,
) -> dict[FeeCategory, LearnedStat]:
    """Stats for one airport; `month_window=1` widens to month +/- 1 (de-icing).

    A quote that touches the airport twice (departure and arrival) counts once.
    """
    stmt = select(
        FeeObservation.quote_id,
        FeeObservation.fee_category,
        FeeObservation.present,
        FeeObservation.amount_cents,
    ).where(
        FeeObservation.workspace_id == workspace_id,
        FeeObservation.airport_icao == airport_icao.upper(),
        FeeObservation.month.in_(sorted(_months(month, month_window))),
    )
    if exclude_quote_id is not None:
        stmt = stmt.where(FeeObservation.quote_id != exclude_quote_id)
    merged: dict[tuple[uuid.UUID, FeeCategory], tuple[bool, int | None]] = {}
    for quote_id, cat, present, amount in db.execute(stmt):
        prev = merged.get((quote_id, cat))
        if prev is None:
            merged[(quote_id, cat)] = (bool(present), amount)
        else:
            amounts = [a for a in (prev[1], amount) if a is not None]
            merged[(quote_id, cat)] = (prev[0] or bool(present), max(amounts, default=None))
    points = [
        FeeObservationPoint(category=FeeCategory(cat), present=p, amount_cents=a)
        for (_, cat), (p, a) in merged.items()
    ]
    return learned_stats(points)
