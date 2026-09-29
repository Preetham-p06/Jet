"""Quotes, quote fields, fee lines, comparison and the review queue."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, Field, NaiveDatetime

from app.models.enums import (
    AircraftCategory,
    AmountStatus,
    Availability,
    DocumentChannel,
    DocumentKind,
    ExtractorKind,
    FeeCategory,
    FeeUnit,
    FieldGroup,
    FieldStatus,
    IncludedBy,
    PricingBasis,
    QuoteStatus,
    ValueType,
)
from app.schemas.common import APIModel, Cents, DecimalNumber, ORMModel
from app.schemas.field_values import FieldValue
from app.schemas.flag import FlagOut
from app.schemas.recommendation import ReasonOut, ScoreBreakdownOut


class SourceRefOut(BaseModel):
    """A pointer to where a value came from, for "p.2 · atlas_quote_01.pdf" links."""

    document_id: uuid.UUID
    kind: DocumentKind
    channel: DocumentChannel
    original_filename: str | None
    page: int | None = None
    received_at: AwareDatetime | None = None


class FieldOut(ORMModel):
    id: uuid.UUID
    quote_id: uuid.UUID
    source_document_id: uuid.UUID | None
    key: str
    group: FieldGroup
    label: str | None
    value_type: ValueType
    original_value: FieldValue | None
    current_value: FieldValue | None
    confidence: int
    extractor: ExtractorKind
    snippet: str | None
    page: int | None
    char_start: int | None
    char_end: int | None
    snippet_verified: bool
    status: FieldStatus
    locked: bool
    reviewed_by_id: uuid.UUID | None
    reviewed_at: AwareDatetime | None
    review_note: str | None
    is_current: bool
    superseded_by_id: uuid.UUID | None
    corroborating_source_ids: list[uuid.UUID]
    version: int = Field(description="Send back on review actions; 409 when stale")
    created_at: AwareDatetime
    updated_at: AwareDatetime


class FieldVersionIn(APIModel):
    """Body of verify and reset."""

    version: int = Field(ge=1)


class FieldAcceptIn(APIModel):
    version: int = Field(ge=1)
    note: str | None = Field(default=None, max_length=1000)


class FieldEditIn(APIModel):
    """`value` must match the field's `value_type` (see `schemas.field_values`)."""

    version: int = Field(ge=1)
    value: Any
    note: str | None = Field(default=None, max_length=1000)


class ManualFieldIn(APIModel):
    """Add a value by hand (status edited, locked). Fee keys are `fee.<category>`."""

    key: str = Field(min_length=1, max_length=80, examples=["fee.fuel_surcharge", "seats"])
    value: Any
    label: str | None = Field(default=None, max_length=200)
    note: str | None = Field(default=None, max_length=1000)


class FeeLineOut(ORMModel):
    id: uuid.UUID
    field_id: uuid.UUID | None
    category: FeeCategory
    label: str
    amount_status: AmountStatus
    included_by: IncludedBy | None
    amount_cents: Cents | None
    original_amount_minor: int | None
    original_currency: str | None
    unit: FeeUnit
    quantity: DecimalNumber | None
    percent: DecimalNumber | None
    explicitly_extra: bool
    counts_in_known: bool
    counts_in_upper: bool
    estimate_cents: Cents | None
    estimate_basis: str | None
    confidence: int | None
    review_status: FieldStatus | None
    source_document_id: uuid.UUID | None
    page: int | None
    sort_order: int


class QuoteSummaryOut(ORMModel):
    id: uuid.UUID
    trip_id: uuid.UUID
    operator_id: uuid.UUID
    operator_name: str
    status: QuoteStatus
    original_currency: str
    pricing_basis: PricingBasis
    headline_cents: Cents | None
    known_total_cents: Cents | None = Field(description="Lower bound of the true cost")
    upper_total_cents: Cents | None
    is_fully_priced: bool = Field(description="False: show known total with a '+'")
    open_blocking_flags: int
    open_info_flags: int
    pending_review_count: int
    quote_confidence: int | None
    confidence_mean: float | None
    fit_score: int | None
    is_recommended: bool
    eligible_for_proposal: bool
    eligibility_reasons: list[ReasonOut]
    aircraft_model: str | None
    aircraft_category: AircraftCategory | None
    tail_number: str | None
    seats: int | None
    wifi: bool | None
    flight_time_minutes: int | None
    departure_local: NaiveDatetime | None
    availability: Availability | None
    first_received_at: AwareDatetime | None
    last_received_at: AwareDatetime | None
    computed_at: AwareDatetime | None
    created_at: AwareDatetime


class QuoteDetailOut(QuoteSummaryOut):
    fields: list[FieldOut]
    fee_lines: list[FeeLineOut]
    flags: list[FlagOut]
    sources: list[SourceRefOut]
    fit_breakdown: ScoreBreakdownOut | None


class QuotePatch(APIModel):
    status: Literal[QuoteStatus.ACTIVE, QuoteStatus.WITHDRAWN, QuoteStatus.REJECTED] | None = None
    operator_id: uuid.UUID | None = None


# --------------------------------------------------------------------------- comparison


class FeeColumnOut(BaseModel):
    category: FeeCategory
    label: str


class ComparisonCellOut(BaseModel):
    """One fee category of one quote; several lines in a category are summed."""

    category: FeeCategory
    amount_status: AmountStatus | None = Field(description="None: the quote has no such line")
    amount_cents: Cents | None
    estimate_cents: Cents | None
    included_by: IncludedBy | None
    confidence: int | None
    review_status: FieldStatus | None
    field_id: uuid.UUID | None
    source: SourceRefOut | None
    line_count: int


class ComparisonRowOut(BaseModel):
    quote: QuoteSummaryOut
    fees: list[ComparisonCellOut] = Field(description="One cell per fee column, same order")
    added_charges_cents: Cents | None
    open_flags: list[FlagOut]


class ComparisonOut(BaseModel):
    trip_id: uuid.UUID
    review_threshold: int
    fee_columns: list[FeeColumnOut]
    rows: list[ComparisonRowOut]
    recommended_quote_id: uuid.UUID | None


# --------------------------------------------------------------------------- review queue


class ReviewQueueItemOut(BaseModel):
    """A field below threshold that is unlocked, or an open blocking flag."""

    kind: Literal["field", "flag"]
    quote_id: uuid.UUID
    operator_name: str
    money_impact_cents: Cents = Field(description="Sort key: the amount at stake")
    field: FieldOut | None = None
    flag: FlagOut | None = None
    source: SourceRefOut | None = None
