"""Trips, legs, RFQ tracking (trip operators) and the processing log."""

from __future__ import annotations

import uuid
from functools import lru_cache
from typing import Any
from zoneinfo import available_timezones

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    NaiveDatetime,
    field_validator,
)

from app.models.enums import (
    AircraftCategory,
    EventLevel,
    ProcessingStep,
    RequestChannel,
    TripOperatorStatus,
    TripStatus,
    TripType,
)
from app.schemas.common import ICAO, APIModel, Cents, ORMModel
from app.schemas.operator import OperatorCreate

REFERENCE_PATTERN = r"^[A-Z0-9][A-Z0-9-]{1,31}$"


class TripPreferences(BaseModel):
    """Stored as `trips.preferences` JSON."""

    model_config = ConfigDict(extra="forbid")

    wifi_required: bool = False
    preferred_categories: list[AircraftCategory] = Field(default_factory=list)
    catering_required: bool = False
    max_budget_cents: Cents | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=2000)


class LegIn(APIModel):
    origin_icao: ICAO
    destination_icao: ICAO
    depart_local: NaiveDatetime = Field(description="Wall-clock time at the origin, no offset")
    depart_tz: str | None = Field(
        default=None, description="IANA zone; defaults to the origin airport's zone"
    )

    @field_validator("origin_icao", "destination_icao", mode="before")
    @classmethod
    def _upper(cls, value: Any) -> Any:
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("depart_tz")
    @classmethod
    def _known_zone(cls, value: str | None) -> str | None:
        if value is not None and value not in _zones():
            raise ValueError(f"unknown time zone {value!r}")
        return value


@lru_cache(maxsize=1)
def _zones() -> frozenset[str]:
    return frozenset(available_timezones())


class LegOut(ORMModel):
    id: uuid.UUID
    seq: int
    origin_icao: str
    destination_icao: str
    depart_local: NaiveDatetime
    depart_tz: str


class TripCreate(APIModel):
    reference: str | None = Field(
        default=None, pattern=REFERENCE_PATTERN, description="Auto-generated as JS### if omitted"
    )
    trip_type: TripType = TripType.ONE_WAY
    pax: int = Field(ge=1, le=500)
    client_name: str | None = Field(default=None, max_length=200)
    client_email: EmailStr | None = None
    preferences: TripPreferences = Field(default_factory=TripPreferences)
    notes: str | None = Field(default=None, max_length=5000)
    legs: list[LegIn] = Field(min_length=1, max_length=20)

    @field_validator("reference", mode="before")
    @classmethod
    def _upper(cls, value: Any) -> Any:
        return value.strip().upper() if isinstance(value, str) else value


class TripPatch(APIModel):
    """Omitted fields are unchanged. `legs`, when given, replaces every leg."""

    reference: str | None = Field(default=None, pattern=REFERENCE_PATTERN)
    status: TripStatus | None = None
    trip_type: TripType | None = None
    pax: int | None = Field(default=None, ge=1, le=500)
    client_name: str | None = Field(default=None, max_length=200)
    client_email: EmailStr | None = None
    preferences: TripPreferences | None = None
    notes: str | None = Field(default=None, max_length=5000)
    legs: list[LegIn] | None = Field(default=None, min_length=1, max_length=20)

    @field_validator("reference", mode="before")
    @classmethod
    def _upper(cls, value: Any) -> Any:
        return value.strip().upper() if isinstance(value, str) else value


class RecommendationSummary(BaseModel):
    quote_id: uuid.UUID
    operator_name: str
    fit_score: int | None
    known_total_cents: Cents | None
    is_fully_priced: bool


class TripCounts(BaseModel):
    operators_requested: int = 0
    operators_quoted: int = 0
    operators_declined: int = 0
    quotes: int = 0
    documents: int = 0
    open_blocking_flags: int = 0
    pending_review: int = 0


class TripSummaryOut(ORMModel):
    id: uuid.UUID
    reference: str
    status: TripStatus
    trip_type: TripType
    pax: int
    client_name: str | None
    legs: list[LegOut]
    quote_count: int = 0
    open_flag_count: int = 0
    recommended_quote_id: uuid.UUID | None = None
    recommended_total_cents: Cents | None = None
    created_at: AwareDatetime
    updated_at: AwareDatetime


class TripOut(TripSummaryOut):
    client_email: str | None
    preferences: TripPreferences
    notes: str | None
    created_by_id: uuid.UUID | None
    booked_quote_id: uuid.UUID | None
    booked_at: AwareDatetime | None
    counts: TripCounts = Field(default_factory=TripCounts)
    recommendation: RecommendationSummary | None = None


class ProcessingEventOut(ORMModel):
    id: uuid.UUID
    trip_id: uuid.UUID
    quote_id: uuid.UUID | None
    source_document_id: uuid.UUID | None
    step: ProcessingStep
    level: EventLevel
    message: str
    data: dict[str, Any] | None
    created_at: AwareDatetime


# --------------------------------------------------------------------------- RFQ tracking


class TripOperatorOut(ORMModel):
    id: uuid.UUID
    trip_id: uuid.UUID
    operator_id: uuid.UUID
    operator_name: str
    status: TripOperatorStatus
    channel: RequestChannel
    requested_at: AwareDatetime
    responded_at: AwareDatetime | None
    response_minutes: int | None = Field(
        default=None, description="responded_at - requested_at, in whole minutes"
    )
    declined_reason: str | None
    notes: str | None
    quote_id: uuid.UUID | None = None
    created_at: AwareDatetime


class TripOperatorsAdd(APIModel):
    """Bulk add: existing operators by id and/or brand-new operators."""

    operator_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)
    new_operators: list[OperatorCreate] = Field(default_factory=list, max_length=50)
    channel: RequestChannel = RequestChannel.EMAIL
    requested_at: AwareDatetime | None = Field(default=None, description="Defaults to now")


class TripOperatorPatch(APIModel):
    status: TripOperatorStatus | None = None
    channel: RequestChannel | None = None
    requested_at: AwareDatetime | None = None
    responded_at: AwareDatetime | None = None
    declined_reason: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=5000)
