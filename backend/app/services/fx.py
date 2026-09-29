"""Static FX from `data/fx_rates.json`: `{base: "USD", as_of, rates: {EUR: "1.08", ...}}`,
USD per unit, stored as Decimal strings. Each fee line converts separately."""

from __future__ import annotations

from pathlib import Path

from app.services.contracts import FxTable


class UnknownCurrency(ValueError):
    def __init__(self, currency: str) -> None:
        super().__init__(f"no FX rate for {currency}")
        self.currency = currency


def load_fx_table(path: Path | None = None) -> FxTable:
    """Load (and cache) the FX table; `path` defaults to `app/data/fx_rates.json`."""
    raise NotImplementedError


def to_usd_cents(amount_minor: int, currency: str, table: FxTable) -> int:
    """Convert minor units of `currency` to USD cents, ROUND_HALF_UP.

    Raises `UnknownCurrency` when the table has no rate.
    """
    raise NotImplementedError
