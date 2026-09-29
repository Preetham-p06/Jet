"""Money helpers. Amounts are integer cents; arithmetic uses Decimal, ROUND_HALF_UP."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Final

ONE: Final = Decimal("1")
HUNDRED: Final = Decimal("100")

# ISO 4217 currencies whose minor unit is not 1/100.
_MINOR_EXPONENTS: Final[dict[str, int]] = {"JPY": 0, "KRW": 0, "CLP": 0, "BHD": 3, "KWD": 3}


def to_decimal(value: Decimal | int | str) -> Decimal:
    if isinstance(value, float):  # pragma: no cover - guarded by typing
        raise TypeError("use Decimal or str for money, never float")
    return value if isinstance(value, Decimal) else Decimal(value)


def round_half_up(value: Decimal, quantum: Decimal = ONE) -> Decimal:
    return value.quantize(quantum, rounding=ROUND_HALF_UP)


def to_int_half_up(value: Decimal) -> int:
    return int(round_half_up(value))


def dollars_to_cents(amount: Decimal | int | str) -> int:
    """`Decimal("41800.005")` -> 4180001."""
    return to_int_half_up(to_decimal(amount) * HUNDRED)


def cents_to_dollars(cents: int) -> Decimal:
    return Decimal(cents) / HUNDRED


def minor_exponent(currency: str) -> int:
    return _MINOR_EXPONENTS.get(currency.upper(), 2)


def minor_to_decimal(amount_minor: int, currency: str) -> Decimal:
    """Minor units of `currency` to a major-unit Decimal (EUR 3250000 -> 32500.00)."""
    return Decimal(amount_minor).scaleb(-minor_exponent(currency))


def decimal_to_minor(amount: Decimal, currency: str) -> int:
    return to_int_half_up(amount.scaleb(minor_exponent(currency)))


def percent_of(base_cents: int, percent: Decimal) -> int:
    """`percent_of(4180000, Decimal("7.5"))` -> 313500."""
    return to_int_half_up(Decimal(base_cents) * percent / HUNDRED)


def apply_markup(cost_basis_cents: int, markup_pct: Decimal) -> int:
    """Client total in cents, rounded half-up to whole dollars (spec §6).

    Never below the cost basis: when half-up rounding would undercut it, the
    total rounds up to the next whole dollar instead.
    """
    dollars = cents_to_dollars(cost_basis_cents) * (ONE + markup_pct / HUNDRED)
    total = to_int_half_up(dollars) * 100
    if total < cost_basis_cents:
        total = -(-cost_basis_cents // 100) * 100
    return total


def format_usd(cents: int, *, show_cents: bool = False) -> str:
    """`4482000` -> "$44,820"; used in log and flag messages."""
    sign = "-" if cents < 0 else ""
    value = cents_to_dollars(abs(cents))
    if show_cents:
        return f"{sign}${value:,.2f}"
    return f"{sign}${round_half_up(value):,.0f}"
