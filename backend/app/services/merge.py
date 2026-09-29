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
from typing import Any, Final

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import NotFound, Unprocessable
from app.extraction.types import ExtractedFee, ExtractedField, ExtractionResult, Money
from app.models.document import SourceDocument
from app.models.enums import (
    AmountStatus,
    DocumentChannel,
    ExtractorKind,
    OperatorSource,
    QuoteStatus,
    RequestChannel,
    TripOperatorStatus,
    TripStatus,
)
from app.models.operator import Operator
from app.models.quote import Quote, QuoteField
from app.models.trip import Trip, TripOperator
from app.schemas.field_values import (
    FeeValue,
    MoneyValue,
    fee_key,
    group_for_key,
    parse_field_value,
    value_type_for_key,
)
from app.services import operators as operator_service


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
    if isinstance(item, ExtractedFee):
        return fee_key(item.category, item.label)
    return item.key


#: A new operator is created from the extracted name only at or above this confidence.
NEW_OPERATOR_MIN_CONFIDENCE: Final = 75
#: Corroboration raises confidence by this much, capped at `CORROBORATED_CAP`.
CORROBORATION_BONUS: Final = 3
CORROBORATED_CAP: Final = 99
_WEAKER_STATUSES: Final = frozenset({AmountStatus.ESTIMATED, AmountStatus.NOT_STATED})
_FEE_COMPARE_KEYS: Final = ("status", "amount", "unit", "quantity", "percent", "explicitly_extra")

_CHANNEL_LABELS: Final[dict[DocumentChannel, str]] = {
    DocumentChannel.PDF_UPLOAD: "PDF",
    DocumentChannel.EMAIL: "email",
    DocumentChannel.SMS: "SMS",
    DocumentChannel.WHATSAPP: "WhatsApp",
    DocumentChannel.PASTE: "pasted text",
    DocumentChannel.OTHER: "upload",
}
_REQUEST_CHANNELS: Final[dict[DocumentChannel, RequestChannel]] = {
    DocumentChannel.EMAIL: RequestChannel.EMAIL,
    DocumentChannel.PDF_UPLOAD: RequestChannel.EMAIL,
    DocumentChannel.SMS: RequestChannel.SMS,
    DocumentChannel.WHATSAPP: RequestChannel.WHATSAPP,
}


def channel_label(channel: DocumentChannel) -> str:
    return _CHANNEL_LABELS.get(channel, "upload")


def document_time(doc: SourceDocument) -> datetime:
    """When the source reached the broker (merge ordering, response times)."""
    return doc.received_at or doc.created_at


# --------------------------------------------------------------------------- resolution


def _field_value(result: ExtractionResult, key: str) -> ExtractedField | None:
    items = [f for f in result.fields if f.key == key and f.value is not None]
    return max(items, key=lambda f: (f.sequence, f.confidence)) if items else None


def _explicit_operator(
    db: Session, trip: Trip, operator_id: uuid.UUID
) -> tuple[Operator, TripOperator | None]:
    op = db.get(Operator, operator_id)
    if op is not None and op.workspace_id == trip.workspace_id:
        return op, None
    # A trip_operator (RFQ row) id is accepted as well.
    row = db.get(TripOperator, operator_id)
    if row is not None and row.workspace_id == trip.workspace_id and row.trip_id == trip.id:
        op = db.get(Operator, row.operator_id)
        if op is not None:
            return op, row
    raise NotFound("Operator not found")


def explicit_quote(db: Session, trip: Trip, quote_id: uuid.UUID) -> Quote:
    """A quote of this trip (404 for other trips and workspaces)."""
    quote = db.get(Quote, quote_id)
    if quote is None or quote.workspace_id != trip.workspace_id or quote.trip_id != trip.id:
        raise NotFound("Quote not found")
    return quote


def explicit_operator(db: Session, trip: Trip, operator_id: uuid.UUID) -> Operator:
    """An operator of the trip's workspace, by operator id or RFQ-row id (404 otherwise)."""
    return _explicit_operator(db, trip, operator_id)[0]


def _create_operator(db: Session, trip: Trip, name: str, sender: str | None) -> Operator:
    _, email, phone = operator_service.parse_sender(sender)
    op = Operator(
        workspace_id=trip.workspace_id,
        name=name[:200],
        normalized_name=operator_service.normalize_operator_name(name)[:200] or "unknown",
        aliases=[],
        email=email,
        email_domain=operator_service.email_domain(email),
        phone=f"+{phone}" if phone else None,
        source=OperatorSource.EXTRACTION,
    )
    db.add(op)
    db.flush()
    return op


def _find_operator(
    db: Session, trip: Trip, doc: SourceDocument, result: ExtractionResult
) -> tuple[Operator, bool]:
    name_field = _field_value(result, "operator_name")
    name = str(name_field.value) if name_field is not None else None
    match = operator_service.match_operator(db, trip.workspace_id, sender=doc.sender, name=name)
    if match is None and name is None:
        # The sender's display name is the next best name to match on.
        match = operator_service.match_operator(
            db, trip.workspace_id, sender=None, name=operator_service.sender_label(doc.sender)
        )
    if match is not None:
        return match.operator, False
    if name_field is not None and name and name_field.confidence >= NEW_OPERATOR_MIN_CONFIDENCE:
        return _create_operator(db, trip, name, doc.sender), True
    label = operator_service.sender_label(doc.sender) or name or "Unknown operator"
    existing = operator_service.match_operator(db, trip.workspace_id, sender=None, name=label)
    if existing is not None:
        return existing.operator, False
    return _create_operator(db, trip, label, doc.sender), True


def _trip_operator(
    db: Session, trip: Trip, operator: Operator, doc: SourceDocument, received: datetime
) -> TripOperator:
    row = db.scalars(
        select(TripOperator).where(
            TripOperator.trip_id == trip.id, TripOperator.operator_id == operator.id
        )
    ).first()
    if row is None:
        # An unsolicited quote: record the RFQ row as requested when it arrived.
        row = TripOperator(
            workspace_id=trip.workspace_id,
            trip_id=trip.id,
            operator_id=operator.id,
            status=TripOperatorStatus.REQUESTED,
            channel=_REQUEST_CHANNELS.get(doc.channel, RequestChannel.OTHER),
            requested_at=received,
        )
        db.add(row)
        db.flush()
    return row


def _responded(row: TripOperator, received: datetime) -> None:
    if row.responded_at is None or received < row.responded_at:
        row.responded_at = received


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
    received = document_time(doc)
    quote: Quote | None = None
    trip_op: TripOperator | None = None
    created_operator = False
    if quote_id is not None:
        quote = explicit_quote(db, trip, quote_id)
        found = db.get(Operator, quote.operator_id)
        if found is None:  # pragma: no cover - FK guarantees it
            raise NotFound("Operator not found")
        operator = found
    elif operator_id is not None:
        operator, trip_op = _explicit_operator(db, trip, operator_id)
    else:
        operator, created_operator = _find_operator(db, trip, doc, result)
    doc.operator_id = operator.id
    if trip_op is None:
        trip_op = _trip_operator(db, trip, operator, doc, received)

    if result.intent == "decline" and quote is None:
        trip_op.status = TripOperatorStatus.DECLINED
        _responded(trip_op, received)
        return QuoteResolution(
            quote=None,
            operator=operator,
            trip_operator=trip_op,
            created_quote=False,
            created_operator=created_operator,
        )

    created_quote = False
    if quote is None:
        quote = db.scalars(
            select(Quote)
            .where(
                Quote.trip_id == trip.id,
                Quote.operator_id == operator.id,
                Quote.status == QuoteStatus.ACTIVE,
            )
            .order_by(Quote.created_at.desc(), Quote.id)
        ).first()
    if quote is None:
        currency = _field_value(result, "currency")
        quote = Quote(
            workspace_id=trip.workspace_id,
            trip_id=trip.id,
            operator_id=operator.id,
            trip_operator_id=trip_op.id,
            status=QuoteStatus.ACTIVE,
            original_currency=str(currency.value).upper()[:3] if currency else "USD",
            created_at=now,
        )
        db.add(quote)
        db.flush()
        created_quote = True
    if quote.trip_operator_id is None:
        quote.trip_operator_id = trip_op.id

    trip_op.status = TripOperatorStatus.QUOTED
    _responded(trip_op, received)
    if quote.first_received_at is None or received < quote.first_received_at:
        quote.first_received_at = received
    if quote.last_received_at is None or received > quote.last_received_at:
        quote.last_received_at = received
    if trip.status in (TripStatus.DRAFT, TripStatus.SOURCING):
        trip.status = TripStatus.QUOTED
    return QuoteResolution(
        quote=quote,
        operator=operator,
        trip_operator=trip_op,
        created_quote=created_quote,
        created_operator=created_operator,
    )


# --------------------------------------------------------------------------- field merge


def item_value(key: str, item: ExtractedField | ExtractedFee) -> Any:
    """The JSON value stored in `quote_fields` for an extracted item (422 when invalid)."""
    if isinstance(item, ExtractedFee):
        value = FeeValue(
            category=item.category,
            label=item.label[:200],
            status=AmountStatus(item.status),
            amount=MoneyValue(amount_minor=item.amount.amount_minor, currency=item.amount.currency)
            if item.amount is not None
            else None,
            unit=item.unit,
            quantity=item.quantity,
            percent=item.percent,
            explicitly_extra=item.explicitly_extra,
            hedged=item.hedged,
        )
        return value.model_dump(mode="json")
    raw: Any = item.value.model_dump(mode="json") if isinstance(item.value, Money) else item.value
    return parse_field_value(key, raw)


def _norm_text(value: str) -> str:
    return " ".join(value.casefold().split())


def same_value(a: Any, b: Any) -> bool:
    """Values equal for corroboration (fee labels and hedging are ignored)."""
    if isinstance(a, dict) and isinstance(b, dict):
        if "category" in a and "category" in b:
            return all(a.get(k) == b.get(k) for k in _FEE_COMPARE_KEYS)
        return a == b
    if isinstance(a, str) and isinstance(b, str):
        return _norm_text(a) == _norm_text(b)
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    return bool(a == b)


def _format_amount(amount: Any) -> str | None:
    if not isinstance(amount, dict) or not isinstance(amount.get("amount_minor"), int):
        return None
    minor = int(amount["amount_minor"])
    whole, cents = divmod(abs(minor), 100)
    text = f"{whole:,}" if cents == 0 else f"{whole:,}.{cents:02d}"
    currency = amount.get("currency")
    prefix = "" if currency in (None, "USD") else f"{currency} "
    return f"{'-' if minor < 0 else ''}{prefix}{text}"


def display_value(value: Any) -> str:
    """Short human form of a stored value, for processing events."""
    if isinstance(value, dict):
        if "category" in value:
            amount = _format_amount(value.get("amount"))
            status = str(value.get("status", ""))
            if amount is None:
                return status.replace("_", " ")
            return amount if status == "stated" else f"{amount} ({status})"
        return _format_amount(value) or str(value)
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def display_key(key: str) -> str:
    if key.startswith("fee.other."):
        return key.removeprefix("fee.other.").replace("_", " ")
    return key.removeprefix("fee.").replace("_", " ")


def _new_field(
    quote: Quote,
    doc: SourceDocument,
    key: str,
    item: ExtractedField | ExtractedFee,
    value: Any,
    result: ExtractionResult,
) -> QuoteField:
    ev = item.evidence
    return QuoteField(
        workspace_id=quote.workspace_id,
        quote_id=quote.id,
        source_document_id=doc.id,
        key=key,
        group=group_for_key(key),
        label=item.label[:200] if isinstance(item, ExtractedFee) else None,
        value_type=value_type_for_key(key),
        original_value=value,
        current_value=value,
        confidence=max(0, min(100, item.confidence)),
        extractor=ExtractorKind(result.extractor),
        extractor_version=result.extractor_version[:64],
        snippet=ev.snippet[:500] if ev.snippet else None,
        page=ev.page,
        char_start=ev.char_start,
        char_end=ev.char_end,
        snippet_verified=ev.verified,
        sequence=item.sequence,
        is_current=True,
        corroborating_source_ids=[],
    )


def current_field(db: Session, quote_id: uuid.UUID, key: str) -> QuoteField | None:
    return db.scalars(
        select(QuoteField).where(
            QuoteField.quote_id == quote_id,
            QuoteField.key == key,
            QuoteField.is_current.is_(True),
        )
    ).first()


def open_candidates(db: Session, quote_id: uuid.UUID, key: str) -> list[QuoteField]:
    """Non-current values of a key that were never superseded: unresolved conflicts."""
    return list(
        db.scalars(
            select(QuoteField)
            .where(
                QuoteField.quote_id == quote_id,
                QuoteField.key == key,
                QuoteField.is_current.is_(False),
                QuoteField.superseded_by_id.is_(None),
            )
            .order_by(QuoteField.created_at, QuoteField.id)
        )
    )


def make_current(db: Session, old: QuoteField | None, new: QuoteField) -> None:
    """Make `new` the current value of its key; `old` (and open conflicts) point at it.

    The partial unique index allows one current row per key, so the old row is
    retired and flushed before the new one is written.
    """
    if old is not None:
        old.is_current = False
        db.flush()
    new.is_current = True
    if new not in db:
        db.add(new)
    db.flush()
    if old is not None:
        old.superseded_by_id = new.id
    for cand in open_candidates(db, new.quote_id, new.key):
        if cand.id != new.id:
            cand.superseded_by_id = new.id
    db.flush()


def _store_non_current(db: Session, new: QuoteField, superseded_by: uuid.UUID | None) -> None:
    new.is_current = False
    new.superseded_by_id = superseded_by
    db.add(new)
    db.flush()


def _time_of(db: Session, field_row: QuoteField, cache: dict[uuid.UUID, datetime]) -> datetime:
    doc_id = field_row.source_document_id
    if doc_id is None:
        return field_row.created_at
    if doc_id not in cache:
        other = db.get(SourceDocument, doc_id)
        cache[doc_id] = document_time(other) if other is not None else field_row.created_at
    return cache[doc_id]


def _is_weaker(new_value: Any, current: QuoteField, review_threshold: int) -> bool:
    if not isinstance(new_value, dict) or not isinstance(current.current_value, dict):
        return False
    try:
        new_status = AmountStatus(str(new_value.get("status")))
        cur_status = AmountStatus(str(current.current_value.get("status")))
    except ValueError:
        return False
    return (
        new_status in _WEAKER_STATUSES
        and cur_status is AmountStatus.STATED
        and current.confidence >= review_threshold
    )


def _already_merged(
    db: Session, quote_id: uuid.UUID, doc_id: uuid.UUID, key: str, sequence: int, value: Any
) -> bool:
    rows = db.scalars(
        select(QuoteField).where(
            QuoteField.quote_id == quote_id,
            QuoteField.key == key,
            QuoteField.source_document_id == doc_id,
            QuoteField.sequence == sequence,
        )
    )
    return any(same_value(r.original_value, value) for r in rows)


def merge_result(
    db: Session,
    quote: Quote,
    doc: SourceDocument,
    result: ExtractionResult,
    *,
    review_threshold: int,
    now: datetime,
) -> MergeReport:
    report = MergeReport()
    items: list[ExtractedField | ExtractedFee] = [
        *(f for f in result.fields if f.value is not None),
        *result.fees,
    ]
    # Within a document, later messages (a fresh reply after quoted text) win.
    items.sort(key=lambda i: i.sequence)
    doc_time = document_time(doc)
    times: dict[uuid.UUID, datetime] = {doc.id: doc_time}
    source = channel_label(doc.channel)

    for item in items:
        key = key_for(item)
        try:
            value = item_value(key, item)
        except Unprocessable:
            report.events.append(f"Skipped an invalid value for {display_key(key)}")
            continue
        if _already_merged(db, quote.id, doc.id, key, item.sequence, value):
            continue  # reprocessing produced the same value again
        new = _new_field(quote, doc, key, item, value, result)
        current = current_field(db, quote.id, key)

        if current is None:
            make_current(db, None, new)
            report.inserted.append(key)
            continue

        same = same_value(current.current_value, value)
        same_doc = current.source_document_id == doc.id
        if same and not same_doc:
            ids = list(current.corroborating_source_ids or [])
            if str(doc.id) not in ids:
                current.corroborating_source_ids = [*ids, str(doc.id)]
                bumped = min(
                    CORROBORATED_CAP, max(current.confidence, new.confidence) + CORROBORATION_BONUS
                )
                current.confidence = max(current.confidence, bumped)
                report.corroborated.append(key)
            continue
        if same:
            continue
        if current.locked:
            _store_non_current(db, new, None)
            report.conflicts.append(key)
            report.events.append(
                f"Conflict: {display_key(key)} {display_value(value)} ({source}) differs from "
                f"the reviewed {display_value(current.current_value)}"
            )
            continue
        newer = (doc_time, item.sequence) > (_time_of(db, current, times), current.sequence)
        if same_doc and item.sequence == current.sequence:
            make_current(db, current, new)  # reprocessed: the new reading replaces the old
            report.replaced.append(key)
            continue
        if not newer:
            _store_non_current(db, new, current.id)
            report.history_only.append(key)
            continue
        if _is_weaker(value, current, review_threshold):
            _store_non_current(db, new, None)
            report.conflicts.append(key)
            report.events.append(
                f"Conflict: {display_key(key)} {display_value(value)} ({source}) is weaker than "
                f"the stated {display_value(current.current_value)}; kept the stated value"
            )
            continue
        previous = current.current_value
        make_current(db, current, new)
        report.superseded.append(key)
        report.events.append(
            f"Revised: {display_key(key)} {display_value(previous)} → "
            f"{display_value(value)} ({source})"
        )
    return report
