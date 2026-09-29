"""Expected-fee rules: FET, segment fees, international, de-icing, crew overnight,
positioning and learned thresholds."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from app.models.enums import AircraftCategory, AmountStatus, FeeCategory, FlagSeverity
from app.services import airports
from app.services.contracts import LearnedStat, LegState
from app.services.fee_rules import expected_fees, rule_estimate
from tests.unit.demo_js184 import line, make_trip, state

F = FeeCategory
A = AmountStatus


def leg(o: str, d: str, when: datetime, seq: int = 1) -> LegState:
    return LegState(
        seq=seq,
        origin_icao=o,
        destination_icao=d,
        depart_local=when,
        depart_tz="America/New_York",
        depart_utc=when.replace(tzinfo=UTC),
    )


def trip_for(*legs: LegState):
    codes = [c for lg in legs for c in (lg.origin_icao, lg.destination_icao)]
    return make_trip(legs=legs, airports=airports.airports_for(codes))


def by_rule(fees):
    return {f.rule_id: f for f in fees}


def test_domestic_fet_and_segment_fees() -> None:
    fees = by_rule(expected_fees(state(), make_trip()))
    assert fees["fet"].severity is FlagSeverity.WARNING
    assert fees["fet"].estimate_cents == 75_000  # 7.5 % of $10,000
    assert fees["segment_fees"].severity is FlagSeverity.INFO
    assert fees["segment_fees"].estimate_cents == 7 * 530
    assert "international" not in fees


def test_fet_base_excludes_taxes_and_counts_stated_fees() -> None:
    s = state((line(F.RAMP_HANDLING, A.STATED, 100_000), line(F.TAXES, A.STATED, 50_000)))
    assert by_rule(expected_fees(s, make_trip()))["fet"].estimate_cents == 82_500


def test_international_trip_has_no_fet() -> None:
    trip = trip_for(leg("KTEB", "MYNN", datetime(2026, 7, 1, 9)))
    fees = by_rule(expected_fees(state(aircraft_category=AircraftCategory.MIDSIZE), trip))
    assert "fet" not in fees and "segment_fees" not in fees
    assert fees["international"].severity is FlagSeverity.WARNING
    assert fees["international"].estimate_cents == 150_000


@pytest.mark.parametrize(
    ("origin", "month", "severity"),
    [
        ("KTEB", 10, FlagSeverity.INFO),
        ("KTEB", 4, FlagSeverity.INFO),
        ("KTEB", 1, FlagSeverity.WARNING),
        ("KTEB", 12, FlagSeverity.WARNING),
        ("KTEB", 7, None),
        ("KOPF", 1, None),
        ("KABQ", 2, FlagSeverity.WARNING),  # listed despite latitude
    ],
)
def test_deicing_by_month_and_zone(origin: str, month: int, severity: FlagSeverity | None) -> None:
    trip = trip_for(leg(origin, "KMIA", datetime(2026, month, 10, 9)))
    fee = by_rule(expected_fees(state(), trip)).get("deicing")
    assert (fee.severity if fee else None) is severity


def test_crew_overnight_on_multi_day_trip_only() -> None:
    same_day = trip_for(
        leg("KTEB", "KOPF", datetime(2026, 7, 1, 9)),
        leg("KOPF", "KTEB", datetime(2026, 7, 1, 17), 2),
    )
    assert "crew_overnight" not in by_rule(expected_fees(state(), same_day))
    two_nights = trip_for(
        leg("KTEB", "KOPF", datetime(2026, 7, 1, 9)),
        leg("KOPF", "KTEB", datetime(2026, 7, 3, 17), 2),
    )
    fee = by_rule(expected_fees(state(aircraft_category=AircraftCategory.HEAVY), two_nights))[
        "crew_overnight"
    ]
    assert fee.severity is FlagSeverity.WARNING and fee.estimate_cents == 2 * 120_000
    covered = state((line(F.CREW_OVERNIGHT, A.STATED, 70_000),))
    assert "crew_overnight" not in by_rule(expected_fees(covered, two_nights))


def test_positioning_rule() -> None:
    s = state(base_airport_icao="KHPN", aircraft_category=AircraftCategory.MIDSIZE)
    fee = by_rule(expected_fees(s, make_trip()))["positioning"]
    assert fee.severity is FlagSeverity.WARNING
    assert fee.estimate_cents is not None and 150_000 < fee.estimate_cents < 400_000
    with_line = replace(s, fees=(line(F.POSITIONING, A.STATED, 120_000),))
    assert "positioning" not in by_rule(expected_fees(with_line, make_trip()))
    at_origin = replace(s, base_airport_icao="KTEB")
    assert "positioning" not in by_rule(expected_fees(at_origin, make_trip()))


def test_nothing_fires_when_present_or_all_in() -> None:
    s = state(
        (
            line(F.FET, A.INCLUDED),
            line(F.SEGMENT_FEES, A.INCLUDED),
            line(F.DEICING, A.NOT_APPLICABLE),
        )
    )
    assert expected_fees(s, make_trip()) == []
    all_in = state(all_in=True)
    assert {f.rule_id for f in expected_fees(all_in, make_trip())} == {"deicing"}


@pytest.mark.parametrize(
    ("n", "freq", "severity"),
    [
        (5, 0.6, FlagSeverity.INFO),
        (4, 1.0, None),
        (9, 0.9, FlagSeverity.INFO),
        (10, 0.85, FlagSeverity.WARNING),
        (20, 0.59, None),
    ],
)
def test_learned_thresholds(n: int, freq: float, severity: FlagSeverity | None) -> None:
    learned = {F.LANDING: LearnedStat(n=n, frequency=freq, median_cents=31_000)}
    fees = [
        f for f in expected_fees(state(), make_trip(), learned=learned) if f.source == "learned"
    ]
    if severity is None:
        assert fees == []
    else:
        (fee,) = fees
        assert (fee.severity, fee.rule_id, fee.estimate_cents) == (severity, "learned:KTEB", 31_000)
        assert fee.stat is learned[F.LANDING]


def test_learned_skips_categories_a_rule_covers_or_quote_has() -> None:
    learned = {
        F.FET: LearnedStat(n=20, frequency=1.0),
        F.RAMP_HANDLING: LearnedStat(n=20, frequency=1.0),
    }
    s = state((line(F.RAMP_HANDLING, A.STATED, 1_000),))
    fees = expected_fees(s, make_trip(), learned=learned)
    assert [f.rule_id for f in fees if f.category is F.FET] == ["fet"]
    assert all(f.category is not F.RAMP_HANDLING for f in fees)


def test_rule_estimate_for_present_not_stated_lines() -> None:
    trip = make_trip()
    assert rule_estimate(F.DEICING, state(), trip) == (350_000, "rule:deicing")
    assert rule_estimate(F.SEGMENT_FEES, state(), trip) == (7 * 530, "rule:segment_fees")
    assert rule_estimate(F.FUEL_SURCHARGE, state(), trip) == (None, None)
