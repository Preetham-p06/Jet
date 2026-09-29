"""Rebuilding every derived value of a trip (spec §4-5).

For each active quote: build `QuoteState`, get expected fees (rules + learned),
`normalize_quote`, rebuild `fee_lines`, `evaluate_flags` and reconcile them by
fingerprint, observe fees, compute quote confidence. Then `score_trip`,
persist a `Recommendation`, and update quotes' fit, recommendation and
proposal eligibility. Flag reconciliation: open flags are updated; resolved or
dismissed flags stay unless `data_hash` changed and the condition still
holds (reopened, audited `flag.auto_reopen`); open flags whose condition is
gone are resolved `auto_cleared`.
"""

from __future__ import annotations

import dataclasses
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from decimal import Decimal, InvalidOperation
from types import MappingProxyType
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.base import utcnow
from app.models.document import SourceDocument
from app.models.enums import (
    AircraftCategory,
    AmountStatus,
    Availability,
    ExtractionStatus,
    ExtractorKind,
    FeeCategory,
    FeeUnit,
    FlagResolution,
    FlagStatus,
    PricingBasis,
    QuoteStatus,
)
from app.models.flag import Flag
from app.models.intelligence import Recommendation
from app.models.operator import Operator
from app.models.quote import FeeLine, Quote, QuoteField
from app.models.trip import Trip
from app.models.workspace import Workspace
from app.permissions import RequestContext
from app.schemas.field_values import decimal_or_none
from app.services import audit
from app.services.airports import airports_for
from app.services.contracts import (
    CALC_VERSION,
    ConflictState,
    DocumentIssue,
    FeeLineState,
    FieldState,
    FlagSpec,
    LegState,
    QuoteState,
    RankedQuote,
    RecommendationResult,
    RevisionState,
    ScoreBreakdown,
    ScoreInput,
    TripContext,
    TripPreferencesState,
    TrueCost,
    is_material_key,
)
from app.services.fee_intelligence import load_learned, observe_quote
from app.services.fee_rules import expected_fees
from app.services.flags import evaluate_flags
from app.services.fx import load_fx_table
from app.services.merge import same_value
from app.services.normalization import normalize_quote
from app.services.proposals import proposal_eligibility
from app.services.scoring import build_score_input, quote_confidence, score_trip

_FLAG_MESSAGE_MAX = 500


@dataclass(slots=True)
class FlagReconcileReport:
    created: list[Flag] = field(default_factory=list)
    updated: list[Flag] = field(default_factory=list)
    reopened: list[Flag] = field(default_factory=list)
    auto_cleared: list[Flag] = field(default_factory=list)


@dataclass(slots=True)
class _Computed:
    quote: Quote
    state: QuoteState
    true_cost: TrueCost
    specs: list[FlagSpec]
    score_input: ScoreInput


# --------------------------------------------------------------------------- trip context


def _depart_utc(local: datetime, tz: str) -> datetime:
    try:
        zone = ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError):
        zone = ZoneInfo("UTC")
    return local.replace(tzinfo=zone).astimezone(UTC)


def _preferences(raw: Mapping[str, Any] | None) -> TripPreferencesState:
    raw = raw or {}
    categories: list[AircraftCategory] = []
    for value in raw.get("preferred_categories") or []:
        try:
            categories.append(AircraftCategory(value))
        except ValueError:
            continue
    budget = raw.get("max_budget_cents")
    return TripPreferencesState(
        wifi_required=bool(raw.get("wifi_required", False)),
        preferred_categories=tuple(categories),
        catering_required=bool(raw.get("catering_required", False)),
        max_budget_cents=int(budget) if isinstance(budget, int | float) else None,
    )


def build_trip_context(db: Session, trip: Trip, workspace: Workspace) -> TripContext:
    legs = tuple(
        LegState(
            seq=leg.seq,
            origin_icao=leg.origin_icao.upper(),
            destination_icao=leg.destination_icao.upper(),
            depart_local=leg.depart_local,
            depart_tz=leg.depart_tz,
            depart_utc=_depart_utc(leg.depart_local, leg.depart_tz),
        )
        for leg in sorted(trip.legs, key=lambda leg: leg.seq)
    )
    codes = {c for leg in legs for c in (leg.origin_icao, leg.destination_icao)}
    home_bases = db.scalars(
        select(Operator.home_base_icao).where(
            Operator.id.in_(select(Quote.operator_id).where(Quote.trip_id == trip.id)),
            Operator.home_base_icao.is_not(None),
        )
    )
    codes.update(str(c).upper() for c in home_bases if c)
    weights = workspace.scoring_weights
    return TripContext(
        trip_id=trip.id,
        workspace_id=trip.workspace_id,
        reference=trip.reference,
        trip_type=trip.trip_type,
        pax=trip.pax,
        legs=legs,
        preferences=_preferences(trip.preferences),
        review_threshold=workspace.review_threshold,
        airports=MappingProxyType(airports_for(sorted(codes))),
        base_currency=workspace.base_currency,
        scoring_weights={str(k): float(v) for k, v in weights.items()} if weights else None,
    )


# --------------------------------------------------------------------------- quote state


def _money(value: Any) -> tuple[int | None, str | None]:
    if isinstance(value, dict) and isinstance(value.get("amount_minor"), int):
        currency = value.get("currency")
        return int(value["amount_minor"]), str(currency).upper() if currency else None
    return None, None


def _decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return decimal_or_none(value)
    except (InvalidOperation, ValueError):
        return None


def _int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return round(value)
    return None


def _enum(enum_cls: type[Any], value: Any) -> Any:
    if value is None:
        return None
    try:
        return enum_cls(value)
    except ValueError:
        return None


def parse_local_datetime(value: Any) -> datetime | None:
    """ "2026-10-18T09:00" -> naive wall-clock datetime (any offset is dropped)."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    return parsed.replace(tzinfo=None)


def parse_valid_until(value: Any) -> datetime | None:
    """ISO date (end of that day, UTC) or datetime (naive read as UTC) -> aware UTC."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    try:
        if len(text) == 10:
            return datetime.combine(date.fromisoformat(text), time(23, 59, 59), tzinfo=UTC)
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _fee_line(f: QuoteField) -> FeeLineState | None:
    v = f.current_value
    if not isinstance(v, dict):
        return None
    category = _enum(FeeCategory, v.get("category"))
    status = _enum(AmountStatus, v.get("status"))
    if category is None or status is None:
        return None
    amount, currency = _money(v.get("amount"))
    return FeeLineState(
        category=category,
        label=str(v.get("label") or f.label or category.value.replace("_", " ")),
        status=status,
        amount_minor=amount,
        currency=currency,
        unit=_enum(FeeUnit, v.get("unit")) or FeeUnit.FLAT,
        quantity=_decimal(v.get("quantity")),
        percent=_decimal(v.get("percent")),
        explicitly_extra=bool(v.get("explicitly_extra", False)),
        hedged=bool(v.get("hedged", False)),
        confidence=f.confidence,
        review_status=f.status,
        field_id=f.id,
        source_document_id=f.source_document_id,
        page=f.page,
    )


def _current_fields(db: Session, quote: Quote) -> list[QuoteField]:
    return list(
        db.scalars(
            select(QuoteField)
            .where(QuoteField.quote_id == quote.id, QuoteField.is_current.is_(True))
            .order_by(QuoteField.key)
        )
    )


def _conflicts(db: Session, quote: Quote, by_key: Mapping[str, QuoteField]) -> list[ConflictState]:
    rows = db.scalars(
        select(QuoteField)
        .where(
            QuoteField.quote_id == quote.id,
            QuoteField.is_current.is_(False),
            QuoteField.superseded_by_id.is_(None),
        )
        .order_by(QuoteField.created_at, QuoteField.id)
    )
    out: list[ConflictState] = []
    for cand in rows:
        cur = by_key.get(cand.key)
        if cur is None:
            continue
        out.append(
            ConflictState(
                kind="conflict_with_locked" if cur.locked else "conflicting_values",
                key=cand.key,
                current_field_id=cur.id,
                candidate_field_id=cand.id,
                current_value=cur.current_value,
                candidate_value=cand.current_value,
                candidate_source_document_id=cand.source_document_id,
            )
        )
    return out


def _revisions(db: Session, current: Sequence[QuoteField]) -> list[RevisionState]:
    by_id = {f.id: f for f in current if f.extractor is not ExtractorKind.MANUAL}
    if not by_id:
        return []
    rows = db.scalars(
        select(QuoteField)
        .where(QuoteField.superseded_by_id.in_(list(by_id)), QuoteField.is_current.is_(False))
        .order_by(QuoteField.created_at.desc(), QuoteField.id)
    )
    out: list[RevisionState] = []
    seen: set[uuid.UUID] = set()
    for prev in rows:
        cur = by_id[prev.superseded_by_id] if prev.superseded_by_id else None
        if cur is None or cur.id in seen or prev.source_document_id == cur.source_document_id:
            continue
        if same_value(prev.current_value, cur.current_value):
            continue
        seen.add(cur.id)
        out.append(
            RevisionState(
                key=cur.key,
                previous_value=prev.current_value,
                current_value=cur.current_value,
                field_id=cur.id,
                source_document_id=cur.source_document_id,
            )
        )
    return out


def _document_issues(db: Session, quote: Quote) -> list[DocumentIssue]:
    docs = db.scalars(
        select(SourceDocument)
        .where(
            SourceDocument.quote_id == quote.id,
            SourceDocument.extraction_status.in_(
                [ExtractionStatus.FAILED, ExtractionStatus.NEEDS_MANUAL]
            ),
        )
        .order_by(SourceDocument.created_at, SourceDocument.id)
    )
    out: list[DocumentIssue] = []
    for d in docs:
        manual = d.extraction_status is ExtractionStatus.NEEDS_MANUAL
        name = d.original_filename or "document"
        default = (
            f"{name} has no text layer and no OCR is configured; enter the values by hand"
            if manual
            else f"Extraction failed for {name}"
        )
        out.append(
            DocumentIssue(
                kind="ocr_unavailable" if manual else "extraction_failed",
                source_document_id=d.id,
                message=(d.extraction_error or default)[:300] if not manual else default,
            )
        )
    return out


def build_quote_state(db: Session, quote: Quote) -> QuoteState:
    """Current fields -> QuoteState, plus conflicts, revisions and document issues."""
    current = _current_fields(db, quote)
    by_key = {f.key: f for f in current}

    def val(key: str) -> Any:
        f = by_key.get(key)
        return f.current_value if f is not None else None

    headline, head_ccy = _money(val("headline_price"))
    hourly, hourly_ccy = _money(val("hourly_rate"))
    stated, stated_ccy = _money(val("stated_total"))
    currency_field = val("currency")
    currency = (
        head_ccy
        or hourly_ccy
        or stated_ccy
        or (str(currency_field).upper() if isinstance(currency_field, str) else None)
        or quote.original_currency
        or "USD"
    )
    basis = PricingBasis.HOURLY if headline is None and hourly is not None else PricingBasis.FLAT
    operator = db.get(Operator, quote.operator_id)
    wifi = val("wifi")
    all_in = val("all_in")
    model = val("aircraft_model")
    tail = val("tail_number")

    fees = tuple(ln for f in current if f.key.startswith("fee.") if (ln := _fee_line(f)))
    fields = tuple(
        FieldState(
            field_id=f.id,
            key=f.key,
            group=f.group,
            value=f.current_value,
            confidence=f.confidence,
            status=f.status,
            snippet_verified=f.snippet_verified or f.source_document_id is None,
            source_document_id=f.source_document_id,
            page=f.page,
        )
        for f in current
    )
    return QuoteState(
        quote_id=quote.id,
        operator_id=quote.operator_id,
        operator_name=operator.name if operator is not None else "Unknown operator",
        status=quote.status,
        currency=currency,
        pricing_basis=basis,
        created_at=quote.created_at,
        headline_minor=headline,
        hourly_rate_minor=hourly,
        billable_hours=_decimal(val("billable_hours")),
        daily_minimum_hours=_decimal(val("daily_minimum_hours")),
        stated_total_minor=stated,
        all_in=all_in is True,
        fees=fees,
        aircraft_model=str(model) if isinstance(model, str) and model.strip() else None,
        aircraft_category=_enum(AircraftCategory, val("aircraft_category")),
        tail_number=str(tail)[:16] if isinstance(tail, str) and tail.strip() else None,
        seats=_int(val("seats")),
        wifi=wifi if isinstance(wifi, bool) else None,
        flight_time_minutes=_int(val("flight_time_minutes")),
        departure_local=parse_local_datetime(val("departure_local")),
        availability=_enum(Availability, val("availability")),
        valid_until=parse_valid_until(val("valid_until")),
        base_airport_icao=None,
        operator_home_base_icao=operator.home_base_icao if operator is not None else None,
        fields=fields,
        conflicts=tuple(_conflicts(db, quote, by_key)),
        revisions=tuple(_revisions(db, current)),
        document_issues=tuple(_document_issues(db, quote)),
        first_received_at=quote.first_received_at,
        last_received_at=quote.last_received_at,
    )


# --------------------------------------------------------------------------- flags


def _flag_snapshot(flag: Flag) -> dict[str, Any]:
    return audit.snapshot(
        flag, ("status", "resolution", "resolution_note", "severity", "blocking", "data_hash")
    )


def _apply_spec(flag: Flag, spec: FlagSpec, data_hash: str) -> None:
    flag.type = spec.type
    flag.severity = spec.severity
    flag.blocking = spec.is_blocking
    flag.message = spec.message[:_FLAG_MESSAGE_MAX]
    flag.details = audit.jsonable(dict(spec.details))
    flag.field_id = spec.field_id
    flag.fee_category = spec.fee_category
    flag.source_document_id = spec.source_document_id
    flag.data_hash = data_hash


def reconcile_flags(
    db: Session,
    quote: Quote,
    specs: Sequence[FlagSpec],
    *,
    now: datetime,
    ctx: RequestContext | None = None,
) -> FlagReconcileReport:
    report = FlagReconcileReport()
    existing = {
        f.fingerprint: f
        for f in db.scalars(select(Flag).where(Flag.quote_id == quote.id).order_by(Flag.created_at))
    }
    wanted: dict[str, FlagSpec] = {}
    for spec in specs:
        wanted.setdefault(spec.fingerprint[:200], spec)

    for fingerprint, spec in wanted.items():
        data_hash = spec.data_hash()
        flag = existing.get(fingerprint)
        if flag is None:
            flag = Flag(
                workspace_id=quote.workspace_id,
                trip_id=quote.trip_id,
                quote_id=quote.id,
                fingerprint=fingerprint,
                status=FlagStatus.OPEN,
            )
            _apply_spec(flag, spec, data_hash)
            db.add(flag)
            report.created.append(flag)
        elif flag.status is FlagStatus.OPEN:
            _apply_spec(flag, spec, data_hash)
            report.updated.append(flag)
        elif flag.resolution is FlagResolution.AUTO_CLEARED or flag.data_hash != data_hash:
            # The condition came back, or its data changed after a human resolved it.
            before = _flag_snapshot(flag)
            human = flag.resolution is not FlagResolution.AUTO_CLEARED
            _apply_spec(flag, spec, data_hash)
            flag.status = FlagStatus.OPEN
            flag.resolution = None
            flag.resolution_note = None
            flag.resolved_by_id = None
            flag.resolved_at = None
            report.reopened.append(flag)
            if human:
                audit.record(
                    db,
                    None,
                    "flag.auto_reopen",
                    flag,
                    before,
                    _flag_snapshot(flag),
                    trip_id=quote.trip_id,
                    workspace_id=quote.workspace_id,
                    actor_label="system",
                )
    for fingerprint, flag in existing.items():
        if fingerprint in wanted or flag.status is not FlagStatus.OPEN:
            continue
        flag.status = FlagStatus.RESOLVED
        flag.resolution = FlagResolution.AUTO_CLEARED
        flag.resolved_at = now
        flag.resolved_by_id = None
        report.auto_cleared.append(flag)
    db.flush()
    return report


# --------------------------------------------------------------------------- per quote


def _fee_line_rows(quote: Quote, true_cost: TrueCost) -> list[FeeLine]:
    return [
        FeeLine(
            workspace_id=quote.workspace_id,
            quote_id=quote.id,
            field_id=ln.field_id,
            category=ln.category,
            label=ln.label[:200],
            amount_status=ln.amount_status,
            included_by=ln.included_by,
            amount_cents=ln.amount_cents,
            original_amount_minor=ln.original_amount_minor,
            original_currency=ln.original_currency,
            unit=ln.unit,
            quantity=ln.quantity,
            percent=ln.percent,
            explicitly_extra=ln.explicitly_extra,
            counts_in_known=ln.counts_in_known,
            counts_in_upper=ln.counts_in_upper,
            estimate_cents=ln.estimate_cents,
            estimate_basis=ln.estimate_basis,
            confidence=ln.confidence,
            review_status=ln.review_status,
            source_document_id=ln.source_document_id,
            page=ln.page,
            sort_order=ln.sort_order,
        )
        for ln in true_cost.lines
    ]


def _open_flag_counts(db: Session, quote: Quote) -> tuple[int, int]:
    flags = db.scalars(
        select(Flag).where(Flag.quote_id == quote.id, Flag.status == FlagStatus.OPEN)
    ).all()
    blocking = sum(1 for f in flags if f.blocking)
    return blocking, len(flags) - blocking


def _pending_review(state: QuoteState, threshold: int) -> int:
    return sum(
        1
        for f in state.fields
        if is_material_key(f.key) and not f.is_reviewed and f.confidence < threshold
    )


def _recompute_quote(
    db: Session,
    quote: Quote,
    trip_ctx: TripContext,
    *,
    now: datetime,
    ctx: RequestContext | None,
) -> _Computed:
    state = build_quote_state(db, quote)
    learned = load_learned(
        db,
        quote.workspace_id,
        trip_ctx.first_leg.origin_icao,
        trip_ctx.departure_month,
        exclude_quote_id=quote.id,
    )
    expected = expected_fees(state, trip_ctx, learned=learned)
    true_cost = normalize_quote(state, trip_ctx, load_fx_table(), expected)
    specs = evaluate_flags(state, trip_ctx, true_cost, expected, now, learned=learned)
    reconcile_flags(db, quote, specs, now=now, ctx=ctx)
    blocking, info = _open_flag_counts(db, quote)
    # Open blocking flags keep the quote "+" even when the numbers are complete.
    true_cost = dataclasses.replace(
        true_cost, is_fully_priced=true_cost.is_fully_priced and blocking == 0
    )
    low, mean = quote_confidence(state, trip_ctx.review_threshold)

    quote.fee_lines = _fee_line_rows(quote, true_cost)
    quote.original_currency = state.currency[:3]
    quote.pricing_basis = state.pricing_basis
    quote.headline_cents = true_cost.headline_cents
    quote.known_total_cents = true_cost.known_total_cents
    quote.upper_total_cents = true_cost.upper_total_cents
    quote.is_fully_priced = true_cost.is_fully_priced
    quote.open_blocking_flags = blocking
    quote.open_info_flags = info
    quote.pending_review_count = _pending_review(state, trip_ctx.review_threshold)
    quote.quote_confidence = low
    quote.confidence_mean = mean
    quote.aircraft_model = state.aircraft_model[:120] if state.aircraft_model else None
    quote.aircraft_category = state.aircraft_category
    quote.tail_number = state.tail_number
    quote.seats = state.seats
    quote.wifi = state.wifi
    quote.flight_time_minutes = state.flight_time_minutes
    quote.departure_local = state.departure_local
    quote.availability = state.availability
    quote.computed_at = now
    quote.calc_version = CALC_VERSION
    db.flush()
    if quote.status is QuoteStatus.ACTIVE:
        observe_quote(db, quote, trip_ctx, true_cost, now=now)

    score_input = build_score_input(
        state, true_cost, open_blocking_flags=blocking, quote_confidence=low
    )
    return _Computed(quote, state, true_cost, specs, score_input)


def recompute_quote(
    db: Session, quote: Quote, trip_ctx: TripContext, *, now: datetime
) -> tuple[TrueCost, list[FlagSpec]]:
    """Normalize one quote, rebuild its fee lines and reconcile its flags."""
    computed = _recompute_quote(db, quote, trip_ctx, now=now, ctx=None)
    return computed.true_cost, computed.specs


# --------------------------------------------------------------------------- trip


def breakdown_json(breakdown: ScoreBreakdown) -> dict[str, Any]:
    """`Quote.fit_breakdown` shape (ScoreBreakdownOut without labels)."""
    return {
        "fit": breakdown.fit,
        "signals": [
            {
                "key": s.signal.value,
                "weight": s.weight,
                "raw": s.raw,
                "value": s.value,
                "imputed": s.imputed,
                "dropped": s.dropped,
                "detail": s.detail,
            }
            for s in breakdown.signals
        ],
        "schedule_subscore": breakdown.schedule_subscore,
    }


def _reasons(ranked: RankedQuote) -> list[dict[str, str]]:
    return [{"code": r.code.value, "message": r.message} for r in ranked.eligibility.reasons]


def ranking_json(result: RecommendationResult) -> dict[str, Any]:
    """`Recommendation.ranking` shape: per quote fit, eligibility, reasons, signals; checks."""
    return {
        "ranking": [
            {
                "quote_id": str(r.quote_id),
                "rank": r.rank,
                "fit": r.breakdown.fit,
                "eligible": r.eligibility.eligible,
                "reasons": _reasons(r),
                "signals": breakdown_json(r.breakdown)["signals"],
            }
            for r in result.ranking
        ],
        "checks": [{"key": c.key, "label": c.label, "passed": c.passed} for c in result.checks],
    }


def recompute_trip(
    db: Session,
    trip: Trip,
    *,
    now: datetime | None = None,
    ctx: RequestContext | None = None,
) -> RecommendationResult | None:
    """Recompute every quote of the trip and the recommendation; None without quotes."""
    now = now or utcnow()
    stmt = select(Quote).where(Quote.trip_id == trip.id).order_by(Quote.created_at, Quote.id)
    quotes = list(db.scalars(stmt))
    if not quotes:
        return None
    workspace = db.get(Workspace, trip.workspace_id)
    if workspace is None:  # pragma: no cover - FK guarantees it
        raise LookupError("workspace not found")
    trip_ctx = build_trip_context(db, trip, workspace)
    computed = [_recompute_quote(db, q, trip_ctx, now=now, ctx=ctx) for q in quotes]
    result = score_trip([c.score_input for c in computed], trip_ctx)

    for c in computed:
        ranked = result.for_quote(c.quote.id)
        c.quote.fit_score = ranked.breakdown.fit if ranked else None
        c.quote.fit_breakdown = breakdown_json(ranked.breakdown) if ranked else None
        c.quote.is_recommended = result.recommended_quote_id == c.quote.id
    db.flush()
    for c in computed:
        elig = proposal_eligibility(db, c.quote, trip, review_threshold=workspace.review_threshold)
        c.quote.eligible_for_proposal = bool(elig.eligible)
        c.quote.eligibility_reasons = [
            {"code": r.code.value, "message": r.message} for r in elig.reasons
        ]
    db.add(
        Recommendation(
            workspace_id=trip.workspace_id,
            trip_id=trip.id,
            recommended_quote_id=result.recommended_quote_id,
            algorithm_version=result.algorithm_version,
            weights={s.value: float(w) for s, w in result.weights.items()},
            ranking=ranking_json(result),
            computed_at=now,
        )
    )
    db.flush()
    return result
