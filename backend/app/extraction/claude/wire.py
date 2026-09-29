"""Wire schema for structured outputs: flat, every field required but nullable,
no numeric or length constraints (the API does not support them), no dicts.

`to_extraction_result` clamps confidence to 0..100, converts amounts to minor
units and maps unknown fee categories to `other`.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from typing import Any, Final, Literal

import anthropic
from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from app.extraction.types import (
    FIELD_TYPES,
    Evidence,
    ExtractedFee,
    ExtractedField,
    ExtractionResult,
    FieldKey,
    Money,
)
from app.models.enums import AircraftCategory, Availability, FeeCategory, FeeUnit
from app.services.money import decimal_to_minor

WireFeeCategory = Literal[
    "positioning",
    "ramp_handling",
    "fuel_surcharge",
    "catering",
    "crew_overnight",
    "crew",
    "overnight",
    "landing",
    "deicing",
    "international",
    "fet",
    "segment_fees",
    "taxes",
    "wifi_fee",
    "other",
]

_CURRENCY_RE: Final = re.compile(r"^[A-Z]{3}$")
_UPPER_KEYS: Final = frozenset({"tail_number", "departure_airport", "arrival_airport"})


class WireField(BaseModel):
    key: FieldKey
    text_value: str | None = Field(
        description="Value for text, code, date and enum fields; null otherwise."
    )
    number_value: float | None = Field(
        description="Value for numeric and money fields, in major units (41800.00); null otherwise."
    )
    bool_value: bool | None = Field(description="Value for yes/no fields; null otherwise.")
    currency: str | None = Field(description="ISO 4217 code for money fields; null otherwise.")
    confidence: int = Field(description="0-100, per the confidence rubric.")
    snippet: str = Field(description="Verbatim text from the document supporting the value.")
    page: int | None = Field(description="1-based PDF page of the snippet; null for text sources.")
    sequence: int | None = Field(
        description="Message number the value came from, for chats and email threads; else null."
    )


class WireFee(BaseModel):
    category: WireFeeCategory
    label: str = Field(description="The charge's name as written in the document.")
    status: Literal["stated", "included", "estimated", "not_stated", "waived"]
    amount: float | None = Field(description="Amount in major units, or null when none is written.")
    currency: str | None = Field(description="ISO 4217 code of the amount, or null.")
    unit: Literal["flat", "per_hour", "per_night", "per_leg", "per_pax", "percent"]
    quantity: float | None = Field(description="Hours, nights, legs or pax the unit applies to.")
    percent: float | None = Field(description="Percentage for percent fees: 7.5 means 7.5 %.")
    explicitly_extra: bool
    hedged: bool
    confidence: int = Field(description="0-100, per the confidence rubric.")
    snippet: str = Field(description="Verbatim text from the document supporting the fee.")
    page: int | None = Field(description="1-based PDF page of the snippet; null for text sources.")
    sequence: int | None = Field(
        description="Message number the fee came from, for chats and email threads; else null."
    )


class ClaudeQuoteExtraction(BaseModel):
    is_quote: bool
    intent: Literal["quote", "revision", "decline", "other"]
    fields: list[WireField]
    fees: list[WireFee]
    notes: list[str]


@lru_cache(maxsize=1)
def wire_json_schema() -> dict[str, Any]:
    """The JSON schema sent as `output_config.format.schema`.

    Built exactly as the SDK builds it for `output_format=` (a `TypeAdapter`
    schema passed through `anthropic.transform_schema`).
    """
    return anthropic.transform_schema(TypeAdapter(ClaudeQuoteExtraction).json_schema())


def output_format_param() -> dict[str, Any]:
    return {"type": "json_schema", "schema": wire_json_schema()}


def parse_wire(text: str) -> ClaudeQuoteExtraction | None:
    """Validate the model's JSON text; None when it does not fit the schema."""
    if not text.strip():
        return None
    try:
        return ClaudeQuoteExtraction.model_validate_json(text)
    except ValidationError:
        return None


# --- mapping --------------------------------------------------------------------------


def _clamp(confidence: int) -> int:
    return max(0, min(100, int(confidence)))


def _page(page: int | None) -> int | None:
    return page if page is not None and page >= 1 else None


def _currency(raw: str | None, default: str) -> str:
    code = (raw or "").strip().upper()
    return code if _CURRENCY_RE.match(code) else default


def _decimal(value: float | None) -> Decimal | None:
    if value is None:
        return None
    try:
        result = Decimal(repr(value))
    except InvalidOperation:
        return None
    return result if result.is_finite() else None


def _money(amount: float | None, currency: str | None, default: str) -> Money | None:
    dec = _decimal(amount)
    if dec is None:
        return None
    code = _currency(currency, default)
    return Money(amount_minor=decimal_to_minor(dec, code), currency=code)


def _enum_value(raw: str | None, allowed: set[str]) -> str | None:
    if raw is None:
        return None
    norm = re.sub(r"[\s\-]+", "_", raw.strip().lower())
    return norm if norm in allowed else None


_AIRCRAFT_CATEGORIES: Final = {c.value for c in AircraftCategory}
_AVAILABILITIES: Final = {a.value for a in Availability}
_FEE_CATEGORIES: Final = {c.value for c in FeeCategory}
_FEE_UNITS: Final = {u.value for u in FeeUnit}


def _field_value(wire: WireField, default_currency: str) -> Any:
    """The typed value for `wire.key`, or None when absent or unusable."""
    expected = FIELD_TYPES[wire.key]
    text = wire.text_value.strip() if wire.text_value is not None else None
    if expected is Money:
        return _money(wire.number_value, wire.currency, default_currency)
    if expected is bool:
        return wire.bool_value
    if expected is int:
        if wire.number_value is not None:
            return round(wire.number_value)
        if text and text.lstrip("-").isdigit():
            return int(text)
        return None
    if expected is float:
        if wire.number_value is not None:
            return float(wire.number_value)
        try:
            return float(text) if text else None
        except ValueError:
            return None
    # str-typed keys
    if not text:
        return None
    if wire.key == "aircraft_category":
        return _enum_value(text, _AIRCRAFT_CATEGORIES)
    if wire.key == "availability":
        return _enum_value(text, _AVAILABILITIES)
    if wire.key == "currency":
        code = text.upper()
        return code if _CURRENCY_RE.match(code) else None
    if wire.key in _UPPER_KEYS:
        return text.upper()
    return text


def _map_field(
    wire: WireField, default_currency: str, warnings: list[str]
) -> ExtractedField | None:
    value = _field_value(wire, default_currency)
    if value is None:
        if wire.text_value or wire.number_value is not None or wire.bool_value is not None:
            warnings.append(f"claude: dropped unusable value for {wire.key}")
        return None
    try:
        return ExtractedField(
            key=wire.key,
            value=value,
            confidence=_clamp(wire.confidence),
            evidence=Evidence(snippet=wire.snippet, page=_page(wire.page)),
            sequence=wire.sequence or 0,
        )
    except ValidationError:
        warnings.append(f"claude: dropped invalid value for {wire.key}")
        return None


def _map_fee(wire: WireFee, default_currency: str) -> ExtractedFee:
    category = FeeCategory(wire.category if wire.category in _FEE_CATEGORIES else "other")
    unit = FeeUnit(wire.unit if wire.unit in _FEE_UNITS else "flat")
    return ExtractedFee(
        category=category,
        label=wire.label.strip() or category.value.replace("_", " "),
        status=wire.status,
        amount=_money(wire.amount, wire.currency, default_currency),
        unit=unit,
        quantity=_decimal(wire.quantity),
        percent=_decimal(wire.percent),
        explicitly_extra=wire.explicitly_extra,
        hedged=wire.hedged,
        confidence=_clamp(wire.confidence),
        evidence=Evidence(snippet=wire.snippet, page=_page(wire.page)),
        sequence=wire.sequence or 0,
    )


def to_extraction_result(
    wire: ClaudeQuoteExtraction,
    *,
    extractor_version: str,
    model: str,
    default_currency: str,
    usage: dict[str, int] | None,
) -> ExtractionResult:
    warnings: list[str] = []
    # A currency stated once in the document is the default for bare amounts.
    stated = [f.text_value for f in wire.fields if f.key == "currency" and f.text_value]
    currency = _currency(stated[0] if stated else None, _currency(default_currency, "USD"))

    fields = [f for w in wire.fields if (f := _map_field(w, currency, warnings)) is not None]
    fees = [_map_fee(w, currency) for w in wire.fees]
    intent = wire.intent
    if not wire.is_quote and intent in ("quote", "revision"):
        intent = "other"
        warnings.append("claude: document is not a quote")
    return ExtractionResult(
        extractor="claude",
        extractor_version=extractor_version,
        model=model,
        intent=intent,
        fields=fields,
        fees=fees,
        notes=[n for n in wire.notes if n.strip()],
        warnings=warnings,
        usage=usage,
    )
