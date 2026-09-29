"""Read models shared by several route modules: quote detail, comparison and
recommendation views. They only read rows written by the services."""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import SourceDocument
from app.models.enums import (
    FEE_CATEGORY_ORDER,
    AmountStatus,
    FlagStatus,
    QuoteStatus,
)
from app.models.flag import Flag
from app.models.intelligence import Recommendation
from app.models.operator import Operator
from app.models.quote import FeeLine, Quote, QuoteField
from app.models.trip import Trip
from app.permissions import RequestContext, scoped
from app.schemas.meta import FEE_CATEGORY_LABELS
from app.schemas.quote import (
    ComparisonCellOut,
    ComparisonOut,
    ComparisonRowOut,
    FeeColumnOut,
    FeeLineOut,
    FieldOut,
    QuoteDetailOut,
    QuoteSummaryOut,
    SourceRefOut,
)
from app.schemas.recommendation import (
    CheckOut,
    RankingEntryOut,
    ReasonOut,
    RecommendationOut,
    ScoreBreakdownOut,
    SignalOut,
)
from app.services.contracts import SIGNAL_LABELS, Signal
from app.services.review import flag_out

# When several lines share a category, the cell shows the least certain status.
_STATUS_PRIORITY: tuple[AmountStatus, ...] = (
    AmountStatus.NOT_STATED,
    AmountStatus.ESTIMATED,
    AmountStatus.STATED,
    AmountStatus.INCLUDED,
    AmountStatus.WAIVED,
    AmountStatus.NOT_APPLICABLE,
)


def field_out(field: QuoteField) -> FieldOut:
    return FieldOut.model_validate(field)


def operator_names(db: Session, operator_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, str]:
    ids = set(operator_ids)
    if not ids:
        return {}
    return dict(db.execute(select(Operator.id, Operator.name).where(Operator.id.in_(ids))).all())


def quote_summaries(db: Session, quotes: Sequence[Quote]) -> list[QuoteSummaryOut]:
    """Summary rows with `operator_name` filled in."""
    names = operator_names(db, (q.operator_id for q in quotes))
    return [QuoteSummaryOut.from_row(q, operator_name=names.get(q.operator_id, "")) for q in quotes]


class SourceRefs:
    """Lazily loaded `SourceRefOut`s by document id."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._docs: dict[uuid.UUID, SourceDocument | None] = {}

    def preload(self, ids: Iterable[uuid.UUID | None]) -> None:
        missing = {i for i in ids if i is not None and i not in self._docs}
        if missing:
            for doc in self._db.scalars(
                select(SourceDocument).where(SourceDocument.id.in_(missing))
            ):
                self._docs[doc.id] = doc
            for i in missing:
                self._docs.setdefault(i, None)

    def ref(self, doc_id: uuid.UUID | None, page: int | None = None) -> SourceRefOut | None:
        if doc_id is None:
            return None
        self.preload([doc_id])
        doc = self._docs.get(doc_id)
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


# --------------------------------------------------------------------------- fit breakdown


def _signal_out(raw: Mapping[str, Any]) -> SignalOut | None:
    key = raw.get("key") or raw.get("signal")
    if not isinstance(key, str):
        return None
    try:
        label = SIGNAL_LABELS[Signal(key)]
    except ValueError:
        label = key.replace("_", " ").capitalize()
    return SignalOut(
        key=key,
        label=str(raw.get("label") or label),
        weight=float(raw.get("weight") or 0),
        raw=raw.get("raw"),
        value=raw.get("value"),
        imputed=bool(raw.get("imputed", False)),
        dropped=bool(raw.get("dropped", False)),
        detail=raw.get("detail"),
    )


def signals_out(raw: Any) -> list[SignalOut]:
    if not isinstance(raw, list):
        return []
    return [s for s in (_signal_out(r) for r in raw if isinstance(r, Mapping)) if s is not None]


def breakdown_out(raw: Any, fit: int | None = None) -> ScoreBreakdownOut | None:
    if not isinstance(raw, Mapping):
        return None
    return ScoreBreakdownOut(
        fit=raw.get("fit", fit),
        signals=signals_out(raw.get("signals")),
        schedule_subscore=raw.get("schedule_subscore"),
    )


def reasons_out(raw: Any) -> list[ReasonOut]:
    if not isinstance(raw, list):
        return []
    return [
        ReasonOut(code=str(r.get("code", "")), message=str(r.get("message", "")))
        for r in raw
        if isinstance(r, Mapping)
    ]


# --------------------------------------------------------------------------- quote detail


def quote_detail(db: Session, quote: Quote) -> QuoteDetailOut:
    summary = quote_summaries(db, [quote])[0]
    fields = db.scalars(
        select(QuoteField)
        .where(QuoteField.quote_id == quote.id, QuoteField.is_current.is_(True))
        .order_by(QuoteField.group, QuoteField.key, QuoteField.created_at)
    ).all()
    lines = db.scalars(
        select(FeeLine).where(FeeLine.quote_id == quote.id).order_by(FeeLine.sort_order)
    ).all()
    flags = db.scalars(
        select(Flag)
        .where(Flag.quote_id == quote.id)
        .order_by(Flag.blocking.desc(), Flag.created_at, Flag.id)
    ).all()
    docs = db.scalars(
        select(SourceDocument)
        .where(SourceDocument.quote_id == quote.id)
        .order_by(SourceDocument.received_at, SourceDocument.created_at)
    ).all()
    return QuoteDetailOut(
        **summary.model_dump(),
        fields=[field_out(f) for f in fields],
        fee_lines=[FeeLineOut.model_validate(line) for line in lines],
        flags=[flag_out(f) for f in flags],
        sources=[
            SourceRefOut(
                document_id=d.id,
                kind=d.kind,
                channel=d.channel,
                original_filename=d.original_filename,
                received_at=d.received_at,
            )
            for d in docs
        ],
        fit_breakdown=breakdown_out(quote.fit_breakdown, quote.fit_score),
    )


# --------------------------------------------------------------------------- comparison


def _row_order(q: Quote) -> tuple[Any, ...]:
    return (
        not q.is_recommended,
        not q.eligible_for_proposal,
        -(q.fit_score if q.fit_score is not None else -1),
        q.known_total_cents if q.known_total_cents is not None else 1 << 62,
        q.created_at,
        str(q.id),
    )


def _cell(category: Any, lines: Sequence[FeeLine], sources: SourceRefs) -> ComparisonCellOut:
    if not lines:
        return ComparisonCellOut(
            category=category,
            amount_status=None,
            amount_cents=None,
            estimate_cents=None,
            included_by=None,
            confidence=None,
            review_status=None,
            field_id=None,
            source=None,
            line_count=0,
        )
    statuses = {line.amount_status for line in lines}
    status = next(s for s in _STATUS_PRIORITY if s in statuses)
    amounts = [line.amount_cents for line in lines if line.amount_cents is not None]
    estimates = [line.estimate_cents for line in lines if line.estimate_cents is not None]
    confidences = [line.confidence for line in lines if line.confidence is not None]
    first = lines[0]
    return ComparisonCellOut(
        category=category,
        amount_status=status,
        amount_cents=sum(amounts) if amounts else None,
        estimate_cents=sum(estimates) if estimates else None,
        included_by=next((ln.included_by for ln in lines if ln.included_by), None),
        confidence=min(confidences) if confidences else None,
        review_status=first.review_status,
        field_id=first.field_id if len(lines) == 1 else None,
        source=sources.ref(first.source_document_id, first.page),
        line_count=len(lines),
    )


def comparison(db: Session, ctx: RequestContext, trip: Trip) -> ComparisonOut:
    quotes = sorted(
        db.scalars(
            scoped(select(Quote), ctx).where(
                Quote.trip_id == trip.id, Quote.status == QuoteStatus.ACTIVE
            )
        ).all(),
        key=_row_order,
    )
    ids = [q.id for q in quotes]
    lines = (
        db.scalars(
            select(FeeLine).where(FeeLine.quote_id.in_(ids)).order_by(FeeLine.sort_order)
        ).all()
        if ids
        else []
    )
    open_flags = (
        db.scalars(
            select(Flag)
            .where(Flag.quote_id.in_(ids), Flag.status == FlagStatus.OPEN)
            .order_by(Flag.blocking.desc(), Flag.created_at, Flag.id)
        ).all()
        if ids
        else []
    )
    sources = SourceRefs(db)
    sources.preload(line.source_document_id for line in lines)

    present = {line.category for line in lines}
    columns = [c for c in FEE_CATEGORY_ORDER if c in present]
    summaries = {s.id: s for s in quote_summaries(db, quotes)}
    rows = []
    for quote in quotes:
        mine = [line for line in lines if line.quote_id == quote.id]
        added = (
            quote.known_total_cents - quote.headline_cents
            if quote.known_total_cents is not None and quote.headline_cents is not None
            else None
        )
        rows.append(
            ComparisonRowOut(
                quote=summaries[quote.id],
                fees=[_cell(c, [ln for ln in mine if ln.category == c], sources) for c in columns],
                added_charges_cents=added,
                open_flags=[flag_out(f) for f in open_flags if f.quote_id == quote.id],
            )
        )
    recommended = next((q.id for q in quotes if q.is_recommended), None)
    return ComparisonOut(
        trip_id=trip.id,
        review_threshold=ctx.workspace.review_threshold,
        fee_columns=[FeeColumnOut(category=c, label=FEE_CATEGORY_LABELS[c]) for c in columns],
        rows=rows,
        recommended_quote_id=recommended,
    )


# --------------------------------------------------------------------------- recommendation


def recommendation(db: Session, ctx: RequestContext, trip: Trip) -> RecommendationOut:
    """The latest persisted scoring run, joined with the quotes' derived columns."""
    rec = db.scalars(
        scoped(select(Recommendation), ctx)
        .where(Recommendation.trip_id == trip.id)
        .order_by(Recommendation.computed_at.desc(), Recommendation.created_at.desc())
        .limit(1)
    ).first()
    quotes = db.scalars(
        scoped(select(Quote), ctx).where(
            Quote.trip_id == trip.id, Quote.status == QuoteStatus.ACTIVE
        )
    ).all()
    names = operator_names(db, (q.operator_id for q in quotes))
    by_id = {q.id: q for q in quotes}

    payload: Mapping[str, Any] = rec.ranking if rec is not None and rec.ranking else {}
    raw_entries = payload.get("ranking") if isinstance(payload, Mapping) else None
    persisted: dict[uuid.UUID, Mapping[str, Any]] = {}
    for entry in raw_entries if isinstance(raw_entries, list) else []:
        if not isinstance(entry, Mapping):
            continue
        try:
            persisted[uuid.UUID(str(entry.get("quote_id")))] = entry
        except ValueError:
            continue

    def order(q: Quote) -> tuple[Any, ...]:
        entry = persisted.get(q.id)
        rank = entry.get("rank") if entry else None
        return (rank if isinstance(rank, int) else 1 << 30, *_row_order(q))

    ranking = []
    for i, quote in enumerate(sorted(quotes, key=order), start=1):
        entry = persisted.get(quote.id, {})
        breakdown = breakdown_out(quote.fit_breakdown, quote.fit_score)
        signals = signals_out(entry.get("signals")) if "signals" in entry else None
        if signals is None:
            signals = breakdown.signals if breakdown else []
        reasons = entry.get("reasons") if "reasons" in entry else quote.eligibility_reasons
        eligible = entry.get("eligible")
        ranking.append(
            RankingEntryOut(
                quote_id=quote.id,
                operator_name=names.get(quote.operator_id, ""),
                rank=i,
                fit_score=entry.get("fit", quote.fit_score),
                eligible=bool(eligible) if eligible is not None else not reasons,
                reasons=reasons_out(reasons),
                signals=signals,
                known_total_cents=quote.known_total_cents,
                upper_total_cents=quote.upper_total_cents,
                is_fully_priced=quote.is_fully_priced,
                quote_confidence=quote.quote_confidence,
            )
        )

    checks_raw = payload.get("checks") if isinstance(payload, Mapping) else None
    checks = [
        CheckOut(key=str(c.get("key")), label=str(c.get("label")), passed=bool(c.get("passed")))
        for c in (checks_raw if isinstance(checks_raw, list) else [])
        if isinstance(c, Mapping)
    ]
    recommended = rec.recommended_quote_id if rec is not None else None
    if recommended is not None and recommended not in by_id:
        recommended = None
    return RecommendationOut(
        trip_id=trip.id,
        algorithm_version=rec.algorithm_version if rec is not None else "",
        weights={str(k): float(v) for k, v in (rec.weights if rec is not None else {}).items()},
        recommended_quote_id=recommended,
        computed_at=rec.computed_at if rec is not None else None,
        checks=checks,
        ranking=ranking,
    )
