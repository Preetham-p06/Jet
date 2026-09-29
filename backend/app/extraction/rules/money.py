"""Money parsing: `$41,800.00`, `USD 41,800`, `41.8k`, `€32.500,00`, `C$`, `£`, `CHF`,
percentages (`7.5%`) and rates (`$4,950/hr x 3.2 hrs`)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Final


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


BARE_MINIMUM: Final = Decimal(50)

# Longest first so "US$" beats "$" and "C$" beats "$".
SYMBOLS: Final[dict[str, str]] = {
    "US$": "USD",
    "CA$": "CAD",
    "C$": "CAD",
    "A$": "AUD",
    "$": "USD",
    "€": "EUR",
    "£": "GBP",
}
CODES: Final = ("USD", "EUR", "GBP", "CAD", "CHF", "AUD")

_NUMBER: Final = r"\d{1,3}(?:[,.]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?"
_PREFIX: Final = (
    r"(?P<prefix>US\$|CA\$|C\$|A\$|\$|€|£|(?<![A-Za-z])(?:USD|EUR|GBP|CAD|CHF|AUD)(?![A-Za-z]))"
)
_SUFFIX: Final = r"(?P<suffix>€|£|(?<![A-Za-z])(?:USD|EUR|GBP|CAD|CHF|AUD)(?![A-Za-z]))"
_K: Final = r"(?P<k>\s?[kK](?![A-Za-z]))"
_PER_HOUR: Final = (
    r"(?P<hour>\s*(?:/\s*(?:hr|hour|h)\b|per\s+(?:flight\s+|block\s+)?hour\b|an\s+hour\b))"
)
_QTY: Final = r"(?P<qty>\s*[x×*]\s*(?P<qn>\d+(?:\.\d+)?)\s*(?:hrs?|hours?|h)\b\.?)"

MONEY_RE: Final = re.compile(
    rf"(?<![\w.,/:-]){_PREFIX}?\s?(?P<num>{_NUMBER}){_K}?(?:\s?{_SUFFIX})?"
    rf"(?P<pct>\s?%)?{_PER_HOUR}?{_QTY}?"
)

# Bare numbers followed by these are counts, durations or dates, not money.
_NOT_MONEY_AFTER: Final = re.compile(
    r"\s*(?:seats?|pax|passengers?|people|persons?|guests?|hrs?\b|hours?|h\b|m\b|mins?\b|minutes?|"
    r"nm\b|miles?|lbs?\b|kg\b|gal|gallons?|nights?|days?|legs?|am\b|pm\b|[:/]\d|"
    r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b|st\b|nd\b|rd\b|th\b|[A-Za-z]\d)",
    re.IGNORECASE,
)
_NOT_MONEY_BEFORE: Final = re.compile(
    r"(?:\bno\.?|#|\bflight|\bref|\bJS|\btail|\broom|\bgate|\bfl|\bmay|\d\s*h|"
    r"\b(?:jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?)\s*$",
    re.IGNORECASE,
)
_YEAR: Final = re.compile(r"^(?:19|20)\d\d$")


def parse_amount(text: str) -> Decimal | None:
    """Parse one number in US or EU grouping, with `k` shorthand."""
    raw = text.strip().replace(" ", "")
    multiplier = Decimal(1)
    if raw[-1:] in ("k", "K"):
        multiplier = Decimal(1000)
        raw = raw[:-1]
    if not raw or not re.fullmatch(r"[\d.,]+", raw) or not raw[0].isdigit():
        return None
    if "," in raw and "." in raw:
        # Whichever separator comes last is the decimal point.
        if raw.rfind(",") > raw.rfind("."):
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", "")
    elif "," in raw:
        groups = raw.split(",")
        if len(groups) == 2 and len(groups[1]) in (1, 2):
            raw = raw.replace(",", ".")  # EU decimal: "12,50"
        else:
            raw = raw.replace(",", "")
    elif "." in raw:
        groups = raw.split(".")
        # "32.500" / "1.250.000": EU thousands grouping (three digits after each dot).
        if len(groups) > 2 or (len(groups) == 2 and len(groups[1]) == 3 and multiplier == 1):
            if all(len(g) == 3 for g in groups[1:]) and 1 <= len(groups[0]) <= 3:
                raw = raw.replace(".", "")
            else:
                return None
    try:
        value = Decimal(raw) * multiplier
    except InvalidOperation:
        return None
    return value


def to_minor(value: Decimal) -> int:
    return int((value * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _currency_of(token: str | None) -> str | None:
    if not token:
        return None
    return SYMBOLS.get(token) or (token.upper() if token.upper() in CODES else None)


def find_money(
    text: str, *, default_currency: str = "USD", has_anchor: bool = False
) -> list[MoneyMatch]:
    """All money values in `text`. Bare numbers >= 50 count only when `has_anchor`."""
    found: list[MoneyMatch] = []
    for m in MONEY_RE.finditer(text):
        num = m.group("num")
        k = m.group("k")
        amount = parse_amount(num + ("k" if k else ""))
        if amount is None:
            continue
        currency = _currency_of(m.group("prefix")) or _currency_of(m.group("suffix"))
        explicit = currency is not None
        end = m.end()
        # Trim trailing whitespace captured by optional groups.
        while end > m.start() and text[end - 1].isspace():
            end -= 1
        start = m.start()
        if m.group("pct"):
            if m.group("prefix"):
                continue
            found.append(
                MoneyMatch(
                    start=start,
                    end=m.start("pct") + len(m.group("pct")),
                    text=text[start : m.start("pct") + len(m.group("pct"))],
                    amount_minor=None,
                    currency=currency or default_currency,
                    explicit_currency=False,
                    percent=amount,
                )
            )
            continue
        per_hour = bool(m.group("hour"))
        quantity = Decimal(m.group("qn")) if m.group("qn") else None
        if not explicit and not k:
            if not has_anchor or amount < BARE_MINIMUM:
                continue
            if _YEAR.match(num) or _NOT_MONEY_AFTER.match(text, m.end("num")):
                continue
            if _NOT_MONEY_BEFORE.search(text[: m.start()]):
                continue
        elif not explicit and k and not has_anchor:
            continue
        found.append(
            MoneyMatch(
                start=start,
                end=end,
                text=text[start:end],
                amount_minor=to_minor(amount),
                currency=currency or default_currency,
                explicit_currency=explicit,
                per_hour=per_hour,
                quantity=quantity,
            )
        )
    return found
