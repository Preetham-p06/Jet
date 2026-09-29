"""The extraction contract shared by every extractor and the pipeline.

Frozen at foundation (design spec §3.1). Changes go through the lead; see
`backend/AGENTS.md`.

Money is carried in *minor units of the original currency* (`Money`);
conversion to USD cents happens later in normalization.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Final, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.enums import FeeCategory, FeeUnit

__all__ = [
    "FIELD_TYPES",
    "MAX_SNIPPET_CHARS",
    "Evidence",
    "ExtractedAmountStatus",
    "ExtractedFee",
    "ExtractedField",
    "ExtractionIntent",
    "ExtractionResult",
    "ExtractorName",
    "FeeCategory",
    "FeeUnit",
    "FieldKey",
    "Money",
]

MAX_SNIPPET_CHARS: Final = 300

FieldKey = Literal[
    "operator_name",
    "aircraft_model",
    "aircraft_category",
    "tail_number",
    "seats",
    "wifi",
    "departure_airport",
    "arrival_airport",
    "departure_local",
    "flight_time_minutes",
    "pax",
    "availability",
    "currency",
    "headline_price",
    "hourly_rate",
    "billable_hours",
    "daily_minimum_hours",
    "stated_total",
    "all_in",
    "valid_until",
]
FIELD_KEYS: Final[tuple[str, ...]] = get_args(FieldKey)

# The status an extractor may assign. `not_applicable` is a review outcome only.
ExtractedAmountStatus = Literal["stated", "included", "estimated", "not_stated", "waived"]
ExtractionIntent = Literal["quote", "revision", "decline", "other"]
ExtractorName = Literal["rules", "claude"]


class Money(BaseModel):
    """An amount in minor units (cents) of `currency` (ISO 4217, upper case)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    amount_minor: int
    currency: str = Field(pattern=r"^[A-Z]{3}$")


# Python type of `ExtractedField.value` per key. String-typed values use these
# formats: departure_local "YYYY-MM-DDTHH:MM" (naive, local to the origin),
# valid_until ISO date or datetime, airports ICAO or IATA as written,
# aircraft_category an `AircraftCategory` value, availability an
# `Availability` value, currency ISO 4217.
FIELD_TYPES: Final[dict[str, type]] = {
    "operator_name": str,
    "aircraft_model": str,
    "aircraft_category": str,
    "tail_number": str,
    "seats": int,
    "wifi": bool,
    "departure_airport": str,
    "arrival_airport": str,
    "departure_local": str,
    "flight_time_minutes": int,
    "pax": int,
    "availability": str,
    "currency": str,
    "headline_price": Money,
    "hourly_rate": Money,
    "billable_hours": float,
    "daily_minimum_hours": float,
    "stated_total": Money,
    "all_in": bool,
    "valid_until": str,
}


class Evidence(BaseModel):
    """Where a value came from. Snippets are verbatim and truncated to 300 chars."""

    snippet: str
    page: int | None = Field(default=None, ge=1)  # 1-based for PDFs, None for text sources
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)
    verified: bool = False  # set by provenance.verify()

    @field_validator("snippet", mode="before")
    @classmethod
    def _truncate(cls, value: Any) -> Any:
        if isinstance(value, str) and len(value) > MAX_SNIPPET_CHARS:
            return value[:MAX_SNIPPET_CHARS]
        return value


class ExtractedField(BaseModel):
    key: FieldKey
    value: str | int | float | bool | Money | None
    confidence: int = Field(ge=0, le=100)
    evidence: Evidence
    sequence: int = 0  # order within the document (chat messages, quoted email text)

    @model_validator(mode="after")
    def _check_value_type(self) -> ExtractedField:
        if self.value is None:
            return self
        expected = FIELD_TYPES[self.key]
        value = self.value
        if expected is float and isinstance(value, int) and not isinstance(value, bool):
            self.value = float(value)
            return self
        # bool is an int subclass; reject it where an int is expected and vice versa.
        is_bool = isinstance(value, bool)
        if (expected is bool) != is_bool or not isinstance(value, expected):
            raise ValueError(f"{self.key} expects {expected.__name__}, got {type(value).__name__}")
        return self


class ExtractedFee(BaseModel):
    category: FeeCategory
    label: str  # as written in the document
    status: ExtractedAmountStatus
    amount: Money | None = None
    unit: FeeUnit = FeeUnit.FLAT
    quantity: Decimal | None = None
    percent: Decimal | None = None  # 7.5 means 7.5 %
    explicitly_extra: bool = False
    hedged: bool = False
    confidence: int = Field(ge=0, le=100)
    evidence: Evidence
    sequence: int = 0


class ExtractionResult(BaseModel):
    extractor: ExtractorName
    extractor_version: str
    model: str | None = None
    intent: ExtractionIntent
    fields: list[ExtractedField]
    fees: list[ExtractedFee]
    notes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    usage: dict[str, int] | None = None
