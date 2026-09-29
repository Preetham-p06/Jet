"""Money parsing in the rules extractor (spec §3.3 step 3)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.extraction.rules.money import find_money, parse_amount


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("41,800.00", Decimal("41800.00")),
        ("41800", Decimal("41800")),
        ("38,900", Decimal("38900")),
        ("41.8k", Decimal("41800")),
        ("1.2K", Decimal("1200")),
        ("32.500,00", Decimal("32500.00")),
        ("32.500", Decimal("32500")),
        ("1.250.000", Decimal("1250000")),
        ("450,00", Decimal("450.00")),
        ("12.5", Decimal("12.5")),
        ("abc", None),
    ],
)
def test_parse_amount(text: str, value: Decimal | None) -> None:
    assert parse_amount(text) == value


@pytest.mark.parametrize(
    ("text", "minor", "currency"),
    [
        ("$41,800.00", 4_180_000, "USD"),
        ("USD 41,800", 4_180_000, "USD"),
        ("41,800 USD", 4_180_000, "USD"),
        ("US$ 5,000", 500_000, "USD"),
        ("€32.500,00", 3_250_000, "EUR"),
        ("EUR 32.950,00", 3_295_000, "EUR"),
        ("£9,999", 999_900, "GBP"),
        ("C$12,000", 1_200_000, "CAD"),
        ("CHF 18,400", 1_840_000, "CHF"),
        ("$10.60", 1_060, "USD"),
    ],
)
def test_explicit_currency(text: str, minor: int, currency: str) -> None:
    [money] = find_money(f"Charter price {text}")
    assert money.amount_minor == minor
    assert money.currency == currency
    assert money.explicit_currency


def test_bare_numbers_need_an_anchor_and_at_least_50() -> None:
    assert find_money("crew overnight 700 extra") == []
    [money] = find_money("crew overnight 700 extra", has_anchor=True)
    assert money.amount_minor == 70_000
    assert not money.explicit_currency
    assert find_money("positioning 45", has_anchor=True) == []


@pytest.mark.parametrize(
    "text",
    [
        "JS184 on 18 Oct 2026",
        "departs 09:00, 7 pax, 13 seats",
        "tail N684AC",
        "flight time 2h 58m",
        "10/18/2026",
        "3 nights",
    ],
)
def test_counts_dates_and_codes_are_not_money(text: str) -> None:
    assert find_money(text, has_anchor=True) == []


def test_k_shorthand_uses_the_default_currency() -> None:
    [money] = find_money("quote is 41.8k", has_anchor=True, default_currency="EUR")
    assert money.amount_minor == 4_180_000
    assert money.currency == "EUR"


def test_percentage() -> None:
    [money] = find_money("Federal excise tax (7.5%)")
    assert money.amount_minor is None
    assert money.percent == Decimal("7.5")


def test_hourly_rate_with_quantity() -> None:
    [money] = find_money("Rate: $4,950/hr x 3.2 hrs, 2 hr daily minimum")
    assert money.amount_minor == 495_000
    assert money.per_hour
    assert money.quantity == Decimal("3.2")
    [money] = find_money("$5,200 per hour")
    assert money.per_hour
    assert money.quantity is None


@pytest.mark.parametrize(
    ("text", "minor", "currency"),
    [
        ("Total: 32 500,00 €", 3_250_000, "EUR"),
        ("Total: 32 500,00 €", 3_250_000, "EUR"),  # narrow no-break space
        ("Total: 32 500,00 €", 3_250_000, "EUR"),  # thin space
        ("Total: 32 500 EUR", 3_250_000, "EUR"),  # no-break space
        ("Total: EUR 1 250 000", 125_000_000, "EUR"),
        ("Total: CHF 12'500", 1_250_000, "CHF"),
        ("Total: CHF 12’500.50", 1_250_050, "CHF"),
        ("Total: USD 41 800", 4_180_000, "USD"),
    ],
)
def test_space_and_apostrophe_thousands_separators(text: str, minor: int, currency: str) -> None:
    [money] = find_money(text, has_anchor=True)
    assert (money.amount_minor, money.currency) == (minor, currency)


def test_space_grouping_does_not_join_separate_numbers() -> None:
    # Mixed separators are two numbers, and bare space-grouped digits are not money.
    [money] = find_money("Charter $41,800 200 nm", has_anchor=True)
    assert money.amount_minor == 4_180_000
    assert find_money("legs 3 100", has_anchor=True) == []


@pytest.mark.parametrize(
    ("text", "minor"),
    [("$1.2M", 120_000_000), ("USD 1.25m", 125_000_000), ("€2M", 200_000_000)],
)
def test_million_suffix_with_a_currency(text: str, minor: int) -> None:
    [money] = find_money(f"Charter price {text}")
    assert money.amount_minor == minor


def test_million_suffix_without_a_currency_is_not_money() -> None:
    assert find_money("quote is 1.2M", has_anchor=True) == []
    assert find_money("flight time 2h 58m", has_anchor=True) == []


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("12'500", Decimal("12500")),
        ("32 500,00", Decimal("32500.00")),
        ("1.2M", Decimal("1200000")),
    ],
)
def test_parse_amount_grouping_and_million(text: str, value: Decimal) -> None:
    assert parse_amount(text) == value
