"""Static FX from `data/fx_rates.json`: `{base: "USD", as_of, rates: {EUR: "1.08", ...}}`,
USD per unit, stored as Decimal strings. Each fee line converts separately."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType

from app.services.contracts import FxTable
from app.services.money import HUNDRED, minor_to_decimal, to_int_half_up

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "fx_rates.json"


class UnknownCurrency(ValueError):
    def __init__(self, currency: str) -> None:
        super().__init__(f"no FX rate for {currency}")
        self.currency = currency


@lru_cache(maxsize=8)
def _load(path: Path) -> FxTable:
    raw = json.loads(path.read_text(encoding="utf-8"))
    rates = {str(k).upper(): Decimal(str(v)) for k, v in raw["rates"].items()}
    return FxTable(
        as_of=date.fromisoformat(raw["as_of"]),
        rates=MappingProxyType(rates),
        base=str(raw.get("base", "USD")).upper(),
    )


def load_fx_table(path: Path | None = None) -> FxTable:
    """Load (and cache) the FX table; `path` defaults to `app/data/fx_rates.json`."""
    return _load((path or DEFAULT_PATH).resolve())


def rate_for(currency: str, table: FxTable) -> Decimal:
    """USD per one unit of `currency`; raises `UnknownCurrency`."""
    ccy = currency.upper()
    if ccy == table.base:
        return Decimal(1)
    try:
        return table.rates[ccy]
    except KeyError:
        raise UnknownCurrency(ccy) from None


def to_usd_cents(amount_minor: int, currency: str, table: FxTable) -> int:
    """Convert minor units of `currency` to USD cents, ROUND_HALF_UP.

    Raises `UnknownCurrency` when the table has no rate.
    """
    rate = rate_for(currency, table)
    if currency.upper() == table.base:
        return amount_minor
    return to_int_half_up(minor_to_decimal(amount_minor, currency) * rate * HUNDRED)
