"""Proposal pricing math, client aircraft labels, and analytics helpers (pure)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.models import Operator
from app.services.analytics import default_range, percentile
from app.services.proposals import client_aircraft_label, option_prices


@pytest.mark.parametrize(
    ("cost_cents", "markup", "expected_cents"),
    [
        (4_000_000, Decimal("5"), 4_200_000),
        (4_283_000, Decimal("5"), 4_497_200),  # 44,971.50 rounds half up to 44,972
        (10_050, Decimal("0"), 10_100),  # $100.50 -> $101
        (99_949, Decimal("0"), 100_000),  # $999.49 -> $1,000, never below cost
        (4_482_040, Decimal("0"), 4_482_100),  # $44,820.40 -> $44,821
        (4_482_000, Decimal("0"), 4_482_000),
        (1_000_000, Decimal("2.5"), 1_025_000),
        (1_234_567, Decimal("12.35"), 1_387_000),  # 13,870.36... -> 13,870
        (0, Decimal("10"), 0),
    ],
)
def test_client_total_rounds_half_up_to_whole_dollars(
    cost_cents: int, markup: Decimal, expected_cents: int
) -> None:
    (total,) = option_prices([cost_cents], markup)
    assert total == expected_cents
    assert total % 100 == 0


def test_option_prices_keeps_order_and_one_markup() -> None:
    assert option_prices([100_000, 200_000, 300_049], Decimal("10")) == [
        110_000,
        220_000,
        330_100,  # 3,300.539 -> 3,301
    ]
    assert option_prices([], Decimal("5")) == []


def test_markup_is_never_negative_for_nonnegative_rates() -> None:
    for cost in (1, 49, 50, 99, 12_345, 4_283_049):
        (total,) = option_prices([cost], Decimal("0"))
        assert 0 <= total - cost < 100


@settings(max_examples=300, deadline=None)
@given(
    st.integers(min_value=0, max_value=10**10),
    st.decimals(min_value=0, max_value=100, places=2),
)
def test_property_client_total_never_below_cost(cost: int, markup: Decimal) -> None:
    (total,) = option_prices([cost], markup)
    assert total >= cost
    assert total % 100 == 0


def test_client_label_strips_operator_tokens_and_tail() -> None:
    op = Operator(name="Atlas Air Charter", aliases=["Atlas Jets LLC"], normalized_name="atlas")
    label = client_aircraft_label(
        "Atlas Citation Latitude N684AC", operator=op, tail_number="N684AC"
    )
    assert "Atlas" not in label
    assert "N684AC" not in label
    assert "Latitude" in label


def test_client_label_falls_back_to_category_then_generic() -> None:
    op = Operator(name="Atlas", aliases=[], normalized_name="atlas")
    assert client_aircraft_label("Atlas", operator=op, category_label="Midsize") == "Midsize"
    assert client_aircraft_label(None, operator=op) == "Private jet"


WHEELS_UP = Operator(
    name="Wheels Up", aliases=["Wheels Up Partners LLC"], normalized_name="wheelsup"
)


def test_client_label_hides_operator_and_tail_in_review_example() -> None:
    label = client_aircraft_label(
        "Gulfstream G-IV SP - Wheels-Up fleet (N-684AC)",
        operator=WHEELS_UP,
        tail_number="N684AC",
        category_label="Heavy jet",
    )
    assert label == "Gulfstream G450"  # GIV-SP is a dictionary alias


@pytest.mark.parametrize(
    "model",
    [
        "Skyfarer X9 - Wheels-Up fleet (N-684AC)",
        "Wheels-Up Skyfarer X9 N-684AC",
        "WHEELS UP: Skyfarer X9, tail N684AC",
        "Skyfarer X9 n684ac",
        "Skyfarer X9 G-LXRY",
    ],
)
def test_client_label_sanitizes_unknown_models(model: str) -> None:
    label = client_aircraft_label(model, operator=WHEELS_UP, tail_number=None)
    assert label == "Skyfarer X9"


def test_client_label_uses_category_when_nothing_is_left() -> None:
    label = client_aircraft_label(
        "Wheels-Up (N-684AC)", operator=WHEELS_UP, category_label="Heavy jet"
    )
    assert label == "Heavy jet"


def test_percentile_interpolates() -> None:
    assert percentile([], 0.5) is None
    assert percentile([7], 0.25) == 7
    assert percentile([100, 200, 300, 400], 0.5) == 250
    assert percentile([100, 200, 300, 400], 0.25) == 175
    assert percentile([100, 200, 300, 401], 0.75) == 325  # 325.25


def test_default_range_is_twelve_calendar_months() -> None:
    rng = default_range(date(2026, 10, 15))
    assert rng.date_from == date(2025, 11, 1)
    assert rng.date_to == date(2026, 10, 15)
    assert default_range(date(2026, 1, 3)).date_from == date(2025, 2, 1)
