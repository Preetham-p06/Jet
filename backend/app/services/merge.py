"""Resolving the quote for a document and merging extracted values (spec §3.5).

Quote resolution order: explicit quote_id; explicit operator_id or
trip_operator_id; sender match (email, phone, non-webmail domain); extracted
operator name (normalized, alias, distinctive token, difflib >= 0.88);
otherwise a new operator (`source=extraction`) if the name confidence >= 75,
else the sender label. A decline intent marks the trip operator declined and
creates no quote.

Field merge, ordered by (received_at, sequence): insert when absent; replace
when from the same document unless locked; corroborate equal values
(confidence min(99, max + 3)); a conflict with a locked value is stored
non-current with a `conflict_with_locked` warning; a newer unlocked value
supersedes, unless it is weaker (estimated/not_stated vs a stated value at or
above threshold), which stores it non-current with `conflicting_values`; an
older source processed later is stored as history only.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.orm import Session

from app.extraction.types import ExtractedFee, ExtractedField, ExtractionResult
from app.models.document import SourceDocument
from app.models.operator import Operator
from app.models.quote import Quote
from app.models.trip import Trip, TripOperator


@dataclass(frozen=True, slots=True)
class QuoteResolution:
    quote: Quote | None  # None for a decline
    operator: Operator | None
    trip_operator: TripOperator | None
    created_quote: bool
    created_operator: bool


@dataclass(slots=True)
class MergeReport:
    inserted: list[str] = field(default_factory=list)
    replaced: list[str] = field(default_factory=list)
    superseded: list[str] = field(default_factory=list)
    corroborated: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    history_only: list[str] = field(default_factory=list)
    #: Log lines such as "Revised: positioning 1,200 -> 900 (WhatsApp)".
    events: list[str] = field(default_factory=list)


def key_for(item: ExtractedField | ExtractedFee) -> str:
    """Quote field key: the field key, `fee.<category>`, or `fee.other.<slug>`."""
    raise NotImplementedError


def resolve_quote(
    db: Session,
    trip: Trip,
    doc: SourceDocument,
    result: ExtractionResult,
    *,
    quote_id: uuid.UUID | None = None,
    operator_id: uuid.UUID | None = None,
    now: datetime,
) -> QuoteResolution:
    raise NotImplementedError


def merge_result(
    db: Session,
    quote: Quote,
    doc: SourceDocument,
    result: ExtractionResult,
    *,
    review_threshold: int,
    now: datetime,
) -> MergeReport:
    raise NotImplementedError
