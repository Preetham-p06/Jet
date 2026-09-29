"""String enums shared by the ORM, the schemas and the engine.

Every enum is a `StrEnum`, stored in the database as a plain string
(`native_enum=False`) so adding a member never needs a Postgres enum migration.
"""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    ADMIN = "admin"
    BROKER = "broker"
    ASSISTANT = "assistant"


class OperatorSource(StrEnum):
    MANUAL = "manual"
    EXTRACTION = "extraction"


class TripStatus(StrEnum):
    DRAFT = "draft"
    SOURCING = "sourcing"
    QUOTED = "quoted"
    PROPOSED = "proposed"
    BOOKED = "booked"
    CANCELLED = "cancelled"
    LOST = "lost"


class TripType(StrEnum):
    ONE_WAY = "one_way"
    ROUND_TRIP = "round_trip"
    MULTI_LEG = "multi_leg"


class TripOperatorStatus(StrEnum):
    REQUESTED = "requested"
    QUOTED = "quoted"
    DECLINED = "declined"


class RequestChannel(StrEnum):
    """How an operator was asked for a quote (RFQ tracking)."""

    EMAIL = "email"
    PHONE = "phone"
    SMS = "sms"
    WHATSAPP = "whatsapp"
    PORTAL = "portal"
    OTHER = "other"


class DocumentKind(StrEnum):
    PDF = "pdf"
    EMAIL = "email"
    SMS = "sms"
    WHATSAPP = "whatsapp"
    TEXT = "text"
    IMAGE = "image"


class DocumentChannel(StrEnum):
    """How a quote document reached the broker."""

    PDF_UPLOAD = "pdf_upload"
    EMAIL = "email"
    SMS = "sms"
    WHATSAPP = "whatsapp"
    PASTE = "paste"
    OTHER = "other"


class DocumentIntent(StrEnum):
    QUOTE = "quote"
    REVISION = "revision"
    DECLINE = "decline"
    OTHER = "other"


class ExtractionStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    NEEDS_MANUAL = "needs_manual"


class ProcessingStep(StrEnum):
    INGEST = "ingest"
    EXTRACT = "extract"
    NORMALIZE = "normalize"
    VALIDATE = "validate"
    COMPARE = "compare"
    RECOMMENDATION = "recommendation"


class EventLevel(StrEnum):
    INFO = "info"
    WARN = "warn"
    OK = "ok"
    ERROR = "error"


class QuoteStatus(StrEnum):
    ACTIVE = "active"
    WITHDRAWN = "withdrawn"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class PricingBasis(StrEnum):
    FLAT = "flat"
    HOURLY = "hourly"


class Availability(StrEnum):
    CONFIRMED = "confirmed"
    AVAILABLE = "available"
    SUBJECT_TO = "subject_to"
    TENTATIVE = "tentative"
    ON_REQUEST = "on_request"
    UNAVAILABLE = "unavailable"


class FieldGroup(StrEnum):
    SCALAR = "scalar"
    FEE = "fee"


class ValueType(StrEnum):
    TEXT = "text"
    INT = "int"
    NUMBER = "number"
    BOOL = "bool"
    MONEY = "money"
    DATETIME = "datetime"
    DURATION = "duration"
    FEE = "fee"


class ExtractorKind(StrEnum):
    RULES = "rules"
    CLAUDE = "claude"
    MANUAL = "manual"


class FieldStatus(StrEnum):
    EXTRACTED = "extracted"
    VERIFIED = "verified"
    ACCEPTED = "accepted"
    EDITED = "edited"


class FeeCategory(StrEnum):
    """Canonical fee categories, in display order."""

    POSITIONING = "positioning"
    RAMP_HANDLING = "ramp_handling"
    FUEL_SURCHARGE = "fuel_surcharge"
    CATERING = "catering"
    CREW_OVERNIGHT = "crew_overnight"
    CREW = "crew"
    OVERNIGHT = "overnight"
    LANDING = "landing"
    DEICING = "deicing"
    INTERNATIONAL = "international"
    FET = "fet"
    SEGMENT_FEES = "segment_fees"
    TAXES = "taxes"
    WIFI_FEE = "wifi_fee"
    OTHER = "other"


FEE_CATEGORY_ORDER: tuple[FeeCategory, ...] = tuple(FeeCategory)


class AmountStatus(StrEnum):
    STATED = "stated"
    INCLUDED = "included"
    ESTIMATED = "estimated"
    NOT_STATED = "not_stated"
    WAIVED = "waived"
    NOT_APPLICABLE = "not_applicable"


class IncludedBy(StrEnum):
    EXPLICIT = "explicit"
    ALL_IN = "all_in"


class FeeUnit(StrEnum):
    FLAT = "flat"
    PER_HOUR = "per_hour"
    PER_NIGHT = "per_night"
    PER_LEG = "per_leg"
    PER_PAX = "per_pax"
    PERCENT = "percent"


class FlagType(StrEnum):
    AMBIGUOUS_CHARGE = "ambiguous_charge"
    EXPECTED_FEE_MISSING = "expected_fee_missing"
    CONDITIONAL_CHARGE = "conditional_charge"
    LEARNED_FEE_MISSING = "learned_fee_missing"
    TOTAL_MISMATCH = "total_mismatch"
    CONFLICTING_VALUES = "conflicting_values"
    CONFLICT_WITH_LOCKED = "conflict_with_locked"
    MISSING_REQUIRED_FIELD = "missing_required_field"
    CAPACITY_INSUFFICIENT = "capacity_insufficient"
    HOURLY_ESTIMATE = "hourly_estimate"
    UNKNOWN_CURRENCY = "unknown_currency"
    EXTRACTION_FAILED = "extraction_failed"
    OCR_UNAVAILABLE = "ocr_unavailable"
    QUOTE_EXPIRED = "quote_expired"
    ALL_IN_ITEMIZED_CONFLICT = "all_in_itemized_conflict"
    FX_CONVERTED = "fx_converted"
    SNIPPET_UNVERIFIED = "snippet_unverified"
    FEE_OUTLIER = "fee_outlier"
    SCHEDULE_MISMATCH = "schedule_mismatch"
    VALUE_REVISED = "value_revised"


class FlagSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class FlagStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class FlagResolution(StrEnum):
    CONFIRMED_AMOUNT = "confirmed_amount"
    ACCEPTED_ESTIMATE = "accepted_estimate"
    CONFIRMED_INCLUDED = "confirmed_included"
    NOT_APPLICABLE = "not_applicable"
    DISMISSED = "dismissed"
    ACKNOWLEDGED = "acknowledged"
    USE_NEW_VALUE = "use_new_value"
    KEEP_CURRENT = "keep_current"
    AUTO_CLEARED = "auto_cleared"


class ProposalStatus(StrEnum):
    DRAFT = "draft"
    SENT = "sent"
    ACCEPTED = "accepted"
    BOOKED = "booked"
    DECLINED = "declined"
    CANCELLED = "cancelled"
    SUPERSEDED = "superseded"


class ActorKind(StrEnum):
    USER = "user"
    SYSTEM = "system"
    PUBLIC = "public"


class AirportRole(StrEnum):
    DEPARTURE = "departure"
    ARRIVAL = "arrival"


class ObservationSource(StrEnum):
    EXTRACTED = "extracted"
    VERIFIED = "verified"


class AircraftCategory(StrEnum):
    TURBOPROP = "turboprop"
    VERY_LIGHT = "very_light"
    LIGHT = "light"
    MIDSIZE = "midsize"
    SUPER_MIDSIZE = "super_midsize"
    HEAVY = "heavy"
    ULTRA_LONG_RANGE = "ultra_long_range"
    AIRLINER = "airliner"


_FEE_RESOLUTIONS = (
    FlagResolution.CONFIRMED_AMOUNT,
    FlagResolution.CONFIRMED_INCLUDED,
    FlagResolution.NOT_APPLICABLE,
    FlagResolution.DISMISSED,
)

#: Resolutions a broker may choose per flag type (spec §4). Types missing here
#: auto-clear or are fixed by editing/reprocessing; they can still be dismissed.
FLAG_RESOLUTIONS: dict[FlagType, tuple[FlagResolution, ...]] = {
    FlagType.AMBIGUOUS_CHARGE: (
        FlagResolution.CONFIRMED_AMOUNT,
        FlagResolution.ACCEPTED_ESTIMATE,
        FlagResolution.CONFIRMED_INCLUDED,
        FlagResolution.NOT_APPLICABLE,
        FlagResolution.DISMISSED,
    ),
    FlagType.EXPECTED_FEE_MISSING: _FEE_RESOLUTIONS,
    FlagType.LEARNED_FEE_MISSING: _FEE_RESOLUTIONS,
    FlagType.CONDITIONAL_CHARGE: (FlagResolution.ACKNOWLEDGED,),
    FlagType.TOTAL_MISMATCH: (FlagResolution.ACKNOWLEDGED,),
    FlagType.CONFLICTING_VALUES: (FlagResolution.USE_NEW_VALUE, FlagResolution.KEEP_CURRENT),
    FlagType.CONFLICT_WITH_LOCKED: (FlagResolution.USE_NEW_VALUE, FlagResolution.KEEP_CURRENT),
    FlagType.MISSING_REQUIRED_FIELD: (FlagResolution.DISMISSED,),
    FlagType.CAPACITY_INSUFFICIENT: (FlagResolution.DISMISSED,),
    FlagType.HOURLY_ESTIMATE: (FlagResolution.CONFIRMED_AMOUNT, FlagResolution.ACKNOWLEDGED),
    FlagType.UNKNOWN_CURRENCY: (FlagResolution.DISMISSED,),
    FlagType.EXTRACTION_FAILED: (FlagResolution.DISMISSED,),
    FlagType.OCR_UNAVAILABLE: (FlagResolution.DISMISSED,),
    FlagType.QUOTE_EXPIRED: (FlagResolution.ACKNOWLEDGED,),
    FlagType.ALL_IN_ITEMIZED_CONFLICT: (FlagResolution.ACKNOWLEDGED,),
    FlagType.FX_CONVERTED: (FlagResolution.ACKNOWLEDGED,),
    FlagType.SNIPPET_UNVERIFIED: (FlagResolution.ACKNOWLEDGED,),
    FlagType.FEE_OUTLIER: (FlagResolution.ACKNOWLEDGED,),
    FlagType.SCHEDULE_MISMATCH: (FlagResolution.ACKNOWLEDGED,),
    FlagType.VALUE_REVISED: (FlagResolution.ACKNOWLEDGED,),
}
