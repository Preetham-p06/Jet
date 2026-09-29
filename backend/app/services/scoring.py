"""Fit score and recommendation, algorithm "fit-1" (spec §5). Pure and deterministic.

fit = round_half_up(sum(w_k * s_k) / sum(w_k)), s_k in [0, 100]. A missing
signal is imputed as the cohort median (neutral); a signal missing for every
quote is dropped and the weights renormalize. Recommended: the highest-fit
eligible quote (active, fully priced, no open blocking flags, enough seats,
not unavailable). Ties: lower known total, higher quote confidence, earlier
created_at, then id.
"""

from __future__ import annotations

import statistics
from collections.abc import Callable, Mapping, Sequence
from decimal import Decimal
from types import MappingProxyType
from typing import Any, Final

from app.models.enums import AmountStatus, Availability, FeeCategory, FieldStatus, QuoteStatus
from app.services.contracts import (
    ALGORITHM_VERSION,
    DEFAULT_WEIGHTS,
    Check,
    Eligibility,
    EligibilityReason,
    FieldState,
    IneligibilityCode,
    NormalizedFeeLine,
    QuoteState,
    RankedQuote,
    RecommendationResult,
    ScoreBreakdown,
    ScoreInput,
    Signal,
    SignalScore,
    TripContext,
    TrueCost,
)
from app.services.money import format_usd, round_half_up

AVAILABILITY_SCORES: Final[Mapping[Availability, float]] = {
    Availability.CONFIRMED: 100,
    Availability.AVAILABLE: 100,
    Availability.SUBJECT_TO: 70,
    Availability.TENTATIVE: 70,
    Availability.ON_REQUEST: 60,
    Availability.UNAVAILABLE: 0,
}
PRICE_SLOPE: Final = 200.0
SPEED_SLOPE: Final = 200.0
FEES_PER_BLOCKING_FLAG: Final = 35.0
CATEGORY_MISMATCH_PENALTY: Final = 20.0
CREW_OVERNIGHT_PENALTY: Final = 40.0
EXTRA_CREW_PENALTY: Final = 20.0
POSITIONING_FREE_PCT: Final = 2.0
POSITIONING_SLOPE: Final = 10.0
TECH_STOP_PENALTY: Final = 30.0
SCHEDULE_WEIGHT: Final = 0.6
SPEED_WEIGHT: Final = 0.4

_CHARGED: Final = frozenset({AmountStatus.STATED, AmountStatus.ESTIMATED, AmountStatus.NOT_STATED})
_CATERING_PROVIDED: Final = frozenset(
    {
        AmountStatus.STATED,
        AmountStatus.ESTIMATED,
        AmountStatus.NOT_STATED,
        AmountStatus.INCLUDED,
        AmountStatus.WAIVED,
    }
)


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


# --------------------------------------------------------------------------- confidence


def _effective(f: FieldState, threshold: int) -> int:
    if f.status in (FieldStatus.VERIFIED, FieldStatus.EDITED):
        return 100
    if f.status is FieldStatus.ACCEPTED:
        return max(f.confidence, threshold)
    return f.confidence


def _money_weight(value: Any) -> int:
    """Absolute money amount of a stored field value (minor units), 0 when none."""
    if isinstance(value, Mapping):
        if isinstance(value.get("amount_minor"), int):
            return abs(int(value["amount_minor"]))
        amount = value.get("amount")
        if isinstance(amount, Mapping) and isinstance(amount.get("amount_minor"), int):
            return abs(int(amount["amount_minor"]))
    return 0


def quote_confidence(state: QuoteState, review_threshold: int) -> tuple[int | None, float | None]:
    """(min effective confidence over material fields, money-weighted mean).

    Verified or edited counts as 100, accepted as max(confidence, threshold).
    The mean weights each field by its money amount; when no material field
    carries money it is the plain mean.
    """
    material = [f for f in state.fields if f.is_material]
    if not material:
        return None, None
    effective = [(_effective(f, review_threshold), _money_weight(f.value)) for f in material]
    low = min(e for e, _ in effective)
    total_weight = sum(w for _, w in effective)
    if total_weight:
        mean = sum(e * w for e, w in effective) / total_weight
    else:
        mean = sum(e for e, _ in effective) / len(effective)
    return low, round(mean, 2)


# --------------------------------------------------------------------------- inputs


def _lines(true_cost: TrueCost, category: FeeCategory) -> list[NormalizedFeeLine]:
    return [ln for ln in true_cost.lines if ln.category is category]


def _catering(true_cost: TrueCost) -> bool | None:
    lines = _lines(true_cost, FeeCategory.CATERING)
    if not lines:
        return None
    return any(ln.amount_status in _CATERING_PROVIDED for ln in lines)


def _positioning_cents(true_cost: TrueCost) -> int | None:
    """Positioning in USD cents: 0 when included/waived/n.a., None when unknown."""
    lines = [ln for ln in _lines(true_cost, FeeCategory.POSITIONING) if not ln.is_synthetic]
    if not lines:
        synthetic = _lines(true_cost, FeeCategory.POSITIONING)
        if synthetic and synthetic[0].estimate_cents is not None:
            return synthetic[0].estimate_cents
        return None
    total = 0
    for ln in lines:
        if ln.amount_status in _CHARGED:
            amount = ln.amount_cents if ln.amount_cents is not None else ln.estimate_cents
            if amount is None:
                return None
            total += amount
    return total


def build_score_input(
    state: QuoteState,
    true_cost: TrueCost,
    *,
    open_blocking_flags: int,
    quote_confidence: int | None,
) -> ScoreInput:
    def charged(category: FeeCategory) -> bool:
        return any(
            ln.amount_status in _CHARGED and not ln.is_synthetic
            for ln in _lines(true_cost, category)
        )

    return ScoreInput(
        quote_id=state.quote_id,
        operator_name=state.operator_name,
        status=state.status,
        created_at=state.created_at,
        headline_cents=true_cost.headline_cents,
        known_total_cents=true_cost.known_total_cents,
        upper_total_cents=true_cost.upper_total_cents,
        is_fully_priced=true_cost.is_fully_priced,
        open_blocking_flags=open_blocking_flags,
        quote_confidence=quote_confidence,
        seats=state.seats,
        aircraft_category=state.aircraft_category,
        wifi=state.wifi,
        catering_included=_catering(true_cost),
        departure_local=state.departure_local,
        flight_time_minutes=state.flight_time_minutes,
        availability=state.availability,
        crew_overnight_charged=charged(FeeCategory.CREW_OVERNIGHT),
        extra_crew_charged=charged(FeeCategory.CREW),
        positioning_cents=_positioning_cents(true_cost),
    )


# --------------------------------------------------------------------------- eligibility


def recommendation_eligibility(inp: ScoreInput, trip: TripContext) -> Eligibility:
    reasons: list[EligibilityReason] = []
    if inp.status is not QuoteStatus.ACTIVE:
        reasons.append(
            EligibilityReason(IneligibilityCode.NOT_ACTIVE, f"Quote is {inp.status.value}")
        )
    if inp.headline_cents is None:
        reasons.append(EligibilityReason(IneligibilityCode.NO_HEADLINE, "No headline price"))
    elif not inp.is_fully_priced:
        upper = (
            f"; up to {format_usd(inp.upper_total_cents)}"
            if inp.upper_total_cents is not None
            else ""
        )
        reasons.append(
            EligibilityReason(IneligibilityCode.NOT_FULLY_PRICED, f"Not fully priced{upper}")
        )
    if inp.open_blocking_flags > 0:
        n = inp.open_blocking_flags
        reasons.append(
            EligibilityReason(
                IneligibilityCode.BLOCKING_FLAGS,
                f"{n} open blocking flag{'s' if n != 1 else ''}",
            )
        )
    if inp.seats is None:
        reasons.append(
            EligibilityReason(IneligibilityCode.INSUFFICIENT_CAPACITY, "Seat count unknown")
        )
    elif inp.seats < trip.pax:
        reasons.append(
            EligibilityReason(
                IneligibilityCode.INSUFFICIENT_CAPACITY,
                f"{inp.seats} seats for {trip.pax} passengers",
            )
        )
    if inp.availability is Availability.UNAVAILABLE:
        reasons.append(EligibilityReason(IneligibilityCode.UNAVAILABLE, "Aircraft unavailable"))
    return Eligibility.blocked(*reasons)


# --------------------------------------------------------------------------- signals


def _price(inp: ScoreInput) -> int | None:
    return inp.known_total_cents if inp.is_fully_priced else inp.upper_total_cents


def _deviation_minutes(inp: ScoreInput, trip: TripContext) -> float | None:
    if inp.departure_local is None:
        return None
    return abs((inp.departure_local - trip.first_leg.depart_local).total_seconds()) / 60


def _schedule(inp: ScoreInput, trip: TripContext) -> float | None:
    dev = _deviation_minutes(inp, trip)
    return None if dev is None else _clamp(100 - dev / 2)


class _Cohort:
    def __init__(self, inputs: Sequence[ScoreInput]) -> None:
        prices = [p for i in inputs if (p := _price(i)) is not None and p > 0]
        self.best_price = min(prices) if prices else None
        times = [i.flight_time_minutes for i in inputs if i.flight_time_minutes]
        self.min_flight_time = min(times) if times else None


def _sig_pricing(inp: ScoreInput, trip: TripContext, c: _Cohort) -> tuple[float | None, str | None]:
    p = _price(inp)
    if p is None or c.best_price is None:
        return None, None
    basis = "known total" if inp.is_fully_priced else "upper total"
    return _clamp(100 - PRICE_SLOPE * (p - c.best_price) / c.best_price), (
        f"{basis} {format_usd(p)} vs best {format_usd(c.best_price)}"
    )


def _sig_fees(inp: ScoreInput, trip: TripContext, c: _Cohort) -> tuple[float | None, str | None]:
    n = inp.open_blocking_flags
    return _clamp(100 - FEES_PER_BLOCKING_FLAG * n), f"{n} open blocking flag(s)"


def _sig_aircraft(
    inp: ScoreInput, trip: TripContext, c: _Cohort
) -> tuple[float | None, str | None]:
    if inp.seats is None:
        return None, None
    spare = inp.seats - trip.pax
    if spare < 0:
        return 0.0, f"{inp.seats} seats for {trip.pax} pax"
    if spare == 0:
        score = 85.0
    elif spare <= 2:
        score = 100.0
    elif spare <= 4:
        score = 90.0
    elif spare <= 6:
        score = 80.0
    else:
        score = 70.0
    preferred = trip.preferences.preferred_categories
    if preferred and inp.aircraft_category is not None and inp.aircraft_category not in preferred:
        score -= CATEGORY_MISMATCH_PENALTY
    return _clamp(score), f"{inp.seats} seats, {spare} spare"


def _sig_timing(inp: ScoreInput, trip: TripContext, c: _Cohort) -> tuple[float | None, str | None]:
    schedule = _schedule(inp, trip)
    speed: float | None = None
    if inp.flight_time_minutes and c.min_flight_time:
        ft, best = inp.flight_time_minutes, c.min_flight_time
        speed = _clamp(100 - SPEED_SLOPE * (ft - best) / best)
    if schedule is not None and speed is not None:
        return SCHEDULE_WEIGHT * schedule + SPEED_WEIGHT * speed, (
            f"schedule {schedule:.1f}, speed {speed:.1f}"
        )
    if schedule is not None:
        return schedule, f"schedule {schedule:.1f}"
    if speed is not None:
        return speed, f"speed {speed:.1f}"
    return None, None


def _sig_preferences(
    inp: ScoreInput, trip: TripContext, c: _Cohort
) -> tuple[float | None, str | None]:
    prefs = trip.preferences
    matches: list[tuple[str, bool]] = []
    if prefs.wifi_required and inp.wifi is not None:
        matches.append(("wifi", inp.wifi))
    if prefs.catering_required and inp.catering_included is not None:
        matches.append(("catering", inp.catering_included))
    if prefs.preferred_categories and inp.aircraft_category is not None:
        matches.append(("category", inp.aircraft_category in prefs.preferred_categories))
    price = _price(inp)
    if prefs.max_budget_cents is not None and price is not None:
        matches.append(("budget", price <= prefs.max_budget_cents))
    if not matches:
        return None, None
    score = 100 * sum(1 for _, ok in matches if ok) / len(matches)
    return score, ", ".join(f"{k} {'yes' if ok else 'no'}" for k, ok in matches)


def _sig_availability(
    inp: ScoreInput, trip: TripContext, c: _Cohort
) -> tuple[float | None, str | None]:
    if inp.availability is None:
        return None, None
    return AVAILABILITY_SCORES[inp.availability], inp.availability.value


def _sig_crew(inp: ScoreInput, trip: TripContext, c: _Cohort) -> tuple[float | None, str | None]:
    overnight = inp.crew_overnight_charged and not trip.is_multi_day
    score = 100 - CREW_OVERNIGHT_PENALTY * overnight - EXTRA_CREW_PENALTY * inp.extra_crew_charged
    notes = [
        n
        for n, on in (
            ("crew overnight on a same-day trip", overnight),
            ("extra crew charge", inp.extra_crew_charged),
        )
        if on
    ]
    return _clamp(score), ", ".join(notes) or None


def _sig_routing(inp: ScoreInput, trip: TripContext, c: _Cohort) -> tuple[float | None, str | None]:
    total = inp.known_total_cents
    if inp.positioning_cents is None or not total:
        return None, None
    pct = 100 * inp.positioning_cents / total
    score = _clamp(100 - POSITIONING_SLOPE * max(0.0, pct - POSITIONING_FREE_PCT))
    score -= TECH_STOP_PENALTY * inp.tech_stop
    return _clamp(score), f"positioning {pct:.1f}% of total"


_SignalFn = Callable[[ScoreInput, TripContext, _Cohort], tuple[float | None, str | None]]

_SIGNALS: Final[Mapping[Signal, _SignalFn]] = {
    Signal.PRICING: _sig_pricing,
    Signal.FEES: _sig_fees,
    Signal.AIRCRAFT: _sig_aircraft,
    Signal.TIMING: _sig_timing,
    Signal.PREFERENCES: _sig_preferences,
    Signal.AVAILABILITY: _sig_availability,
    Signal.CREW: _sig_crew,
    Signal.ROUTING: _sig_routing,
}


def _resolve_weights(
    trip: TripContext, weights: Mapping[Signal, float] | None
) -> Mapping[Signal, float]:
    if weights is not None:
        chosen = {Signal(k): float(v) for k, v in weights.items()}
    elif trip.scoring_weights:
        chosen = {Signal(k): float(v) for k, v in trip.scoring_weights.items()}
    else:
        chosen = dict(DEFAULT_WEIGHTS)
    return MappingProxyType({s: chosen.get(s, DEFAULT_WEIGHTS[s]) for s in Signal})


def _fit(signals: Sequence[SignalScore]) -> int | None:
    used = [s for s in signals if not s.dropped and s.value is not None and s.weight > 0]
    total_weight = sum(s.weight for s in used)
    if not used or total_weight <= 0:
        return None
    value = sum(Decimal(str(s.weight)) * Decimal(str(s.value)) for s in used if s.value is not None)
    return int(round_half_up(value / Decimal(str(total_weight))))


def _checks(
    rec: ScoreInput,
    breakdown: ScoreBreakdown,
    eligible: Sequence[tuple[ScoreInput, ScoreBreakdown]],
) -> tuple[Check, ...]:
    schedules = [b.schedule_subscore for _, b in eligible if b.schedule_subscore is not None]
    best_schedule = (
        breakdown.schedule_subscore is not None
        and bool(schedules)
        and breakdown.schedule_subscore >= max(schedules) - 1e-9
    )
    totals = [i.known_total_cents for i, _ in eligible if i.known_total_cents is not None]
    lowest = rec.known_total_cents is not None and rec.known_total_cents <= min(
        totals, default=rec.known_total_cents
    )
    aircraft = breakdown.signal(Signal.AIRCRAFT)
    seats_label = f"{rec.seats}-seat configuration" if rec.seats else "Seat configuration"
    return (
        Check("schedule", "Best schedule fit", best_schedule),
        Check("lowest_cost", "Lowest fully-priced total cost", lowest),
        Check("wifi", "Wi-Fi on board", rec.wifi is True),
        Check("seats", seats_label, aircraft is not None and aircraft.raw == 100),
        Check("no_crew_overnight", "No overnight crew requirement", not rec.crew_overnight_charged),
    )


def score_trip(
    inputs: Sequence[ScoreInput],
    trip: TripContext,
    *,
    weights: Mapping[Signal, float] | None = None,
) -> RecommendationResult:
    resolved = _resolve_weights(trip, weights)
    if not inputs:
        return RecommendationResult(
            algorithm_version=ALGORITHM_VERSION,
            weights=resolved,
            recommended_quote_id=None,
            ranking=(),
        )
    active = [i for i in inputs if i.status is QuoteStatus.ACTIVE] or list(inputs)
    cohort = _Cohort(active)
    active_ids = {i.quote_id for i in active}

    raw: dict[Signal, list[tuple[float | None, str | None]]] = {
        sig: [fn(i, trip, cohort) for i in inputs] for sig, fn in _SIGNALS.items()
    }
    medians: dict[Signal, float | None] = {}
    for sig, values in raw.items():
        present = [
            v
            for (v, _), i in zip(values, inputs, strict=True)
            if v is not None and i.quote_id in active_ids
        ] or [v for v, _ in values if v is not None]
        medians[sig] = statistics.median(present) if present else None

    breakdowns: list[ScoreBreakdown] = []
    for idx, inp in enumerate(inputs):
        signals: list[SignalScore] = []
        for sig in Signal:
            value, detail = raw[sig][idx]
            median = medians[sig]
            signals.append(
                SignalScore(
                    signal=sig,
                    weight=resolved[sig],
                    raw=None if value is None else round(value, 4),
                    value=round(value, 4)
                    if value is not None
                    else (None if median is None else round(median, 4)),
                    imputed=value is None and median is not None,
                    dropped=median is None,
                    detail=detail,
                )
            )
        breakdowns.append(
            ScoreBreakdown(
                fit=_fit(signals),
                signals=tuple(signals),
                schedule_subscore=_schedule(inp, trip),
            )
        )

    eligibility = [recommendation_eligibility(i, trip) for i in inputs]

    def key(idx: int) -> tuple[Any, ...]:
        inp, b, e = inputs[idx], breakdowns[idx], eligibility[idx]
        return (
            0 if e.eligible else 1,
            -(b.fit if b.fit is not None else -1),
            inp.known_total_cents if inp.known_total_cents is not None else float("inf"),
            -(inp.quote_confidence if inp.quote_confidence is not None else -1),
            inp.created_at,
            str(inp.quote_id),
        )

    order = sorted(range(len(inputs)), key=key)
    ranking = tuple(
        RankedQuote(
            quote_id=inputs[idx].quote_id,
            rank=pos + 1,
            breakdown=breakdowns[idx],
            eligibility=eligibility[idx],
        )
        for pos, idx in enumerate(order)
    )
    best = order[0]
    recommended = inputs[best] if eligibility[best].eligible else None
    checks: tuple[Check, ...] = ()
    if recommended is not None:
        eligible = [
            (inputs[i], breakdowns[i]) for i in range(len(inputs)) if eligibility[i].eligible
        ]
        checks = _checks(recommended, breakdowns[best], eligible)
    return RecommendationResult(
        algorithm_version=ALGORITHM_VERSION,
        weights=resolved,
        recommended_quote_id=recommended.quote_id if recommended else None,
        ranking=ranking,
        checks=checks,
    )
