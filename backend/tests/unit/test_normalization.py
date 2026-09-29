"""True cost: demo totals, status semantics, all in, hourly, percent FET, FX,
stated-total mismatch, and hypothesis properties."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from types import MappingProxyType

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.models.enums import (
    AmountStatus,
    FeeCategory,
    FeeUnit,
    FieldStatus,
    FlagSeverity,
    IncludedBy,
    PricingBasis,
)
from app.services.contracts import ExpectedFee, FeeLineState, QuoteState, TrueCost
from app.services.fee_rules import expected_fees
from app.services.fx import load_fx_table
from app.services.normalization import (
    normalize_quote,
    reconciling_lines,
    total_tolerance_cents,
)
from tests.unit.demo_js184 import line, make_trip, run_demo, state

F = FeeCategory
A = AmountStatus
FX = load_fx_table()
TRIP = make_trip()


def norm(s: QuoteState, expected: list[ExpectedFee] | None = None) -> TrueCost:
    return normalize_quote(s, TRIP, FX, [] if expected is None else expected)


# --------------------------------------------------------------------------- demo


def test_demo_totals() -> None:
    ev, _ = run_demo()
    totals = {
        k: (e.true_cost.known_total_cents, e.true_cost.upper_total_cents) for k, e in ev.items()
    }
    assert totals == {
        "Atlas": (4_482_000, 4_482_000),
        "SkyBridge": (4_720_000, 4_720_000),
        "Northstar": (5_240_000, 5_240_000),
        "Summit": (4_198_000, 4_283_000),
    }
    assert [e.true_cost.is_fully_priced for e in ev.values()] == [True, True, True, False]
    for name in ("Atlas", "SkyBridge", "Northstar"):
        assert ev[name].true_cost.total_mismatch is None


def test_demo_summit_lines() -> None:
    ev, _ = run_demo()
    tc = ev["Summit"].true_cost
    assert tc.all_in_itemized_conflict
    assert tc.added_charges_cents == 4_198_000 - 3_890_000
    assert tc.price_for_ranking_cents == 4_283_000
    all_in = {ln.category for ln in tc.lines if ln.included_by is IncludedBy.ALL_IN}
    assert all_in == {F.FET, F.SEGMENT_FEES, F.TAXES, F.LANDING, F.CATERING}
    fuel = next(ln for ln in tc.lines if ln.category is F.FUEL_SURCHARGE)
    assert (fuel.counts_in_known, fuel.counts_in_upper, fuel.estimate_cents) == (
        False,
        True,
        85_000,
    )
    assert [c.rule_id for c in tc.conditional_charges] == ["deicing"]
    orders = [ln.sort_order for ln in tc.lines]
    assert orders == sorted(orders) == list(range(len(tc.lines)))


def test_demo_fuel_resolutions() -> None:
    accepted, _ = run_demo("accepted")
    included, _ = run_demo("included")
    a, i = accepted["Summit"].true_cost, included["Summit"].true_cost
    assert (a.known_total_cents, a.upper_total_cents, a.is_fully_priced) == (
        4_283_000,
        4_283_000,
        True,
    )
    assert (i.known_total_cents, i.upper_total_cents, i.is_fully_priced) == (
        4_198_000,
        4_198_000,
        True,
    )


# --------------------------------------------------------------------------- status rules


def test_included_amount_is_never_added() -> None:
    tc = norm(state((line(F.CATERING, A.INCLUDED, 50_000),)))
    assert tc.known_total_cents == tc.upper_total_cents == 1_000_000
    assert tc.lines[0].amount_cents is None
    assert tc.lines[0].included_by is IncludedBy.EXPLICIT
    assert tc.lines[0].original_amount_minor == 50_000


def test_waived_and_not_applicable_add_nothing() -> None:
    tc = norm(state((line(F.LANDING, A.WAIVED, 20_000), line(F.DEICING, A.NOT_APPLICABLE))))
    assert tc.known_total_cents == tc.upper_total_cents == 1_000_000
    assert tc.is_fully_priced


def test_stated_and_extra_add_to_both() -> None:
    tc = norm(
        state(
            (
                line(F.RAMP_HANDLING, A.STATED, 42_000),
                line(F.CREW_OVERNIGHT, A.STATED, 70_000, explicitly_extra=True),
            )
        )
    )
    assert tc.known_total_cents == tc.upper_total_cents == 1_112_000
    assert tc.is_fully_priced


def test_estimate_unaccepted_vs_accepted() -> None:
    est = line(F.FUEL_SURCHARGE, A.ESTIMATED, 85_000, hedged=True)
    open_ = norm(state((est,)))
    assert (open_.known_total_cents, open_.upper_total_cents) == (1_000_000, 1_085_000)
    assert not open_.is_fully_priced
    done = norm(state((replace(est, review_status=FieldStatus.ACCEPTED),)))
    assert (done.known_total_cents, done.upper_total_cents) == (1_085_000, 1_085_000)
    assert done.is_fully_priced


def test_not_stated_uses_rule_estimate_in_upper_only() -> None:
    tc = norm(state((line(F.DEICING, A.NOT_STATED, hedged=True),)))
    ln = tc.lines[0]
    assert ln.estimate_basis == "rule:deicing"
    assert tc.known_total_cents == 1_000_000
    assert tc.upper_total_cents == 1_000_000 + (ln.estimate_cents or 0)
    assert not tc.is_fully_priced


def test_not_stated_prefers_operator_then_expected_estimate() -> None:
    exp = ExpectedFee(F.OTHER, FlagSeverity.INFO, "learned", 12_300, "learned:KTEB", "learned")
    tc = norm(state((line(F.OTHER, A.NOT_STATED, label="cleaning"),)), [exp])
    assert (tc.lines[0].estimate_cents, tc.lines[0].estimate_basis) == (12_300, "learned:KTEB")
    op = norm(state((line(F.OTHER, A.NOT_STATED, 5_000, label="cleaning"),)), [exp])
    assert (op.lines[0].estimate_cents, op.lines[0].estimate_basis) == (5_000, "operator_estimate")


def test_per_unit_lines_multiply() -> None:
    tc = norm(
        state(
            (
                line(F.CREW, A.STATED, 10_000, unit=FeeUnit.PER_HOUR, quantity=Decimal("3.2")),
                line(F.CATERING, A.STATED, 5_000, unit=FeeUnit.PER_PAX),
            )
        )
    )
    assert tc.known_total_cents == 1_000_000 + 32_000 + 35_000


def test_percent_fet_on_base_excluding_taxes() -> None:
    fees = (
        line(F.RAMP_HANDLING, A.STATED, 100_000),
        line(F.SEGMENT_FEES, A.STATED, 3_710),
        line(F.FET, A.STATED, unit=FeeUnit.PERCENT, percent=Decimal("7.5")),
    )
    tc = norm(state(fees))
    fet = next(ln for ln in tc.lines if ln.category is F.FET)
    assert fet.amount_cents == 82_500  # 7.5 % of 1,100,000
    assert tc.known_total_cents == 1_100_000 + 3_710 + 82_500


def test_percent_fet_upper_includes_unaccepted_estimates() -> None:
    fet = line(F.FET, A.STATED, unit=FeeUnit.PERCENT, percent=Decimal("7.5"))
    fuel = line(F.FUEL_SURCHARGE, A.ESTIMATED, 100_000)
    before = norm(state((fet, fuel)))
    assert before.known_total_cents == 1_000_000 + 75_000
    assert before.upper_total_cents == 1_100_000 + 82_500
    after = norm(state((fet, replace(fuel, review_status=FieldStatus.ACCEPTED))))
    assert after.known_total_cents == after.upper_total_cents == 1_182_500


def test_synthetic_fet_estimate_uses_upper_base() -> None:
    fuel = line(F.FUEL_SURCHARGE, A.ESTIMATED, 100_000)
    s = state((fuel,))
    before = norm(s, expected_fees(s, TRIP))
    fet = next(ln for ln in before.lines if ln.category is F.FET)
    assert fet.estimate_cents == 82_500
    accepted = state((replace(fuel, review_status=FieldStatus.ACCEPTED),))
    after = norm(accepted, expected_fees(accepted, TRIP))
    assert after.upper_total_cents == before.upper_total_cents


def test_not_stated_fet_estimate_uses_normalized_lines() -> None:
    trip2 = make_trip(legs=(TRIP.legs[0], replace(TRIP.legs[0], seq=2)))
    fees = (
        line(F.LANDING, A.STATED, 50_000, unit=FeeUnit.PER_LEG),
        line(F.FET, A.NOT_STATED),
    )
    tc = normalize_quote(state(fees), trip2, FX, [])
    fet = next(ln for ln in tc.lines if ln.category is F.FET)
    assert (fet.estimate_cents, fet.estimate_basis) == (82_500, "rule:fet")  # 7.5 % of 1.1 M


def test_not_stated_fet_estimate_uses_the_given_fx_table() -> None:
    fx = replace(FX, rates=MappingProxyType({**FX.rates, "EUR": Decimal("2")}))
    tc = normalize_quote(state((line(F.FET, A.NOT_STATED),), currency="EUR"), TRIP, fx, [])
    fet = next(ln for ln in tc.lines if ln.category is F.FET)
    assert tc.headline_cents == 2_000_000
    assert fet.estimate_cents == 150_000


# --------------------------------------------------------------------------- all in, expected


def test_all_in_covers_missing_categories_but_keeps_itemized() -> None:
    tc = norm(state((line(F.POSITIONING, A.STATED, 190_000),), all_in=True))
    assert tc.all_in_itemized_conflict
    assert tc.known_total_cents == 1_190_000
    covered = {ln.category for ln in tc.lines if ln.included_by is IncludedBy.ALL_IN}
    assert covered == {F.FET, F.SEGMENT_FEES, F.TAXES, F.LANDING, F.CATERING, F.RAMP_HANDLING}


def test_all_in_with_only_extra_lines_is_not_a_conflict() -> None:
    tc = norm(
        state((line(F.CREW_OVERNIGHT, A.STATED, 70_000, explicitly_extra=True),), all_in=True)
    )
    assert not tc.all_in_itemized_conflict
    assert tc.known_total_cents == 1_070_000


def test_warning_expected_fee_becomes_synthetic_line() -> None:
    s = state((line(F.RAMP_HANDLING, A.STATED, 100_000),))
    expected = expected_fees(s, TRIP)
    assert {e.rule_id for e in expected} == {"fet", "segment_fees", "deicing"}
    tc = norm(s, expected)
    fet = next(ln for ln in tc.lines if ln.category is F.FET)
    assert fet.is_synthetic and fet.amount_status is A.NOT_STATED
    assert (fet.estimate_cents, fet.estimate_basis) == (82_500, "rule:fet")
    assert tc.known_total_cents == 1_100_000
    assert tc.upper_total_cents == 1_182_500
    assert not tc.is_fully_priced
    assert {c.rule_id for c in tc.conditional_charges} == {"segment_fees", "deicing"}


# --------------------------------------------------------------------------- headline


def test_hourly_headline_from_billable_hours() -> None:
    s = state(
        headline=None,
        pricing_basis=PricingBasis.HOURLY,
        hourly_rate_minor=600_000,
        billable_hours=Decimal("2.5"),
        daily_minimum_hours=Decimal("2"),
    )
    tc = norm(s)
    assert (tc.headline_cents, tc.headline_estimated, tc.is_fully_priced) == (
        1_500_000,
        False,
        True,
    )


def test_hourly_headline_from_flight_time_is_estimated() -> None:
    s = state(
        headline=None,
        pricing_basis=PricingBasis.HOURLY,
        hourly_rate_minor=600_000,
        flight_time_minutes=178,
    )
    tc = norm(s)
    assert tc.headline_cents == 1_800_000  # ceil_0.1(2.97) = 3.0 h
    assert tc.headline_estimated and not tc.is_fully_priced


def test_hourly_daily_minimum_alone_uses_flight_time_and_is_estimated() -> None:
    # $5,000/hr, 2 h daily minimum, 3 h flight, no billable hours stated.
    s = state(
        headline=None,
        pricing_basis=PricingBasis.HOURLY,
        hourly_rate_minor=500_000,
        daily_minimum_hours=Decimal("2"),
        flight_time_minutes=180,
    )
    tc = norm(s)
    assert tc.headline_cents == 1_500_000  # max(2, 3.0) h
    assert tc.headline_estimated and not tc.is_fully_priced


def test_hourly_daily_minimum_floors_short_flight() -> None:
    s = state(
        headline=None,
        pricing_basis=PricingBasis.HOURLY,
        hourly_rate_minor=500_000,
        daily_minimum_hours=Decimal("2"),
        flight_time_minutes=61,
    )
    tc = norm(s)
    assert tc.headline_cents == 1_000_000  # max(2, 1.1) h
    assert tc.headline_estimated


def test_hourly_daily_minimum_without_flight_time_is_estimated() -> None:
    s = state(
        headline=None,
        pricing_basis=PricingBasis.HOURLY,
        hourly_rate_minor=500_000,
        daily_minimum_hours=Decimal("2"),
    )
    tc = norm(s)
    assert tc.headline_cents == 1_000_000
    assert tc.headline_estimated and not tc.is_fully_priced


def test_missing_headline_gives_no_totals() -> None:
    tc = norm(state(headline=None))
    assert tc.known_total_cents is None and tc.upper_total_cents is None
    assert not tc.is_fully_priced


# --------------------------------------------------------------------------- currency


def test_fx_converts_each_line() -> None:
    s = state(
        (
            line(F.RAMP_HANDLING, A.STATED, 50_000, currency="EUR"),
            line(F.LANDING, A.STATED, 10_000),
        ),
        headline=3_250_000,
        currency="EUR",
    )
    tc = norm(s)
    assert tc.headline_cents == 3_510_000
    assert tc.fx is not None and tc.fx.currency == "EUR" and tc.fx.rate == Decimal("1.08")
    assert tc.known_total_cents == 3_510_000 + 54_000 + 10_000


def test_unknown_currency() -> None:
    tc = norm(state(currency="XYZ"))
    assert tc.unknown_currency == "XYZ"
    assert tc.headline_cents is None and not tc.is_fully_priced


# --------------------------------------------------------------------------- stated total


def test_tolerance() -> None:
    assert total_tolerance_cents(50_000) == 100
    assert total_tolerance_cents(4_482_000) == 4_482


def test_stated_total_above_raises_known() -> None:
    tc = norm(state((line(F.RAMP_HANDLING, A.STATED, 40_000),), stated_total_minor=1_100_000))
    assert tc.total_mismatch is not None and tc.total_mismatch.direction == "above"
    assert tc.total_mismatch.difference_cents == 60_000
    assert tc.known_total_cents == tc.upper_total_cents == 1_100_000


def test_stated_total_below_keeps_computed_and_names_lines() -> None:
    fees = (
        line(F.RAMP_HANDLING, A.STATED, 42_000, label="Ramp"),
        line(F.POSITIONING, A.STATED, 120_000, label="Positioning"),
        line(F.FUEL_SURCHARGE, A.STATED, 140_000, label="Fuel"),
    )
    tc = norm(state(fees, stated_total_minor=1_000_000 + 42_000))
    assert tc.known_total_cents == 1_302_000
    mm = tc.total_mismatch
    assert mm is not None and mm.direction == "below"
    assert set(mm.reconciling_labels) == {"Positioning", "Fuel"}


def test_stated_total_within_tolerance() -> None:
    tc = norm(state((line(F.LANDING, A.STATED, 10_000),), stated_total_minor=1_010_050))
    assert tc.total_mismatch is None


def test_reconciling_lines_none_when_no_subset() -> None:
    tc = norm(state((line(F.LANDING, A.STATED, 10_000),)))
    assert reconciling_lines(tc.lines, 55_555, 100) is None


# --------------------------------------------------------------------------- properties

_categories = st.sampled_from([c for c in FeeCategory if c is not FeeCategory.FET])
_status = st.sampled_from(list(AmountStatus))


@st.composite
def _fee_lines(draw: st.DrawFn) -> FeeLineState:
    status = draw(_status)
    amount = draw(st.one_of(st.none(), st.integers(min_value=0, max_value=5_000_000)))
    return FeeLineState(
        category=draw(_categories),
        label="x",
        status=status,
        amount_minor=amount,
        currency="USD" if amount is not None else None,
        explicitly_extra=draw(st.booleans()),
        hedged=draw(st.booleans()),
        review_status=draw(st.sampled_from(list(FieldStatus))),
        field_id=draw(st.uuids()),
    )


_states = st.builds(
    lambda fees, headline, all_in, stated: state(
        tuple(fees), headline=headline, all_in=all_in, stated_total_minor=stated
    ),
    st.lists(_fee_lines(), max_size=8),
    st.integers(min_value=1, max_value=50_000_000),
    st.booleans(),
    st.one_of(st.none(), st.integers(min_value=1, max_value=80_000_000)),
)


@settings(max_examples=150, deadline=None)
@given(_states)
def test_property_known_le_upper(s: QuoteState) -> None:
    tc = norm(s, expected_fees(s, TRIP))
    assert tc.known_total_cents is not None and tc.upper_total_cents is not None
    assert tc.known_total_cents <= tc.upper_total_cents


@settings(max_examples=150, deadline=None)
@given(_states, _categories, st.integers(min_value=0, max_value=5_000_000))
def test_property_included_line_never_changes_totals(
    s: QuoteState, category: FeeCategory, amount: int
) -> None:
    s = replace(s, stated_total_minor=None, fees=tuple(f for f in s.fees if f.category != category))
    before = norm(s)
    added = replace(s, fees=(*s.fees, line(category, A.INCLUDED, amount)))
    after = norm(added)
    assert (before.known_total_cents, before.upper_total_cents) == (
        after.known_total_cents,
        after.upper_total_cents,
    )


@settings(max_examples=150, deadline=None)
@given(_states, st.integers(min_value=1, max_value=5_000_000))
def test_property_extra_line_raises_both_totals(s: QuoteState, amount: int) -> None:
    s = replace(s, stated_total_minor=None)
    before = norm(s)
    extra = line(F.OTHER, A.STATED, amount, explicitly_extra=True, label="extra item")
    after = norm(replace(s, fees=(*s.fees, extra)))
    assert after.known_total_cents == (before.known_total_cents or 0) + amount
    assert after.upper_total_cents == (before.upper_total_cents or 0) + amount


_estimate_statuses = st.sampled_from([A.ESTIMATED, A.NOT_STATED])


@settings(max_examples=200, deadline=None)
@given(
    _states,
    st.booleans(),
    st.data(),
)
def test_property_accepting_an_estimate_never_exceeds_old_upper(
    s: QuoteState, percent_fet: bool, data: st.DataObject
) -> None:
    s = replace(s, stated_total_minor=None)
    if percent_fet:
        fet = line(F.FET, A.STATED, unit=FeeUnit.PERCENT, percent=Decimal("7.5"))
        s = replace(s, fees=(*s.fees, fet))
    candidates = [
        i
        for i, f in enumerate(s.fees)
        if f.status in (A.ESTIMATED, A.NOT_STATED) and not f.is_accepted
    ]
    extra = line(F.FUEL_SURCHARGE, data.draw(_estimate_statuses), 100_000)
    if not candidates:
        s = replace(s, fees=(*s.fees, extra))
        candidates = [len(s.fees) - 1]
    i = data.draw(st.sampled_from(candidates))
    before = norm(s, expected_fees(s, TRIP))
    fees = list(s.fees)
    fees[i] = replace(fees[i], review_status=FieldStatus.ACCEPTED)
    accepted = replace(s, fees=tuple(fees))
    after = norm(accepted, expected_fees(accepted, TRIP))
    assert after.known_total_cents is not None and before.upper_total_cents is not None
    assert after.known_total_cents <= before.upper_total_cents


@pytest.mark.parametrize("status", [A.STATED, A.ESTIMATED, A.NOT_STATED])
def test_quote_lines_keep_their_field(status: AmountStatus) -> None:
    src = line(F.LANDING, status, 1_000)
    tc = norm(state((src,)), [])
    assert tc.lines[0].field_id == src.field_id and not tc.lines[0].is_synthetic
