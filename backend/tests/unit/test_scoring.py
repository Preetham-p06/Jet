"""Scoring: demo fit values, fuel resolutions, imputation, dropping, gates,
tie-breaks, checks and quote confidence."""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from app.models.enums import (
    Availability,
    FieldGroup,
    FieldStatus,
    QuoteStatus,
)
from app.services.contracts import (
    ALGORITHM_VERSION,
    DEFAULT_WEIGHTS,
    FieldState,
    IneligibilityCode,
    ScoreInput,
    Signal,
)
from app.services.scoring import quote_confidence, recommendation_eligibility, score_trip
from tests.unit.demo_js184 import make_trip, run_demo, state

TRIP = make_trip()


def fits(fuel: str = "open") -> dict[str, int | None]:
    ev, res = run_demo(fuel)
    return {n: res.for_quote(e.state.quote_id).breakdown.fit for n, e in ev.items()}  # type: ignore[union-attr]


def recommended(fuel: str = "open") -> str:
    ev, res = run_demo(fuel)
    return next(n for n, e in ev.items() if e.state.quote_id == res.recommended_quote_id)


# --------------------------------------------------------------------------- demo


def test_demo_fit_scores_and_recommendation() -> None:
    ev, res = run_demo()
    assert fits() == {"Atlas": 96, "SkyBridge": 93, "Northstar": 82, "Summit": 77}
    assert recommended() == "Atlas"
    assert res.algorithm_version == ALGORITHM_VERSION
    assert [r.rank for r in res.ranking] == [1, 2, 3, 4]
    order = [next(n for n, e in ev.items() if e.state.quote_id == r.quote_id) for r in res.ranking]
    assert order == ["Atlas", "SkyBridge", "Northstar", "Summit"]
    summit = res.for_quote(ev["Summit"].state.quote_id)
    assert summit is not None and not summit.eligibility.eligible
    assert {r.code for r in summit.eligibility.reasons} == {
        IneligibilityCode.NOT_FULLY_PRICED,
        IneligibilityCode.BLOCKING_FLAGS,
    }


def test_demo_signal_values() -> None:
    ev, res = run_demo()
    expected = {
        "Atlas": (90.7, 100, 100, 93.7, 100, 100, 100, 93.2),
        "SkyBridge": (79.6, 100, 100, 89.5, 100, 100, 100, 100),
        "Northstar": (55.3, 100, 100, 82.0, 100, 70, 100, 93.3),
        "Summit": (100, 65, 80, 90.3, 0, 100, 60, 74.7),
    }
    for name, values in expected.items():
        b = res.for_quote(ev[name].state.quote_id).breakdown  # type: ignore[union-attr]
        got = tuple(round(b.signal(s).value, 1) for s in Signal)  # type: ignore[arg-type,union-attr]
        assert got == pytest.approx(values, abs=0.06), name


def test_demo_checks_all_pass_for_atlas() -> None:
    _, res = run_demo()
    assert [(c.key, c.passed) for c in res.checks] == [
        ("schedule", True),
        ("lowest_cost", True),
        ("wifi", True),
        ("seats", True),
        ("no_crew_overnight", True),
    ]
    assert res.checks[3].label == "8-seat configuration"


@pytest.mark.parametrize(("fuel", "atlas", "summit"), [("accepted", 96, 82), ("included", 95, 82)])
def test_atlas_wins_under_every_fuel_resolution(fuel: str, atlas: int, summit: int) -> None:
    f = fits(fuel)
    assert (f["Atlas"], f["Summit"]) == (atlas, summit)
    assert recommended(fuel) == "Atlas"


def test_demo_quote_confidence() -> None:
    ev, _ = run_demo()
    assert ev["Summit"].confidence == 61
    assert ev["Atlas"].confidence == 92
    mean = ev["Summit"].confidence_mean
    assert mean is not None and 61 < mean < 100


# --------------------------------------------------------------------------- confidence


def fs(key: str, conf: int, status: FieldStatus = FieldStatus.EXTRACTED, value: object = 1):
    return FieldState(uuid.uuid4(), key, FieldGroup.SCALAR, value, conf, status)


def test_quote_confidence_min_and_mean() -> None:
    s = state(
        fields=(
            fs("headline_price", 90, value={"amount_minor": 900_000, "currency": "USD"}),
            fs(
                "fee.fuel_surcharge",
                60,
                value={"amount": {"amount_minor": 100_000, "currency": "USD"}},
            ),
            fs("seats", 50, FieldStatus.VERIFIED),
            fs("tail_number", 10),  # not material
        )
    )
    low, mean = quote_confidence(s, 75)
    assert low == 60
    assert mean == pytest.approx(87.0)  # (90 * 9 + 60 * 1) / 10; seats has no money weight


def test_quote_confidence_accepted_and_edited() -> None:
    s = state(fields=(fs("seats", 50, FieldStatus.ACCEPTED), fs("wifi", 40, FieldStatus.EDITED)))
    assert quote_confidence(s, 75) == (75, 87.5)
    assert quote_confidence(state(), 75) == (None, None)


# --------------------------------------------------------------------------- engine


def inp(name: str, known: int | None, **kw: object) -> ScoreInput:
    base: dict[str, object] = dict(
        quote_id=uuid.uuid5(uuid.NAMESPACE_URL, name),
        operator_name=name,
        status=QuoteStatus.ACTIVE,
        created_at=datetime(2026, 10, 1, tzinfo=UTC),
        headline_cents=known,
        known_total_cents=known,
        upper_total_cents=known,
        is_fully_priced=True,
        open_blocking_flags=0,
        quote_confidence=90,
        seats=8,
        wifi=True,
        availability=Availability.AVAILABLE,
    )
    base.update(kw)
    return ScoreInput(**base)  # type: ignore[arg-type]


def test_missing_signal_is_imputed_with_cohort_median() -> None:
    quotes = [
        inp("a", 1_000_000, flight_time_minutes=100),
        inp("b", 1_000_000, flight_time_minutes=120),
        inp("c", 1_000_000, flight_time_minutes=140),
        inp("d", 1_000_000),
    ]
    res = score_trip(quotes, TRIP)
    d = res.for_quote(quotes[3].quote_id).breakdown.signal(Signal.TIMING)  # type: ignore[union-attr]
    b = res.for_quote(quotes[1].quote_id).breakdown.signal(Signal.TIMING)  # type: ignore[union-attr]
    assert d is not None and b is not None
    assert d.raw is None and d.imputed and d.value == b.value


def test_signal_missing_everywhere_is_dropped() -> None:
    quotes = [inp("a", 1_000_000), inp("b", 1_100_000)]
    res = score_trip(quotes, TRIP)
    for r in res.ranking:
        routing = r.breakdown.signal(Signal.ROUTING)
        assert routing is not None and routing.dropped and routing.value is None
    # Only pricing differs, so dropping must renormalize identically for both.
    a = res.for_quote(quotes[0].quote_id).breakdown.fit  # type: ignore[union-attr]
    assert a == 100


def test_capacity_gate() -> None:
    small = inp("small", 900_000, seats=6)
    big = inp("big", 1_000_000)
    res = score_trip([small, big], TRIP)
    assert res.recommended_quote_id == big.quote_id
    reasons = recommendation_eligibility(small, TRIP).reasons
    assert [r.code for r in reasons] == [IneligibilityCode.INSUFFICIENT_CAPACITY]
    aircraft = res.for_quote(small.quote_id).breakdown.signal(Signal.AIRCRAFT)  # type: ignore[union-attr]
    assert aircraft is not None and aircraft.raw == 0


def test_eligibility_reasons() -> None:
    q = inp(
        "x",
        None,
        status=QuoteStatus.WITHDRAWN,
        availability=Availability.UNAVAILABLE,
        open_blocking_flags=2,
    )
    codes = [r.code for r in recommendation_eligibility(q, TRIP).reasons]
    assert codes == [
        IneligibilityCode.NOT_ACTIVE,
        IneligibilityCode.NO_HEADLINE,
        IneligibilityCode.BLOCKING_FLAGS,
        IneligibilityCode.UNAVAILABLE,
    ]
    assert recommendation_eligibility(inp("ok", 1), TRIP).eligible


def test_tie_breaks() -> None:
    t = datetime(2026, 10, 1, tzinfo=UTC)
    a = inp("a", 1_000_000, quote_confidence=80, created_at=t)
    b = inp("b", 1_000_000, quote_confidence=90, created_at=t)
    assert score_trip([a, b], TRIP).recommended_quote_id == b.quote_id
    c = inp("c", 1_000_000, quote_confidence=90, created_at=t.replace(hour=1))
    assert score_trip([c, b], TRIP).recommended_quote_id == b.quote_id
    # Identical everything: id decides, deterministically.
    x, y = inp("x", 1_000_000), inp("y", 1_000_000)
    first = min((x, y), key=lambda q: str(q.quote_id))
    assert score_trip([y, x], TRIP).recommended_quote_id == first.quote_id


def test_no_eligible_quote_means_no_recommendation() -> None:
    res = score_trip([inp("a", 1_000_000, is_fully_priced=False)], TRIP)
    assert res.recommended_quote_id is None and res.checks == ()
    assert score_trip([], TRIP).ranking == ()


def test_custom_weights() -> None:
    quotes = [inp("cheap", 1_000_000, wifi=False), inp("wifi", 1_200_000)]
    only_price = {s: (1.0 if s is Signal.PRICING else 0.0) for s in Signal}
    assert score_trip(quotes, TRIP, weights=only_price).recommended_quote_id == quotes[0].quote_id
    only_prefs = {s: (1.0 if s is Signal.PREFERENCES else 0.0) for s in Signal}
    ws_trip = make_trip(scoring_weights={k.value: v for k, v in only_prefs.items()})
    res = score_trip(quotes, ws_trip)
    assert res.recommended_quote_id == quotes[1].quote_id
    assert res.weights[Signal.PRICING] == 0.0
    assert score_trip(quotes, TRIP).weights == dict(DEFAULT_WEIGHTS)


def test_crew_and_routing_signals() -> None:
    q = inp(
        "q",
        1_000_000,
        crew_overnight_charged=True,
        extra_crew_charged=True,
        positioning_cents=50_000,
        tech_stop=True,
    )
    b = score_trip([q], TRIP).ranking[0].breakdown
    assert b.signal(Signal.CREW).value == 40  # type: ignore[union-attr]
    # 5 % positioning: 100 - 10 * (5 - 2) = 70, minus 30 for the tech stop.
    assert b.signal(Signal.ROUTING).value == pytest.approx(40.0)  # type: ignore[union-attr]


def test_routing_signal_formula() -> None:
    q = inp("q", 1_000_000, positioning_cents=40_000)  # 4 % -> 100 - 10 * 2 = 80
    b = score_trip([q], TRIP).ranking[0].breakdown
    assert b.signal(Signal.ROUTING).value == pytest.approx(80.0)  # type: ignore[union-attr]
    stop = score_trip([replace(q, tech_stop=True)], TRIP).ranking[0].breakdown
    assert stop.signal(Signal.ROUTING).value == pytest.approx(50.0)  # type: ignore[union-attr]
