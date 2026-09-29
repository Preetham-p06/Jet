"""Vocabulary, airport lookup and health payloads, plus the display labels."""

from __future__ import annotations

from typing import Final, Literal

from pydantic import BaseModel, Field

from app.models.enums import (
    AircraftCategory,
    AmountStatus,
    FeeCategory,
    FieldStatus,
    FlagResolution,
    FlagSeverity,
    FlagType,
    ProposalStatus,
    QuoteStatus,
    Role,
    TripOperatorStatus,
    TripStatus,
)

# Labels match the landing page vocabulary.
FEE_CATEGORY_LABELS: Final[dict[FeeCategory, str]] = {
    FeeCategory.POSITIONING: "Positioning",
    FeeCategory.RAMP_HANDLING: "Ramp / handling",
    FeeCategory.FUEL_SURCHARGE: "Fuel surcharge",
    FeeCategory.CATERING: "Catering",
    FeeCategory.CREW_OVERNIGHT: "Crew overnight",
    FeeCategory.CREW: "Crew",
    FeeCategory.OVERNIGHT: "Aircraft overnight",
    FeeCategory.LANDING: "Landing",
    FeeCategory.DEICING: "De-icing",
    FeeCategory.INTERNATIONAL: "International fees",
    FeeCategory.FET: "Federal excise tax",
    FeeCategory.SEGMENT_FEES: "Segment fees",
    FeeCategory.TAXES: "Taxes",
    FeeCategory.WIFI_FEE: "Wi-Fi fee",
    FeeCategory.OTHER: "Other",
}

AIRCRAFT_CATEGORY_LABELS: Final[dict[AircraftCategory, str]] = {
    AircraftCategory.TURBOPROP: "Turboprop",
    AircraftCategory.VERY_LIGHT: "Very light",
    AircraftCategory.LIGHT: "Light",
    AircraftCategory.MIDSIZE: "Midsize",
    AircraftCategory.SUPER_MIDSIZE: "Super-midsize",
    AircraftCategory.HEAVY: "Heavy",
    AircraftCategory.ULTRA_LONG_RANGE: "Ultra long range",
    AircraftCategory.AIRLINER: "Airliner",
}

AMOUNT_STATUS_LABELS: Final[dict[AmountStatus, str]] = {
    AmountStatus.STATED: "Stated",
    AmountStatus.INCLUDED: "Included",
    AmountStatus.ESTIMATED: "Estimated",
    AmountStatus.NOT_STATED: "Not stated",
    AmountStatus.WAIVED: "Waived",
    AmountStatus.NOT_APPLICABLE: "Not applicable",
}

FLAG_TYPE_LABELS: Final[dict[FlagType, str]] = {
    FlagType.AMBIGUOUS_CHARGE: "Ambiguous charge",
    FlagType.EXPECTED_FEE_MISSING: "Expected fee missing",
    FlagType.CONDITIONAL_CHARGE: "Conditional charge",
    FlagType.LEARNED_FEE_MISSING: "Usually charged here",
    FlagType.TOTAL_MISMATCH: "Total mismatch",
    FlagType.CONFLICTING_VALUES: "Conflicting values",
    FlagType.CONFLICT_WITH_LOCKED: "Conflicts with reviewed value",
    FlagType.MISSING_REQUIRED_FIELD: "Missing required field",
    FlagType.CAPACITY_INSUFFICIENT: "Not enough seats",
    FlagType.HOURLY_ESTIMATE: "Hourly price estimated",
    FlagType.UNKNOWN_CURRENCY: "Unknown currency",
    FlagType.EXTRACTION_FAILED: "Extraction failed",
    FlagType.OCR_UNAVAILABLE: "Scanned document needs manual entry",
    FlagType.QUOTE_EXPIRED: "Quote expired",
    FlagType.ALL_IN_ITEMIZED_CONFLICT: "All-in with itemized charges",
    FlagType.FX_CONVERTED: "Converted from another currency",
    FlagType.SNIPPET_UNVERIFIED: "Source snippet not found",
    FlagType.FEE_OUTLIER: "Unusually high fee",
    FlagType.SCHEDULE_MISMATCH: "Schedule differs from request",
    FlagType.VALUE_REVISED: "Value revised",
}

FLAG_RESOLUTION_LABELS: Final[dict[FlagResolution, str]] = {
    FlagResolution.CONFIRMED_AMOUNT: "Confirmed amount",
    FlagResolution.ACCEPTED_ESTIMATE: "Accept estimate",
    FlagResolution.CONFIRMED_INCLUDED: "Confirmed included",
    FlagResolution.NOT_APPLICABLE: "Not applicable",
    FlagResolution.DISMISSED: "Dismiss",
    FlagResolution.ACKNOWLEDGED: "Acknowledge",
    FlagResolution.USE_NEW_VALUE: "Use new value",
    FlagResolution.KEEP_CURRENT: "Keep current value",
    FlagResolution.AUTO_CLEARED: "Cleared automatically",
}


class VocabItem(BaseModel):
    value: str
    label: str


class FeeCategoryItem(VocabItem):
    order: int


class FlagTypeItem(VocabItem):
    resolutions: list[VocabItem]


class VocabularyOut(BaseModel):
    fee_categories: list[FeeCategoryItem]
    aircraft_categories: list[VocabItem]
    amount_statuses: list[VocabItem]
    flag_types: list[FlagTypeItem]
    flag_severities: list[FlagSeverity]
    field_statuses: list[FieldStatus]
    quote_statuses: list[QuoteStatus]
    trip_statuses: list[TripStatus]
    trip_operator_statuses: list[TripOperatorStatus]
    proposal_statuses: list[ProposalStatus]
    roles: list[Role]
    max_upload_mb: int = Field(description="Largest file the ingest endpoint accepts (MB)")


class AirportOut(BaseModel):
    icao: str
    iata: str | None
    name: str
    city: str
    country: str
    tz: str


class HealthOut(BaseModel):
    """Never reveals configuration secrets such as the API key."""

    status: Literal["ok", "degraded"]
    db: Literal["ok", "error"]
    extractor: Literal["rules", "claude"]
    version: str
