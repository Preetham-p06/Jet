"""Hand-built engine inputs for demo trip JS184 (spec §9), as merge would present them.

KTEB 2026-10-18 09:00 -> KOPF, 7 pax, Wi-Fi required. Four quotes:
Atlas, SkyBridge, Northstar and Summit (PDF + SMS merged).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import MappingProxyType
from typing import Any

from app.models.enums import (
    AircraftCategory,
    AmountStatus,
    Availability,
    FeeCategory,
    FieldGroup,
    FieldStatus,
    PricingBasis,
    QuoteStatus,
    TripType,
)
from app.services import airports
from app.services.contracts import (
    ExpectedFee,
    FeeLineState,
    FieldState,
    FlagSpec,
    LegState,
    QuoteState,
    RecommendationResult,
    ScoreInput,
    TripContext,
    TripPreferencesState,
    TrueCost,
)
from app.services.fee_rules import expected_fees
from app.services.flags import evaluate_flags
from app.services.fx import load_fx_table
from app.services.normalization import normalize_quote
from app.services.scoring import build_score_input, quote_confidence, score_trip

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
T0 = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)
WS = uuid.UUID(int=1)


def uid(name: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"js184/{name}")


def make_trip(**overrides: Any) -> TripContext:
    leg = LegState(
        seq=1,
        origin_icao="KTEB",
        destination_icao="KOPF",
        depart_local=datetime(2026, 10, 18, 9, 0),
        depart_tz="America/New_York",
        depart_utc=datetime(2026, 10, 18, 13, 0, tzinfo=UTC),
    )
    base: dict[str, Any] = dict(
        trip_id=uid("trip"),
        workspace_id=WS,
        reference="JS184",
        trip_type=TripType.ONE_WAY,
        pax=7,
        legs=(leg,),
        preferences=TripPreferencesState(wifi_required=True),
        review_threshold=75,
        airports=MappingProxyType(airports.airports_for(["KTEB", "KOPF", "KHPN", "KBED"])),
    )
    base.update(overrides)
    return TripContext(**base)


def state(
    fees: tuple[FeeLineState, ...] = (), headline: int | None = 1_000_000, **kw: Any
) -> QuoteState:
    """A minimal flat USD quote for rule-level tests."""
    base: dict[str, Any] = dict(
        quote_id=uuid.uuid4(),
        operator_id=uuid.uuid4(),
        operator_name="Op",
        status=QuoteStatus.ACTIVE,
        currency="USD",
        pricing_basis=PricingBasis.FLAT,
        created_at=datetime(2026, 10, 1, tzinfo=UTC),
        headline_minor=headline,
        fees=fees,
    )
    base.update(kw)
    return QuoteState(**base)


def line(
    cat: FeeCategory, status: AmountStatus, amount: int | None = None, **kw: Any
) -> FeeLineState:
    """A quote fee line (with a field id, as merge would give it)."""
    return FeeLineState(
        category=cat,
        label=kw.pop("label", cat.value),
        status=status,
        amount_minor=amount,
        currency=kw.pop("currency", "USD" if amount is not None else None),
        field_id=kw.pop("field_id", uuid.uuid4()),
        **kw,
    )


def usd(amount_minor: int) -> dict[str, Any]:
    return {"amount_minor": amount_minor, "currency": "USD"}


def fee(
    q: str,
    category: FeeCategory,
    label: str,
    status: AmountStatus,
    dollars: int | None = None,
    *,
    confidence: int = 95,
    review: FieldStatus = FieldStatus.EXTRACTED,
    **kw: Any,
) -> tuple[FeeLineState, FieldState]:
    field_id = uid(f"{q}/fee.{category.value}")
    amount = None if dollars is None else dollars * 100
    line = FeeLineState(
        category=category,
        label=label,
        status=status,
        amount_minor=amount,
        currency="USD" if amount is not None else None,
        confidence=confidence,
        review_status=review,
        field_id=field_id,
        **kw,
    )
    value = {
        "category": category.value,
        "label": label,
        "status": status.value,
        "amount": usd(amount) if amount is not None else None,
    }
    return line, FieldState(
        field_id=field_id,
        key=f"fee.{category.value}",
        group=FieldGroup.FEE,
        value=value,
        confidence=confidence,
        status=review,
    )


def scalar(q: str, key: str, value: Any, confidence: int = 92) -> FieldState:
    return FieldState(
        field_id=uid(f"{q}/{key}"),
        key=key,
        group=FieldGroup.SCALAR,
        value=value,
        confidence=confidence,
        status=FieldStatus.EXTRACTED,
    )


def quote(
    q: str,
    *,
    headline: int,
    fees: list[tuple[FeeLineState, FieldState]],
    model: str,
    category: AircraftCategory,
    seats: int,
    wifi: bool,
    flight_time: int,
    departure: datetime,
    availability: Availability,
    received_min: int,
    stated_total: int | None = None,
    all_in: bool = False,
    extra_fields: tuple[FieldState, ...] = (),
    base_airport: str | None = None,
    headline_confidence: int = 95,
) -> QuoteState:
    fields = [
        scalar(q, "headline_price", usd(headline * 100), headline_confidence),
        scalar(q, "aircraft_model", model),
        scalar(q, "aircraft_category", category.value, 95),
        scalar(q, "seats", seats),
        scalar(q, "wifi", wifi),
        scalar(q, "flight_time_minutes", flight_time),
        *(f for _, f in fees),
        *extra_fields,
    ]
    if stated_total is not None:
        fields.append(scalar(q, "stated_total", usd(stated_total * 100), 95))
    received = T0 + timedelta(minutes=received_min)
    return QuoteState(
        quote_id=uid(q),
        operator_id=uid(f"op/{q}"),
        operator_name=q,
        status=QuoteStatus.ACTIVE,
        currency="USD",
        pricing_basis=PricingBasis.FLAT,
        created_at=received,
        headline_minor=headline * 100,
        stated_total_minor=None if stated_total is None else stated_total * 100,
        all_in=all_in,
        fees=tuple(line for line, _ in fees),
        aircraft_model=model,
        aircraft_category=category,
        seats=seats,
        wifi=wifi,
        flight_time_minutes=flight_time,
        departure_local=departure,
        availability=availability,
        base_airport_icao=base_airport,
        fields=tuple(fields),
        first_received_at=received,
        last_received_at=received,
    )


S, INC, EST = AmountStatus.STATED, AmountStatus.INCLUDED, AmountStatus.ESTIMATED
F = FeeCategory


def atlas() -> QuoteState:
    q = "Atlas"
    return quote(
        q,
        headline=41_800,
        fees=[
            fee(q, F.POSITIONING, "Positioning (ferry KHPN-KTEB)", S, 1_200),
            fee(q, F.RAMP_HANDLING, "Ramp / handling fee (KOPF)", S, 420),
            fee(q, F.FUEL_SURCHARGE, "Fuel surcharge", S, 1_400),
            fee(q, F.FET, "Federal excise tax (7.5%)", INC, percent=Decimal("7.5")),
            fee(q, F.SEGMENT_FEES, "Segment fees", INC),
            fee(q, F.CATERING, "Catering", INC, confidence=95),
        ],
        model="Cessna Citation Latitude",
        category=AircraftCategory.MIDSIZE,
        seats=8,
        wifi=True,
        flight_time=178,
        departure=datetime(2026, 10, 18, 9, 0),
        availability=Availability.CONFIRMED,
        received_min=84,
        stated_total=44_820,
        base_airport="KHPN",
    )


def skybridge() -> QuoteState:
    q = "SkyBridge"
    return quote(
        q,
        headline=45_900,
        fees=[
            fee(q, F.POSITIONING, "Positioning", S, 850),
            fee(q, F.RAMP_HANDLING, "Ramp & handling", S, 450),
            fee(q, F.CATERING, "Catering", INC),
            fee(q, F.FET, "FET 7.5%", INC, percent=Decimal("7.5")),
            fee(q, F.SEGMENT_FEES, "Segment fees", INC),
        ],
        model="Bombardier Challenger 350",
        category=AircraftCategory.SUPER_MIDSIZE,
        seats=9,
        wifi=True,
        flight_time=168,
        departure=datetime(2026, 10, 18, 9, 30),
        availability=Availability.AVAILABLE,
        received_min=126,
        stated_total=47_200,
    )


def northstar() -> QuoteState:
    q = "Northstar"
    return quote(
        q,
        headline=50_200,
        fees=[
            fee(q, F.POSITIONING, "Repositioning", S, 1_400),
            fee(q, F.RAMP_HANDLING, "FBO handling", S, 800),
            fee(q, F.CATERING, "Catering", INC),
            fee(q, F.FET, "FET", INC),
            fee(q, F.SEGMENT_FEES, "Segment fees", INC),
        ],
        model="Gulfstream G280",
        category=AircraftCategory.SUPER_MIDSIZE,
        seats=9,
        wifi=True,
        flight_time=165,
        departure=datetime(2026, 10, 18, 10, 0),
        availability=Availability.SUBJECT_TO,
        received_min=216,
        stated_total=52_400,
    )


def summit(fuel: str = "open") -> QuoteState:
    """`fuel`: "open" (as extracted), "accepted" (estimate accepted), "included"."""
    q = "Summit"
    if fuel == "included":
        fuel_fee = fee(q, F.FUEL_SURCHARGE, "Fuel", INC, confidence=61, review=FieldStatus.EDITED)
    else:
        fuel_fee = fee(
            q,
            F.FUEL_SURCHARGE,
            "fuel may be extra, est. 850",
            EST,
            850,
            confidence=61,
            hedged=True,
            review=FieldStatus.ACCEPTED if fuel == "accepted" else FieldStatus.EXTRACTED,
        )
    return quote(
        q,
        headline=38_900,
        headline_confidence=98,  # PDF corroborated by the SMS
        fees=[
            fee(q, F.POSITIONING, "Positioning from KBED", S, 1_900),
            fee(q, F.RAMP_HANDLING, "Ramp / handling (KTEB)", S, 480),
            fee(
                q,
                F.CREW_OVERNIGHT,
                "crew overnight 700 extra",
                S,
                700,
                confidence=84,
                explicitly_extra=True,
            ),
            fuel_fee,
        ],
        model="Embraer Legacy 650",
        category=AircraftCategory.HEAVY,
        seats=13,
        wifi=False,
        flight_time=185,
        departure=datetime(2026, 10, 18, 9, 0),
        availability=Availability.AVAILABLE,
        received_min=312,
        all_in=True,
        extra_fields=(scalar(q, "all_in", True, 82),),
        base_airport="KBED",
    )


@dataclass(frozen=True)
class Evaluated:
    state: QuoteState
    expected: list[ExpectedFee]
    true_cost: TrueCost
    flags: list[FlagSpec]
    confidence: int | None
    confidence_mean: float | None
    score_input: ScoreInput

    @property
    def blocking(self) -> list[FlagSpec]:
        return [f for f in self.flags if f.is_blocking]


def evaluate(state: QuoteState, trip: TripContext) -> Evaluated:
    fx = load_fx_table()
    expected = expected_fees(state, trip)
    tc = normalize_quote(state, trip, fx, expected)
    flags = evaluate_flags(state, trip, tc, expected, NOW)
    low, mean = quote_confidence(state, trip.review_threshold)
    inp = build_score_input(
        state,
        tc,
        open_blocking_flags=sum(1 for f in flags if f.is_blocking),
        quote_confidence=low,
    )
    return Evaluated(state, expected, tc, flags, low, mean, inp)


def run_demo(fuel: str = "open") -> tuple[dict[str, Evaluated], RecommendationResult]:
    trip = make_trip()
    states = [atlas(), skybridge(), northstar(), summit(fuel)]
    evaluated = {s.operator_name: evaluate(s, trip) for s in states}
    result = score_trip([e.score_input for e in evaluated.values()], trip)
    return evaluated, result
