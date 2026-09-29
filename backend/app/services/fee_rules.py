"""Expected-fee rules (spec §4 table). None fires when the category is present
or covered by "all in".

fet             all legs US-US              warning, 7.5 % x FET base
segment_fees    US domestic                 info, pax x segments x $5.30
international   any non-US endpoint         warning, estimate by category
deicing         departure in de-ice zone,   info Oct/Nov/Mar/Apr, warning Dec-Feb
                month Oct-Apr
crew_overnight  legs span a night           warning
positioning     aircraft based elsewhere,   warning
                no positioning line
learned         freq >= 0.6 with n >= 5     info; warning at >= 0.85 with n >= 10

Estimates are USD cents. The FET estimate here is a first reading from the
quote's own amounts; `normalization` recomputes it from the normalized
headline and lines, which is the figure that reaches the totals.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from decimal import Decimal
from typing import Final

from app.models.enums import AircraftCategory, AmountStatus, FeeCategory, FeeUnit, FlagSeverity
from app.services import airports as airport_data
from app.services import fx as fx_mod
from app.services.contracts import (
    ALL_IN_COVERED,
    FET_BASE_EXCLUDED,
    AirportInfo,
    ExpectedFee,
    FxTable,
    LearnedStat,
    QuoteState,
    TripContext,
)
from app.services.money import to_int_half_up

FET_RATE: Final = Decimal("0.075")
SEGMENT_FEE_CENTS: Final = 530
DEICE_WARNING_MONTHS: Final = frozenset({12, 1, 2})
DEICE_INFO_MONTHS: Final = frozenset({10, 11, 3, 4})
LEARNED_INFO_FREQUENCY: Final = 0.6
LEARNED_INFO_MIN_N: Final = 5
LEARNED_WARNING_FREQUENCY: Final = 0.85
LEARNED_WARNING_MIN_N: Final = 10

#: Typical per-event de-icing cost by aircraft category (USD cents).
DEICE_ESTIMATE_CENTS: Final[Mapping[AircraftCategory | None, int]] = {
    AircraftCategory.TURBOPROP: 80_000,
    AircraftCategory.VERY_LIGHT: 100_000,
    AircraftCategory.LIGHT: 150_000,
    AircraftCategory.MIDSIZE: 250_000,
    AircraftCategory.SUPER_MIDSIZE: 350_000,
    AircraftCategory.HEAVY: 600_000,
    AircraftCategory.ULTRA_LONG_RANGE: 900_000,
    AircraftCategory.AIRLINER: 1_500_000,
    None: 350_000,
}

#: Customs, handling and overflight for an international sector (USD cents).
INTERNATIONAL_ESTIMATE_CENTS: Final[Mapping[AircraftCategory | None, int]] = {
    AircraftCategory.TURBOPROP: 80_000,
    AircraftCategory.VERY_LIGHT: 100_000,
    AircraftCategory.LIGHT: 120_000,
    AircraftCategory.MIDSIZE: 150_000,
    AircraftCategory.SUPER_MIDSIZE: 200_000,
    AircraftCategory.HEAVY: 300_000,
    AircraftCategory.ULTRA_LONG_RANGE: 400_000,
    AircraftCategory.AIRLINER: 600_000,
    None: 200_000,
}

#: Crew hotel and per diem for one night, whole crew (USD cents).
CREW_OVERNIGHT_PER_NIGHT_CENTS: Final[Mapping[AircraftCategory | None, int]] = {
    AircraftCategory.TURBOPROP: 50_000,
    AircraftCategory.VERY_LIGHT: 50_000,
    AircraftCategory.LIGHT: 60_000,
    AircraftCategory.MIDSIZE: 70_000,
    AircraftCategory.SUPER_MIDSIZE: 80_000,
    AircraftCategory.HEAVY: 120_000,
    AircraftCategory.ULTRA_LONG_RANGE: 150_000,
    AircraftCategory.AIRLINER: 250_000,
    None: 80_000,
}

#: (USD cents per hour, cruise knots) used to price a ferry from the aircraft's base.
POSITIONING_RATE: Final[Mapping[AircraftCategory | None, tuple[int, int]]] = {
    AircraftCategory.TURBOPROP: (250_000, 280),
    AircraftCategory.VERY_LIGHT: (350_000, 380),
    AircraftCategory.LIGHT: (450_000, 420),
    AircraftCategory.MIDSIZE: (600_000, 440),
    AircraftCategory.SUPER_MIDSIZE: (800_000, 460),
    AircraftCategory.HEAVY: (1_100_000, 470),
    AircraftCategory.ULTRA_LONG_RANGE: (1_400_000, 480),
    AircraftCategory.AIRLINER: (2_000_000, 450),
    None: (800_000, 450),
}
POSITIONING_TAXI_HOURS: Final = 0.3

_PRICED: Final = frozenset({AmountStatus.STATED, AmountStatus.ESTIMATED})


def present_categories(state: QuoteState) -> frozenset[FeeCategory]:
    """Categories the quote mentions at all (any status, not_applicable included)."""
    return frozenset(f.category for f in state.fees)


def is_covered(state: QuoteState, category: FeeCategory) -> bool:
    """Present in the quote, or covered by an "all in" headline."""
    return category in present_categories(state) or (state.all_in and category in ALL_IN_COVERED)


def _airport(trip: TripContext, code: str | None) -> AirportInfo | None:
    if not code:
        return None
    return trip.airports.get(code.upper()) or airport_data.get_airport(code)


def _usd(amount_minor: int, currency: str, fx: FxTable | None) -> int | None:
    if currency.upper() == "USD":
        return amount_minor
    try:
        return fx_mod.to_usd_cents(amount_minor, currency, fx or fx_mod.load_fx_table())
    except fx_mod.UnknownCurrency:
        return None


def headline_minor(state: QuoteState) -> tuple[int | None, bool]:
    """(headline in minor units of the quote currency, estimated?)."""
    if state.headline_minor is not None:
        return state.headline_minor, False
    rate = state.hourly_rate_minor
    if rate is None:
        return None, False
    hours = max(
        (h for h in (state.billable_hours, state.daily_minimum_hours) if h is not None),
        default=None,
    )
    if hours is not None:
        return to_int_half_up(Decimal(rate) * hours), False
    if state.flight_time_minutes:
        tenths = math.ceil(state.flight_time_minutes / 6)
        return to_int_half_up(Decimal(rate) * Decimal(tenths) / 10), True
    return None, False


def fet_estimate_cents(state: QuoteState, fx: FxTable | None = None) -> int | None:
    """7.5 % of headline plus priced fees outside `FET_BASE_EXCLUDED` (USD cents)."""
    head, _ = headline_minor(state)
    if head is None:
        return None
    base = _usd(head, state.currency, fx)
    if base is None:
        return None
    for fee in state.fees:
        if fee.category in FET_BASE_EXCLUDED or fee.status not in _PRICED:
            continue
        if fee.unit is FeeUnit.PERCENT or fee.amount_minor is None:
            continue
        cents = _usd(fee.amount_minor, fee.currency or state.currency, fx)
        if cents is not None:
            base += cents
    return to_int_half_up(Decimal(base) * FET_RATE)


def nights(trip: TripContext) -> int:
    days = sorted({leg.depart_local.date() for leg in trip.legs})
    return (days[-1] - days[0]).days if days else 0


def _has_foreign_endpoint(trip: TripContext) -> bool:
    for leg in trip.legs:
        for code in (leg.origin_icao, leg.destination_icao):
            info = _airport(trip, code)
            if info is not None and not info.is_us:
                return True
    return False


def _deicing(state: QuoteState, trip: TripContext) -> ExpectedFee | None:
    severity: FlagSeverity | None = None
    where: list[str] = []
    for leg in trip.legs:
        info = _airport(trip, leg.origin_icao)
        month = leg.depart_local.month
        if info is None or not info.deice_zone:
            continue
        if month in DEICE_WARNING_MONTHS:
            severity = FlagSeverity.WARNING
        elif month in DEICE_INFO_MONTHS and severity is None:
            severity = FlagSeverity.INFO
        else:
            continue
        where.append(info.icao)
    if severity is None:
        return None
    season = "winter" if severity is FlagSeverity.WARNING else "shoulder-season"
    return ExpectedFee(
        category=FeeCategory.DEICING,
        severity=severity,
        reason=f"De-icing may be needed departing {', '.join(dict.fromkeys(where))} "
        f"({season}); billed at cost if required",
        estimate_cents=DEICE_ESTIMATE_CENTS[state.aircraft_category],
        rule_id="deicing",
    )


def _positioning(state: QuoteState, trip: TripContext) -> ExpectedFee | None:
    base = _airport(trip, state.base_airport_icao)
    origin = _airport(trip, trip.first_leg.origin_icao)
    if base is None or not state.base_airport_icao:
        return None
    if state.base_airport_icao.upper() == trip.first_leg.origin_icao.upper():
        return None
    if origin is not None and base.icao == origin.icao:
        return None
    estimate: int | None = None
    if origin is not None:
        rate, speed = POSITIONING_RATE[state.aircraft_category]
        hours = airport_data.distance_nm(base, origin) / speed + POSITIONING_TAXI_HOURS
        estimate = to_int_half_up(Decimal(rate) * Decimal(str(round(hours, 2))))
    return ExpectedFee(
        category=FeeCategory.POSITIONING,
        severity=FlagSeverity.WARNING,
        reason=f"Aircraft is based at {base.icao}, not {trip.first_leg.origin_icao}; "
        "no positioning charge is quoted",
        estimate_cents=estimate,
        rule_id="positioning",
    )


def _learned(
    state: QuoteState,
    trip: TripContext,
    learned: Mapping[FeeCategory, LearnedStat],
    taken: set[FeeCategory],
) -> list[ExpectedFee]:
    out: list[ExpectedFee] = []
    airport = trip.first_leg.origin_icao.upper()
    for category in FeeCategory:
        stat = learned.get(category)
        if stat is None or category in taken or is_covered(state, category):
            continue
        if stat.frequency >= LEARNED_WARNING_FREQUENCY and stat.n >= LEARNED_WARNING_MIN_N:
            severity = FlagSeverity.WARNING
        elif stat.frequency >= LEARNED_INFO_FREQUENCY and stat.n >= LEARNED_INFO_MIN_N:
            severity = FlagSeverity.INFO
        else:
            continue
        out.append(
            ExpectedFee(
                category=category,
                severity=severity,
                reason=f"{round(stat.frequency * 100)}% of {stat.n} quotes at {airport} "
                f"carried {category.value.replace('_', ' ')}",
                estimate_cents=stat.median_cents,
                rule_id=f"learned:{airport}",
                source="learned",
                stat=stat,
            )
        )
    return out


def rule_estimate(
    category: FeeCategory, state: QuoteState, trip: TripContext
) -> tuple[int | None, str | None]:
    """(estimate cents, basis) for a category a rule knows how to price.

    Used for a quote's own not_stated line ("fuel may be extra"), which the
    rules above skip because the category is present.
    """
    cat = state.aircraft_category
    if category is FeeCategory.FET:
        return fet_estimate_cents(state), "rule:fet"
    if category is FeeCategory.SEGMENT_FEES:
        return trip.pax * len(trip.legs) * SEGMENT_FEE_CENTS, "rule:segment_fees"
    if category is FeeCategory.INTERNATIONAL:
        return INTERNATIONAL_ESTIMATE_CENTS[cat], "rule:international"
    if category is FeeCategory.DEICING:
        return DEICE_ESTIMATE_CENTS[cat], "rule:deicing"
    if category is FeeCategory.CREW_OVERNIGHT:
        n = max(1, nights(trip))
        return n * CREW_OVERNIGHT_PER_NIGHT_CENTS[cat], "rule:crew_overnight"
    if category is FeeCategory.POSITIONING:
        exp = _positioning(state, trip)
        if exp is not None and exp.estimate_cents is not None:
            return exp.estimate_cents, "rule:positioning"
    return None, None


def expected_fees(
    state: QuoteState,
    trip: TripContext,
    *,
    learned: Mapping[FeeCategory, LearnedStat] | None = None,
) -> list[ExpectedFee]:
    out: list[ExpectedFee] = []

    def add(fee: ExpectedFee | None) -> None:
        if fee is not None and not is_covered(state, fee.category):
            out.append(fee)

    if trip.is_us_domestic:
        add(
            ExpectedFee(
                category=FeeCategory.FET,
                severity=FlagSeverity.WARNING,
                reason="US domestic trip: 7.5% federal excise tax applies",
                estimate_cents=fet_estimate_cents(state),
                rule_id="fet",
            )
        )
        segments = len(trip.legs)
        add(
            ExpectedFee(
                category=FeeCategory.SEGMENT_FEES,
                severity=FlagSeverity.INFO,
                reason=f"US domestic segment fees: {trip.pax} pax x {segments} segment(s)",
                estimate_cents=trip.pax * segments * SEGMENT_FEE_CENTS,
                rule_id="segment_fees",
            )
        )
    if _has_foreign_endpoint(trip):
        add(
            ExpectedFee(
                category=FeeCategory.INTERNATIONAL,
                severity=FlagSeverity.WARNING,
                reason="International sector: customs, handling and overflight fees apply",
                estimate_cents=INTERNATIONAL_ESTIMATE_CENTS[state.aircraft_category],
                rule_id="international",
            )
        )
    add(_deicing(state, trip))
    if trip.is_multi_day:
        n = nights(trip)
        add(
            ExpectedFee(
                category=FeeCategory.CREW_OVERNIGHT,
                severity=FlagSeverity.WARNING,
                reason=f"Itinerary spans {n} night(s); crew overnight costs apply",
                estimate_cents=n * CREW_OVERNIGHT_PER_NIGHT_CENTS[state.aircraft_category],
                rule_id="crew_overnight",
            )
        )
    add(_positioning(state, trip))
    if learned:
        out.extend(_learned(state, trip, learned, {f.category for f in out}))
    return out
