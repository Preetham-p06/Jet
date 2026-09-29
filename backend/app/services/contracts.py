"""Pure data shared by the pricing engine and the database glue.

The engine modules (`normalization`, `fee_rules`, `fee_intelligence.learned_stats`,
`flags`, `scoring`, the proposal math) are pure functions over these
dataclasses: no Session, no clock (``now`` is passed in), no I/O.
`services.recompute` builds them from ORM rows and writes the results back.

Conventions:

* Money on the engine's *output* side is integer USD cents (``*_cents``).
  Inputs from quote fields keep the original currency in minor units
  (``*_minor`` plus ``currency``); normalization converts with an `FxTable`.
* Every dataclass is frozen; collections are tuples or read-only mappings.
* Frozen at foundation. Changes go through the lead (see ``backend/AGENTS.md``).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Final, Literal

from app.models.enums import (
    AircraftCategory,
    AmountStatus,
    Availability,
    FeeCategory,
    FeeUnit,
    FieldGroup,
    FieldStatus,
    FlagSeverity,
    FlagType,
    IncludedBy,
    PricingBasis,
    QuoteStatus,
    TripType,
)

# --------------------------------------------------------------------------- vocabulary

CALC_VERSION: Final = "calc-1"
ALGORITHM_VERSION: Final = "fit-1"

#: Fee statuses that count as reviewed by a human.
REVIEWED_STATUSES: Final = frozenset(
    {FieldStatus.VERIFIED, FieldStatus.ACCEPTED, FieldStatus.EDITED}
)

#: Scalar keys that affect money or are shown to the client (spec §5). Every
#: fee field (``fee.*``) is material as well.
MATERIAL_SCALAR_KEYS: Final = frozenset(
    {
        "headline_price",
        "hourly_rate",
        "billable_hours",
        "daily_minimum_hours",
        "stated_total",
        "all_in",
        "aircraft_model",
        "aircraft_category",
        "seats",
        "wifi",
        "flight_time_minutes",
    }
)

#: Categories an "all in" headline covers when the quote has no line for them.
ALL_IN_COVERED: Final = frozenset(
    {
        FeeCategory.FET,
        FeeCategory.SEGMENT_FEES,
        FeeCategory.TAXES,
        FeeCategory.LANDING,
        FeeCategory.CATERING,
        FeeCategory.RAMP_HANDLING,
    }
)

#: Categories excluded from the FET base (taxes are not taxed).
FET_BASE_EXCLUDED: Final = frozenset(
    {FeeCategory.FET, FeeCategory.SEGMENT_FEES, FeeCategory.TAXES, FeeCategory.INTERNATIONAL}
)


def is_material_key(key: str) -> bool:
    return key.startswith("fee.") or key in MATERIAL_SCALAR_KEYS


# --------------------------------------------------------------------------- reference data


@dataclass(frozen=True, slots=True)
class AirportInfo:
    """One row of ``data/airports.json``."""

    icao: str
    iata: str | None
    name: str
    city: str
    country: str  # ISO 3166-1 alpha-2, "US" for the United States
    tz: str  # IANA zone
    lat: float
    lon: float
    deice_zone: bool = False  # north of 38°N or explicitly listed

    @property
    def is_us(self) -> bool:
        return self.country == "US"


@dataclass(frozen=True, slots=True)
class FxTable:
    """Static FX rates: ``rates[ccy]`` is USD per one unit of ``ccy``."""

    as_of: date
    rates: Mapping[str, Decimal]
    base: str = "USD"

    def knows(self, currency: str) -> bool:
        return currency == self.base or currency in self.rates


# --------------------------------------------------------------------------- trip


@dataclass(frozen=True, slots=True)
class LegState:
    seq: int
    origin_icao: str
    destination_icao: str
    depart_local: datetime  # naive wall-clock at the origin
    depart_tz: str
    depart_utc: datetime  # aware; derived from depart_local + depart_tz


@dataclass(frozen=True, slots=True)
class TripPreferencesState:
    wifi_required: bool = False
    preferred_categories: tuple[AircraftCategory, ...] = ()
    catering_required: bool = False
    max_budget_cents: int | None = None


@dataclass(frozen=True, slots=True)
class TripContext:
    """Everything the engine needs to know about the trip and its workspace."""

    trip_id: uuid.UUID
    workspace_id: uuid.UUID
    reference: str
    trip_type: TripType
    pax: int
    legs: tuple[LegState, ...]
    preferences: TripPreferencesState
    review_threshold: int
    #: Airport rows for every leg endpoint (and quoted base airports), by ICAO.
    airports: Mapping[str, AirportInfo] = field(default_factory=lambda: MappingProxyType({}))
    base_currency: str = "USD"
    #: Workspace overrides of `DEFAULT_WEIGHTS`; None means the defaults.
    scoring_weights: Mapping[str, float] | None = None

    @property
    def first_leg(self) -> LegState:
        return self.legs[0]

    @property
    def departure_month(self) -> int:
        return self.first_leg.depart_local.month

    @property
    def is_multi_day(self) -> bool:
        """True when the legs span at least one night (local calendar dates differ)."""
        days = {leg.depart_local.date() for leg in self.legs}
        return len(days) > 1

    @property
    def is_us_domestic(self) -> bool:
        """All endpoints are known US airports."""
        codes = {c for leg in self.legs for c in (leg.origin_icao, leg.destination_icao)}
        return bool(codes) and all(
            (a := self.airports.get(c)) is not None and a.is_us for c in codes
        )


# --------------------------------------------------------------------------- quote inputs


@dataclass(frozen=True, slots=True)
class FieldState:
    """One current quote_field, reduced to what confidence and flags need."""

    field_id: uuid.UUID
    key: str
    group: FieldGroup
    value: Any  # JSON value as stored in current_value
    confidence: int
    status: FieldStatus
    snippet_verified: bool = True
    source_document_id: uuid.UUID | None = None
    page: int | None = None

    @property
    def is_reviewed(self) -> bool:
        return self.status in REVIEWED_STATUSES

    @property
    def is_material(self) -> bool:
        return is_material_key(self.key)


@dataclass(frozen=True, slots=True)
class FeeLineState:
    """A current fee field as the normalizer sees it.

    ``amount_minor`` is in ``currency`` (the quote's original currency unless the
    line says otherwise). For percent fees ``percent`` is set (7.5 means 7.5 %)
    and ``amount_minor`` is usually None.
    """

    category: FeeCategory
    label: str
    status: AmountStatus
    amount_minor: int | None = None
    currency: str | None = None
    unit: FeeUnit = FeeUnit.FLAT
    quantity: Decimal | None = None
    percent: Decimal | None = None
    explicitly_extra: bool = False
    hedged: bool = False
    confidence: int | None = None
    review_status: FieldStatus = FieldStatus.EXTRACTED
    field_id: uuid.UUID | None = None
    source_document_id: uuid.UUID | None = None
    page: int | None = None

    @property
    def is_accepted(self) -> bool:
        """Reviewed by a human, so an estimate counts in the known total."""
        return self.review_status in REVIEWED_STATUSES


ConflictKind = Literal["conflict_with_locked", "conflicting_values"]


@dataclass(frozen=True, slots=True)
class ConflictState:
    """An unresolved candidate value kept as non-current by the merge.

    Built by recompute from quote_fields with ``is_current=False`` and
    ``superseded_by_id IS NULL`` that are newer than the current row.
    """

    kind: ConflictKind
    key: str
    current_field_id: uuid.UUID
    candidate_field_id: uuid.UUID
    current_value: Any
    candidate_value: Any
    candidate_source_document_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class RevisionState:
    """A value that a newer source replaced (drives the `value_revised` info flag)."""

    key: str
    previous_value: Any
    current_value: Any
    field_id: uuid.UUID
    source_document_id: uuid.UUID | None = None


DocumentIssueKind = Literal["extraction_failed", "ocr_unavailable"]


@dataclass(frozen=True, slots=True)
class DocumentIssue:
    kind: DocumentIssueKind
    source_document_id: uuid.UUID
    message: str


@dataclass(frozen=True, slots=True)
class QuoteState:
    """One quote's current values, as the engine sees them.

    Money inputs are in minor units of ``currency``. ``headline_minor`` is the
    stated headline; for hourly quotes it is None and the normalizer derives it
    from ``hourly_rate_minor`` x max(``billable_hours``, ``daily_minimum_hours``),
    or from ``flight_time_minutes`` (estimated, with a warning).
    """

    quote_id: uuid.UUID
    operator_id: uuid.UUID
    operator_name: str
    status: QuoteStatus
    currency: str
    pricing_basis: PricingBasis
    created_at: datetime

    # Price inputs
    headline_minor: int | None = None
    hourly_rate_minor: int | None = None
    billable_hours: Decimal | None = None
    daily_minimum_hours: Decimal | None = None
    stated_total_minor: int | None = None
    all_in: bool = False
    fees: tuple[FeeLineState, ...] = ()

    # Aircraft and schedule
    aircraft_model: str | None = None
    aircraft_category: AircraftCategory | None = None
    tail_number: str | None = None
    seats: int | None = None
    wifi: bool | None = None
    flight_time_minutes: int | None = None
    departure_local: datetime | None = None  # naive, local to the origin
    availability: Availability | None = None
    valid_until: datetime | None = None  # aware
    #: Where the aircraft is based, when the quote says so (drives the positioning rule).
    base_airport_icao: str | None = None
    operator_home_base_icao: str | None = None

    # Review and provenance
    fields: tuple[FieldState, ...] = ()
    conflicts: tuple[ConflictState, ...] = ()
    revisions: tuple[RevisionState, ...] = ()
    document_issues: tuple[DocumentIssue, ...] = ()
    first_received_at: datetime | None = None
    last_received_at: datetime | None = None

    def fees_in(self, category: FeeCategory) -> tuple[FeeLineState, ...]:
        return tuple(f for f in self.fees if f.category is category)

    def field(self, key: str) -> FieldState | None:
        return next((f for f in self.fields if f.key == key), None)


# --------------------------------------------------------------------------- engine outputs


@dataclass(frozen=True, slots=True)
class LearnedStat:
    """Workspace-local frequency and amount stats for one fee category at one airport."""

    n: int  # quotes observed (present or not)
    frequency: float  # share of those quotes carrying the fee, 0..1
    median_cents: int | None = None  # over present rows with an amount
    p25_cents: int | None = None
    p75_cents: int | None = None
    n_amounts: int = 0

    @property
    def iqr_cents(self) -> int | None:
        if self.p25_cents is None or self.p75_cents is None:
            return None
        return self.p75_cents - self.p25_cents


@dataclass(frozen=True, slots=True)
class FeeObservationPoint:
    """A `fee_observations` row reduced to what `learned_stats` needs."""

    category: FeeCategory
    present: bool
    amount_cents: int | None = None


ExpectedFeeSource = Literal["rule", "learned"]


@dataclass(frozen=True, slots=True)
class ExpectedFee:
    """A fee the trip probably incurs that the quote does not mention.

    ``severity`` warning puts a synthetic not_stated line (with the estimate)
    into the upper total; info goes to `TrueCost.conditional_charges` only.
    """

    category: FeeCategory
    severity: FlagSeverity
    reason: str
    estimate_cents: int | None
    rule_id: str  # "fet", "segment_fees", "international", "deicing", "crew_overnight",
    # "positioning", or "learned:<ICAO>"
    source: ExpectedFeeSource = "rule"
    stat: LearnedStat | None = None


@dataclass(frozen=True, slots=True)
class NormalizedFeeLine:
    """One output fee line; maps 1:1 onto a `FeeLine` row."""

    category: FeeCategory
    label: str
    amount_status: AmountStatus
    counts_in_known: bool
    counts_in_upper: bool
    sort_order: int
    amount_cents: int | None = None  # USD; None when included/not stated
    included_by: IncludedBy | None = None
    original_amount_minor: int | None = None
    original_currency: str | None = None
    unit: FeeUnit = FeeUnit.FLAT
    quantity: Decimal | None = None
    percent: Decimal | None = None
    explicitly_extra: bool = False
    estimate_cents: int | None = None
    estimate_basis: str | None = None  # "operator_estimate", "rule:fet", "learned:KTEB"
    confidence: int | None = None
    review_status: FieldStatus | None = None
    field_id: uuid.UUID | None = None
    source_document_id: uuid.UUID | None = None
    page: int | None = None

    @property
    def is_synthetic(self) -> bool:
        return self.field_id is None


TotalDirection = Literal["above", "below"]


@dataclass(frozen=True, slots=True)
class TotalMismatch:
    """The operator's stated total disagrees with the computed sum.

    ``above``: stated > computed; the stated total becomes the known total and a
    warning is raised. ``below``: the computed sum is kept (conservative) and an
    info flag names the lines whose inclusion would reconcile it.
    """

    direction: TotalDirection
    stated_cents: int
    computed_cents: int
    reconciling_labels: tuple[str, ...] = ()

    @property
    def difference_cents(self) -> int:
        return self.stated_cents - self.computed_cents


@dataclass(frozen=True, slots=True)
class FxApplied:
    currency: str
    rate: Decimal  # USD per unit
    as_of: date


@dataclass(frozen=True, slots=True)
class TrueCost:
    """Result of `normalization.normalize_quote`.

    Invariant: ``known_total_cents <= upper_total_cents`` whenever both are set.
    ``is_fully_priced`` is False while any estimate is unaccepted, any expected
    fee is unresolved, the headline is estimated, or a blocking price flag is
    open; the UI then shows the known total with a "+".
    """

    headline_cents: int | None
    headline_estimated: bool
    known_total_cents: int | None
    upper_total_cents: int | None
    is_fully_priced: bool
    lines: tuple[NormalizedFeeLine, ...]
    conditional_charges: tuple[ExpectedFee, ...] = ()
    stated_total_cents: int | None = None
    total_mismatch: TotalMismatch | None = None
    fx: FxApplied | None = None
    unknown_currency: str | None = None
    all_in_itemized_conflict: bool = False

    @property
    def added_charges_cents(self) -> int | None:
        if self.known_total_cents is None or self.headline_cents is None:
            return None
        return self.known_total_cents - self.headline_cents

    @property
    def price_for_ranking_cents(self) -> int | None:
        """Upper total when not fully priced, else the known total (Pricing signal)."""
        return self.known_total_cents if self.is_fully_priced else self.upper_total_cents


def flag_fingerprint(flag_type: FlagType, subject: str = "") -> str:
    """Stable per-quote identity of a flag condition, e.g. "ambiguous_charge:fuel_surcharge".

    ``subject`` is the fee category, field key, document id or rule id the
    condition is about; empty for quote-level flags.
    """
    return f"{flag_type.value}:{subject}" if subject else flag_type.value


@dataclass(frozen=True, slots=True)
class FlagSpec:
    """A flag condition produced by `flags.evaluate_flags`; reconciled by fingerprint."""

    type: FlagType
    severity: FlagSeverity
    fingerprint: str
    message: str
    details: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))
    field_id: uuid.UUID | None = None
    fee_category: FeeCategory | None = None
    source_document_id: uuid.UUID | None = None
    #: Defaults to the severity rule: warning and critical block, info does not.
    blocking: bool | None = None

    @property
    def is_blocking(self) -> bool:
        if self.blocking is not None:
            return self.blocking
        return self.severity is not FlagSeverity.INFO

    def data_hash(self) -> str:
        """Hash of the details; a change reopens a resolved flag."""
        payload = json.dumps(self.details, sort_keys=True, default=str, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()


# --------------------------------------------------------------------------- scoring


class Signal(StrEnum):
    PRICING = "pricing"
    FEES = "fees"
    AIRCRAFT = "aircraft"
    TIMING = "timing"
    PREFERENCES = "preferences"
    AVAILABILITY = "availability"
    CREW = "crew"
    ROUTING = "routing"


DEFAULT_WEIGHTS: Final[Mapping[Signal, float]] = MappingProxyType(
    {
        Signal.PRICING: 30,
        Signal.FEES: 15,
        Signal.AIRCRAFT: 15,
        Signal.TIMING: 10,
        Signal.PREFERENCES: 10,
        Signal.AVAILABILITY: 8,
        Signal.CREW: 7,
        Signal.ROUTING: 5,
    }
)

SIGNAL_LABELS: Final[Mapping[Signal, str]] = MappingProxyType(
    {
        Signal.PRICING: "Pricing",
        Signal.FEES: "Fees",
        Signal.AIRCRAFT: "Aircraft",
        Signal.TIMING: "Timing",
        Signal.PREFERENCES: "Client preferences",
        Signal.AVAILABILITY: "Availability",
        Signal.CREW: "Crew",
        Signal.ROUTING: "Routing",
    }
)


@dataclass(frozen=True, slots=True)
class ScoreInput:
    """Per-quote inputs to `scoring.score_trip`, built from QuoteState + TrueCost."""

    quote_id: uuid.UUID
    operator_name: str
    status: QuoteStatus
    created_at: datetime
    headline_cents: int | None
    known_total_cents: int | None
    upper_total_cents: int | None
    is_fully_priced: bool
    open_blocking_flags: int
    quote_confidence: int | None
    seats: int | None = None
    aircraft_category: AircraftCategory | None = None
    wifi: bool | None = None
    catering_included: bool | None = None  # None when catering is not mentioned
    departure_local: datetime | None = None  # naive, local to the origin
    flight_time_minutes: int | None = None
    availability: Availability | None = None
    crew_overnight_charged: bool = False
    extra_crew_charged: bool = False
    positioning_cents: int | None = None  # None when unknown, 0 when none/included
    tech_stop: bool = False


@dataclass(frozen=True, slots=True)
class SignalScore:
    signal: Signal
    weight: float
    raw: float | None  # before imputation; None when the data is missing
    value: float | None  # used in the mean; the cohort median when imputed
    imputed: bool = False
    dropped: bool = False  # missing for every quote; weight renormalized away
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class ScoreBreakdown:
    fit: int | None
    signals: tuple[SignalScore, ...]
    schedule_subscore: float | None = None  # for the "Best schedule fit" check

    def signal(self, key: Signal) -> SignalScore | None:
        return next((s for s in self.signals if s.signal is key), None)


class IneligibilityCode(StrEnum):
    NOT_ACTIVE = "not_active"
    NO_HEADLINE = "no_headline"
    NOT_FULLY_PRICED = "not_fully_priced"
    BLOCKING_FLAGS = "blocking_flags"
    INSUFFICIENT_CAPACITY = "insufficient_capacity"
    UNAVAILABLE = "unavailable"
    UNREVIEWED_LOW_CONFIDENCE = "unreviewed_low_confidence"


@dataclass(frozen=True, slots=True)
class EligibilityReason:
    code: IneligibilityCode
    message: str  # e.g. "Fuel surcharge not stated"


@dataclass(frozen=True, slots=True)
class Eligibility:
    """For recommendation (spec §5) and for proposals (spec §6, adds the review gate)."""

    eligible: bool
    reasons: tuple[EligibilityReason, ...] = ()

    @classmethod
    def ok(cls) -> Eligibility:
        return cls(eligible=True)

    @classmethod
    def blocked(cls, *reasons: EligibilityReason) -> Eligibility:
        return cls(eligible=not reasons, reasons=reasons)


CheckKey = Literal["schedule", "lowest_cost", "wifi", "seats", "no_crew_overnight"]


@dataclass(frozen=True, slots=True)
class Check:
    """One of the five checks shown for the recommended quote."""

    key: CheckKey
    label: str  # "Best schedule fit", "Lowest fully-priced total cost", "Wi-Fi on board",
    # "8-seat configuration", "No overnight crew requirement"
    passed: bool


@dataclass(frozen=True, slots=True)
class RankedQuote:
    quote_id: uuid.UUID
    rank: int  # 1-based over all quotes, eligible first
    breakdown: ScoreBreakdown
    eligibility: Eligibility


@dataclass(frozen=True, slots=True)
class RecommendationResult:
    """Output of `scoring.score_trip`. Ties break on lower known total, higher
    quote confidence, earlier created_at, then id."""

    algorithm_version: str
    weights: Mapping[Signal, float]
    recommended_quote_id: uuid.UUID | None
    ranking: tuple[RankedQuote, ...]
    checks: tuple[Check, ...] = ()

    def for_quote(self, quote_id: uuid.UUID) -> RankedQuote | None:
        return next((r for r in self.ranking if r.quote_id == quote_id), None)
