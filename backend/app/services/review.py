"""Human review of fields and flags (spec §4 "Reconciling flags", §8 review endpoints).

Every action checks `version` (409 `stale_version` on mismatch), locks the
field, writes an audit entry with before/after, and recomputes the trip in the
same transaction. Flag resolutions that change money write the field too:
`confirmed_amount` creates or edits the fee field (edited, locked),
`accepted_estimate` accepts it, `confirmed_included` edits it to included,
`not_applicable` sets the line to not_applicable.
"""

from __future__ import annotations

import uuid
from typing import Any, Final

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import Conflict, NotFound, Unprocessable
from app.models.base import utcnow
from app.models.document import SourceDocument
from app.models.enums import (
    FLAG_RESOLUTIONS,
    AmountStatus,
    ExtractorKind,
    FeeCategory,
    FieldStatus,
    FlagResolution,
    FlagStatus,
    FlagType,
    QuoteStatus,
)
from app.models.flag import Flag
from app.models.operator import Operator
from app.models.quote import Quote, QuoteField
from app.models.trip import Trip
from app.models.workspace import Workspace
from app.permissions import RequestContext
from app.schemas.field_values import (
    fee_key,
    group_for_key,
    is_fee_key,
    parse_field_value,
    value_type_for_key,
)
from app.schemas.flag import FlagOut
from app.schemas.quote import FieldOut, ReviewQueueItemOut, SourceRefOut
from app.services import audit, merge, recompute
from app.services.contracts import is_material_key
from app.services.fx import load_fx_table, to_usd_cents
from app.services.normalization import CATEGORY_LABELS

_FIELD_AUDITED: Final = (
    "key",
    "current_value",
    "status",
    "locked",
    "review_note",
    "confidence",
    "is_current",
    "superseded_by_id",
)
_FLAG_AUDITED: Final = ("status", "resolution", "resolution_note", "resolved_by_id", "resolved_at")

# --------------------------------------------------------------------------- helpers


def _check_version(field: QuoteField, version: int) -> None:
    if field.version != version:
        raise Conflict(
            f"The field changed since you loaded it (version {field.version}, sent {version})",
            code="stale_version",
        )
    if not field.is_current:
        raise Conflict("Only the current value of a field can be reviewed", code="not_current")


def _quote(db: Session, quote_id: uuid.UUID) -> Quote:
    quote = db.get(Quote, quote_id)
    if quote is None:  # pragma: no cover - FK guarantees it
        raise NotFound("Quote not found")
    return quote


def _trip(db: Session, trip_id: uuid.UUID) -> Trip:
    trip = db.get(Trip, trip_id)
    if trip is None:  # pragma: no cover - FK guarantees it
        raise NotFound("Trip not found")
    return trip


def _snap(field: QuoteField) -> dict[str, Any]:
    return audit.snapshot(field, _FIELD_AUDITED)


def _mark_reviewed(
    field: QuoteField, ctx: RequestContext, status: FieldStatus, note: str | None
) -> None:
    field.status = status
    field.locked = True
    field.reviewed_by_id = ctx.user_id
    field.reviewed_at = utcnow()
    if note is not None:
        field.review_note = note[:1000]


def _finish_field(
    db: Session,
    ctx: RequestContext,
    field: QuoteField,
    action: str,
    before: dict[str, Any] | None,
    *,
    recompute_trip: bool = True,
) -> QuoteField:
    db.flush()
    quote = _quote(db, field.quote_id)
    after = _snap(field)
    if before is not None:
        before, after = audit.diff(before, after)
    audit.record(db, ctx, action, field, before, after, trip_id=quote.trip_id)
    if recompute_trip:
        recompute.recompute_trip(db, _trip(db, quote.trip_id), ctx=ctx)
    return field


# --------------------------------------------------------------------------- field actions


def verify_field(
    db: Session, ctx: RequestContext, field: QuoteField, *, version: int
) -> QuoteField:
    """Status verified, locked; effective confidence becomes 100."""
    _check_version(field, version)
    before = _snap(field)
    _mark_reviewed(field, ctx, FieldStatus.VERIFIED, None)
    return _finish_field(db, ctx, field, "field.verify", before)


def accept_field(
    db: Session, ctx: RequestContext, field: QuoteField, *, version: int, note: str | None
) -> QuoteField:
    """Status accepted, locked; an accepted estimate counts in the known total."""
    _check_version(field, version)
    before = _snap(field)
    _mark_reviewed(field, ctx, FieldStatus.ACCEPTED, note)
    return _finish_field(db, ctx, field, "field.accept", before)


def _validated(key: str, value: Any, label: str | None = None) -> Any:
    """Parse a value for `key`; fee values get their category and label filled in."""
    if is_fee_key(key):
        if not isinstance(value, dict):
            raise Unprocessable(
                f"Invalid value for {key}", code="invalid_field_value", fields={key: "object"}
            )
        category = _category_for_key(key)
        value = {**value}
        value.setdefault("category", category.value)
        if value["category"] != category.value:
            raise Unprocessable(
                f"{key} holds {category.value} fees",
                code="invalid_field_value",
                fields={key: "category mismatch"},
            )
        value.setdefault("label", label or CATEGORY_LABELS.get(category, category.value))
    return parse_field_value(key, value)


def _category_for_key(key: str) -> FeeCategory:
    name = key.removeprefix("fee.").split(".", 1)[0]
    try:
        return FeeCategory(name)
    except ValueError:
        raise Unprocessable(f"Unknown fee key {key!r}", code="unknown_field_key") from None


def edit_field(
    db: Session,
    ctx: RequestContext,
    field: QuoteField,
    *,
    version: int,
    value: Any,
    note: str | None,
) -> QuoteField:
    """Validate `value` for the key, set `current_value`, status edited, locked."""
    _check_version(field, version)
    parsed = _validated(field.key, value, field.label)
    before = _snap(field)
    field.current_value = parsed
    if isinstance(parsed, dict) and parsed.get("label"):
        field.label = str(parsed["label"])[:200]
    _mark_reviewed(field, ctx, FieldStatus.EDITED, note)
    return _finish_field(db, ctx, field, "field.edit", before)


def reset_field(db: Session, ctx: RequestContext, field: QuoteField, *, version: int) -> QuoteField:
    """Back to `original_value`, status extracted, unlocked."""
    _check_version(field, version)
    before = _snap(field)
    field.current_value = field.original_value
    field.status = FieldStatus.EXTRACTED
    field.locked = False
    field.reviewed_by_id = None
    field.reviewed_at = None
    field.review_note = None
    return _finish_field(db, ctx, field, "field.reset", before)


def _insert_manual(
    db: Session,
    ctx: RequestContext,
    quote: Quote,
    key: str,
    parsed: Any,
    label: str | None,
    note: str | None,
) -> tuple[QuoteField, QuoteField | None]:
    current = merge.current_field(db, quote.id, key)
    if isinstance(parsed, dict) and parsed.get("label"):
        label = str(parsed["label"])
    new = QuoteField(
        workspace_id=quote.workspace_id,
        quote_id=quote.id,
        source_document_id=None,
        key=key,
        group=group_for_key(key),
        label=label[:200] if label else None,
        value_type=value_type_for_key(key),
        original_value=parsed,
        current_value=parsed,
        confidence=100,
        extractor=ExtractorKind.MANUAL,
        snippet_verified=True,
        is_current=True,
        corroborating_source_ids=[],
    )
    _mark_reviewed(new, ctx, FieldStatus.EDITED, note)
    merge.make_current(db, current, new)
    return new, current


def add_manual_field(
    db: Session,
    ctx: RequestContext,
    quote: Quote,
    *,
    key: str,
    value: Any,
    label: str | None,
    note: str | None,
) -> QuoteField:
    """Insert a manual current value (extractor manual, edited, locked), superseding
    any current value for the key."""
    if quote.workspace_id != ctx.workspace_id:
        raise NotFound("Quote not found")
    if key == "fee.other":
        key = fee_key(FeeCategory.OTHER, label or "other")
    parsed = _validated(key, value, label)
    new, previous = _insert_manual(db, ctx, quote, key, parsed, label, note)
    before = _snap(previous) if previous is not None else None
    audit.record(
        db,
        ctx,
        "field.add",
        new,
        before,
        _snap(new),
        trip_id=quote.trip_id,
    )
    recompute.recompute_trip(db, _trip(db, quote.trip_id), ctx=ctx)
    return new


def field_history(db: Session, field: QuoteField) -> list[QuoteField]:
    """Every revision of the field's (quote, key), newest first."""
    return list(
        db.scalars(
            select(QuoteField)
            .where(QuoteField.quote_id == field.quote_id, QuoteField.key == field.key)
            .order_by(QuoteField.created_at.desc(), QuoteField.id)
        )
    )


# --------------------------------------------------------------------------- review queue


def _money_cents(value: Any, fx_currency_default: str = "USD") -> int:
    """USD cents of a money value or a fee amount (0 when none)."""
    if isinstance(value, dict) and "category" in value:
        value = value.get("amount")
    if not isinstance(value, dict) or not isinstance(value.get("amount_minor"), int):
        return 0
    currency = str(value.get("currency") or fx_currency_default)
    try:
        return abs(to_usd_cents(int(value["amount_minor"]), currency, load_fx_table()))
    except ValueError:
        return abs(int(value["amount_minor"]))


def _source_ref(db: Session, doc_id: uuid.UUID | None, page: int | None) -> SourceRefOut | None:
    if doc_id is None:
        return None
    doc = db.get(SourceDocument, doc_id)
    if doc is None:
        return None
    return SourceRefOut(
        document_id=doc.id,
        kind=doc.kind,
        channel=doc.channel,
        original_filename=doc.original_filename,
        page=page,
        received_at=doc.received_at,
    )


def allowed_resolutions(flag_type: FlagType) -> list[FlagResolution]:
    """`FLAG_RESOLUTIONS` for the type, plus `dismissed` (with a note), which every flag allows."""
    allowed = list(FLAG_RESOLUTIONS.get(flag_type, ()))
    if FlagResolution.DISMISSED not in allowed:
        allowed.append(FlagResolution.DISMISSED)
    return allowed


def flag_out(flag: Flag) -> FlagOut:
    out = FlagOut.model_validate(flag)
    out.allowed_resolutions = allowed_resolutions(flag.type)
    return out


def _flag_impact(flag: Flag, field: QuoteField | None, quote: Quote) -> int:
    details = flag.details or {}
    for key in ("estimate_cents", "amount_cents"):
        value = details.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            return abs(value)
    if field is not None:
        cents = _money_cents(field.current_value)
        if cents:
            return cents
    if flag.type in (FlagType.TOTAL_MISMATCH,):
        stated, computed = details.get("stated_cents"), details.get("computed_cents")
        if isinstance(stated, int) and isinstance(computed, int):
            return abs(stated - computed)
    # A quote-level problem puts the whole quote at stake.
    return quote.upper_total_cents or quote.known_total_cents or 0


def review_queue(db: Session, ctx: RequestContext, trip: Trip) -> list[ReviewQueueItemOut]:
    """Unlocked material fields below the workspace threshold plus open blocking
    flags, sorted by money impact (largest first)."""
    if trip.workspace_id != ctx.workspace_id:
        raise NotFound("Trip not found")
    workspace = db.get(Workspace, trip.workspace_id)
    threshold = workspace.review_threshold if workspace else ctx.workspace.review_threshold
    quotes = {
        q.id: q
        for q in db.scalars(
            select(Quote).where(Quote.trip_id == trip.id, Quote.status == QuoteStatus.ACTIVE)
        )
    }
    if not quotes:
        return []
    names = {
        op.id: op.name
        for op in db.scalars(
            select(Operator).where(Operator.id.in_({q.operator_id for q in quotes.values()}))
        )
    }
    fields = [
        f
        for f in db.scalars(
            select(QuoteField).where(
                QuoteField.quote_id.in_(list(quotes)),
                QuoteField.is_current.is_(True),
                QuoteField.locked.is_(False),
                QuoteField.confidence < threshold,
            )
        )
        if is_material_key(f.key)
    ]
    flags = list(
        db.scalars(
            select(Flag).where(
                Flag.trip_id == trip.id,
                Flag.quote_id.in_(list(quotes)),
                Flag.status == FlagStatus.OPEN,
                Flag.blocking.is_(True),
            )
        )
    )
    field_by_id = {f.id: f for f in fields}
    items: list[ReviewQueueItemOut] = []
    used_fields: set[uuid.UUID] = set()
    for flag in flags:
        quote = quotes[flag.quote_id] if flag.quote_id else None
        if quote is None:
            continue
        linked = field_by_id.get(flag.field_id) if flag.field_id else None
        flag_field = linked or (db.get(QuoteField, flag.field_id) if flag.field_id else None)
        if linked is not None:
            used_fields.add(linked.id)
        items.append(
            ReviewQueueItemOut(
                kind="field" if linked is not None else "flag",
                quote_id=quote.id,
                operator_name=names.get(quote.operator_id, "Unknown operator"),
                money_impact_cents=_flag_impact(flag, flag_field, quote),
                field=FieldOut.model_validate(linked) if linked is not None else None,
                flag=flag_out(flag),
                source=_source_ref(
                    db,
                    flag.source_document_id
                    or (flag_field.source_document_id if flag_field else None),
                    flag_field.page if flag_field else None,
                ),
            )
        )
    for f in fields:
        if f.id in used_fields:
            continue
        quote = quotes[f.quote_id]
        items.append(
            ReviewQueueItemOut(
                kind="field",
                quote_id=quote.id,
                operator_name=names.get(quote.operator_id, "Unknown operator"),
                money_impact_cents=_money_cents(f.current_value, quote.original_currency),
                field=FieldOut.model_validate(f),
                flag=None,
                source=_source_ref(db, f.source_document_id, f.page),
            )
        )
    items.sort(key=lambda i: (-i.money_impact_cents, i.operator_name, i.kind))
    return items


# --------------------------------------------------------------------------- flags


def _flag_field(db: Session, flag: Flag) -> QuoteField | None:
    """The current field a fee flag is about (by id, else by the category's key)."""
    if flag.field_id is not None:
        row = db.get(QuoteField, flag.field_id)
        if row is not None and row.is_current:
            return row
        if row is not None:
            return merge.current_field(db, row.quote_id, row.key)
    if flag.quote_id is not None and flag.fee_category is not None:
        if flag.fee_category is FeeCategory.OTHER:
            return None
        return merge.current_field(db, flag.quote_id, fee_key(flag.fee_category))
    return None


def _fee_value(
    flag: Flag, field: QuoteField | None, status: AmountStatus, amount_cents: int | None
) -> dict[str, Any]:
    base: dict[str, Any] = dict(field.current_value) if field is not None else {}
    category = flag.fee_category or (
        _category_for_key(field.key) if field is not None else FeeCategory.OTHER
    )
    base["category"] = category.value
    base.setdefault("label", CATEGORY_LABELS.get(category, category.value))
    base["status"] = status.value
    base["hedged"] = False
    if amount_cents is not None:
        base["amount"] = {"amount_minor": amount_cents, "currency": "USD"}
        base["unit"] = "flat"
        base["quantity"] = None
        base["percent"] = None
    elif status in (AmountStatus.INCLUDED, AmountStatus.NOT_APPLICABLE, AmountStatus.WAIVED):
        base["amount"] = None
    return base


def _write_fee(
    db: Session,
    ctx: RequestContext,
    flag: Flag,
    status: AmountStatus,
    amount_cents: int | None,
    note: str | None,
) -> QuoteField:
    field = _flag_field(db, flag)
    if flag.fee_category is None and field is None:
        raise Unprocessable("This flag is not about a fee", code="invalid_resolution")
    quote = _quote(db, flag.quote_id) if flag.quote_id else None
    if quote is None:
        raise Unprocessable("This flag has no quote", code="invalid_resolution")
    value = _fee_value(flag, field, status, amount_cents)
    if field is None:
        category = flag.fee_category or FeeCategory.OTHER
        key = fee_key(category, str(value.get("label", "other")))
        parsed = _validated(key, value)
        new, _ = _insert_manual(db, ctx, quote, key, parsed, str(value["label"]), note)
        audit.record(db, ctx, "field.add", new, None, _snap(new), trip_id=quote.trip_id)
        return new
    before = _snap(field)
    field.current_value = _validated(field.key, value, field.label)
    _mark_reviewed(field, ctx, FieldStatus.EDITED, note)
    db.flush()
    audit.record(
        db, ctx, "field.edit", field, *audit.diff(before, _snap(field)), trip_id=quote.trip_id
    )
    return field


def _write_headline(
    db: Session, ctx: RequestContext, flag: Flag, amount_cents: int, note: str | None
) -> QuoteField:
    if flag.quote_id is None:
        raise Unprocessable("This flag has no quote", code="invalid_resolution")
    quote = _quote(db, flag.quote_id)
    parsed = _validated("headline_price", {"amount_minor": amount_cents, "currency": "USD"})
    new, previous = _insert_manual(db, ctx, quote, "headline_price", parsed, None, note)
    audit.record(
        db,
        ctx,
        "field.add",
        new,
        _snap(previous) if previous is not None else None,
        _snap(new),
        trip_id=quote.trip_id,
    )
    return new


def _resolve_conflict(
    db: Session, ctx: RequestContext, flag: Flag, resolution: FlagResolution, note: str | None
) -> None:
    raw = (flag.details or {}).get("candidate_field_id")
    try:
        candidate = db.get(QuoteField, uuid.UUID(str(raw))) if raw else None
    except ValueError:
        candidate = None
    if candidate is None or candidate.quote_id != flag.quote_id:
        raise Unprocessable("The conflicting value no longer exists", code="invalid_resolution")
    current = merge.current_field(db, candidate.quote_id, candidate.key)
    quote = _quote(db, candidate.quote_id)
    if resolution is FlagResolution.KEEP_CURRENT:
        before = _snap(candidate)
        candidate.superseded_by_id = current.id if current is not None else None
        db.flush()
        audit.record(
            db,
            ctx,
            "field.keep_current",
            candidate,
            *audit.diff(before, _snap(candidate)),
            trip_id=quote.trip_id,
        )
        return
    before = _snap(candidate)
    candidate.superseded_by_id = None
    _mark_reviewed(candidate, ctx, FieldStatus.ACCEPTED, note)
    merge.make_current(db, current, candidate)
    audit.record(
        db,
        ctx,
        "field.use_new_value",
        candidate,
        *audit.diff(before, _snap(candidate)),
        trip_id=quote.trip_id,
    )


def resolve_flag(
    db: Session,
    ctx: RequestContext,
    flag: Flag,
    *,
    resolution: FlagResolution,
    amount_cents: int | None,
    note: str | None,
) -> Flag:
    """422 when `resolution` is not allowed for the flag type (`FLAG_RESOLUTIONS`, plus
    `dismissed` for every type, which needs a note); 409 when the flag is not open."""
    if flag.workspace_id != ctx.workspace_id:
        raise NotFound("Flag not found")
    allowed = allowed_resolutions(flag.type)
    if resolution not in allowed:
        raise Unprocessable(
            f"{resolution.value} is not a valid resolution for {flag.type.value}",
            code="invalid_resolution",
            fields={"resolution": [r.value for r in allowed]},
        )
    if flag.status is not FlagStatus.OPEN:
        raise Conflict("The flag is already resolved", code="flag_not_open")
    if resolution is FlagResolution.DISMISSED and not (note and note.strip()):
        raise Unprocessable(
            "Say why the flag is dismissed", code="note_required", fields={"note": "required"}
        )
    if resolution is FlagResolution.CONFIRMED_AMOUNT and amount_cents is None:
        raise Unprocessable(
            "amount_cents is required to confirm an amount",
            code="amount_required",
            fields={"amount_cents": "required"},
        )
    before = audit.snapshot(flag, _FLAG_AUDITED)

    if resolution is FlagResolution.CONFIRMED_AMOUNT and flag.type is FlagType.HOURLY_ESTIMATE:
        assert amount_cents is not None  # noqa: S101 - checked above
        _write_headline(db, ctx, flag, amount_cents, note)
    elif resolution is FlagResolution.CONFIRMED_AMOUNT:
        _write_fee(db, ctx, flag, AmountStatus.STATED, amount_cents, note)
    elif resolution is FlagResolution.ACCEPTED_ESTIMATE:
        field = _flag_field(db, flag)
        if field is None:
            raise Unprocessable("There is no estimate to accept", code="invalid_resolution")
        field_before = _snap(field)
        _mark_reviewed(field, ctx, FieldStatus.ACCEPTED, note)
        db.flush()
        audit.record(
            db,
            ctx,
            "field.accept",
            field,
            *audit.diff(field_before, _snap(field)),
            trip_id=flag.trip_id,
        )
    elif resolution is FlagResolution.CONFIRMED_INCLUDED:
        _write_fee(db, ctx, flag, AmountStatus.INCLUDED, None, note)
    elif resolution is FlagResolution.NOT_APPLICABLE:
        _write_fee(db, ctx, flag, AmountStatus.NOT_APPLICABLE, None, note)
    elif resolution in (FlagResolution.USE_NEW_VALUE, FlagResolution.KEEP_CURRENT):
        _resolve_conflict(db, ctx, flag, resolution, note)

    flag.status = (
        FlagStatus.DISMISSED if resolution is FlagResolution.DISMISSED else FlagStatus.RESOLVED
    )
    flag.resolution = resolution
    flag.resolution_note = note[:1000] if note else None
    flag.resolved_by_id = ctx.user_id
    flag.resolved_at = utcnow()
    db.flush()
    audit.record(
        db,
        ctx,
        "flag.resolve",
        flag,
        before,
        {**audit.snapshot(flag, _FLAG_AUDITED), "amount_cents": amount_cents},
        trip_id=flag.trip_id,
    )
    recompute.recompute_trip(db, _trip(db, flag.trip_id), ctx=ctx)
    return flag


def reopen_flag(db: Session, ctx: RequestContext, flag: Flag) -> Flag:
    if flag.workspace_id != ctx.workspace_id:
        raise NotFound("Flag not found")
    if flag.status is FlagStatus.OPEN:
        raise Conflict("The flag is already open", code="flag_open")
    before = audit.snapshot(flag, _FLAG_AUDITED)
    flag.status = FlagStatus.OPEN
    flag.resolution = None
    flag.resolution_note = None
    flag.resolved_by_id = None
    flag.resolved_at = None
    db.flush()
    audit.record(
        db,
        ctx,
        "flag.reopen",
        flag,
        before,
        audit.snapshot(flag, _FLAG_AUDITED),
        trip_id=flag.trip_id,
    )
    recompute.recompute_trip(db, _trip(db, flag.trip_id), ctx=ctx)
    return flag
