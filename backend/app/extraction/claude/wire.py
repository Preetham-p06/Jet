"""Wire schema for structured outputs: flat, every field required but nullable,
no numeric or length constraints (the API does not support them), no dicts.

`to_extraction_result` clamps confidence to 0..100, converts amounts to minor
units and maps unknown fee categories to `other`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from app.extraction.types import ExtractionResult, FieldKey

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


class WireField(BaseModel):
    key: FieldKey
    text_value: str | None
    number_value: float | None
    bool_value: bool | None
    currency: str | None
    confidence: int
    snippet: str
    page: int | None


class WireFee(BaseModel):
    category: WireFeeCategory
    label: str
    status: Literal["stated", "included", "estimated", "not_stated", "waived"]
    amount: float | None
    currency: str | None
    unit: Literal["flat", "per_hour", "per_night", "per_leg", "per_pax", "percent"]
    quantity: float | None
    percent: float | None
    explicitly_extra: bool
    hedged: bool
    confidence: int
    snippet: str
    page: int | None


class ClaudeQuoteExtraction(BaseModel):
    is_quote: bool
    intent: Literal["quote", "revision", "decline", "other"]
    fields: list[WireField]
    fees: list[WireFee]
    notes: list[str]


def to_extraction_result(
    wire: ClaudeQuoteExtraction,
    *,
    extractor_version: str,
    model: str,
    default_currency: str,
    usage: dict[str, int] | None,
) -> ExtractionResult:
    raise NotImplementedError
