"""Money parsing: `$41,800.00`, `USD 41,800`, `41.8k`, `€32.500,00`, `C$`, `£`, `CHF`,
percentages (`7.5%`) and rates (`$4,950/hr x 3.2 hrs`)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class MoneyMatch:
    start: int
    end: int
    text: str
    amount_minor: int | None  # None for a pure percentage
    currency: str
    explicit_currency: bool  # a symbol or code was written (+3 confidence)
    percent: Decimal | None = None
    per_hour: bool = False
    quantity: Decimal | None = None  # hours in "x 3.2 hrs"


def parse_amount(text: str) -> Decimal | None:
    """Parse one number in US or EU grouping, with `k` shorthand."""
    raise NotImplementedError


def find_money(
    text: str, *, default_currency: str = "USD", has_anchor: bool = False
) -> list[MoneyMatch]:
    """All money values in `text`. Bare numbers >= 50 count only when `has_anchor`."""
    raise NotImplementedError
