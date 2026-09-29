"""Proposals (spec §6): eligibility, pricing, lifecycle, snapshots and the public view.

Eligible quotes are active, have a headline, no open blocking flags, are
fully priced, seat the pax, and every material field below threshold is
locked. client_total = round_half_up(cost_basis x (1 + markup/100)) in whole
dollars with cost_basis = known_total (`money.apply_markup`).

Lifecycle: draft -> sent -> accepted -> booked; sent may become declined,
cancelled or superseded; drafts may be cancelled. `send` re-checks
eligibility (409 with reasons), freezes snapshots, creates the share token
(`secrets.token_urlsafe(32)`) valid `SHARE_LINK_TTL_DAYS`. Sent proposals are
immutable; `revise` clones into a new draft and supersedes the old one (its
link then returns 410). `mark_booked` books the trip. Every transition is
audited.
"""

from __future__ import annotations

import re
import secrets
import uuid
from collections.abc import Iterable, Sequence
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Final

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.config import Settings
from app.db import set_workspace
from app.errors import Conflict, Gone, NotFound, Unprocessable
from app.extraction.rules.aircraft import canonical_model
from app.models.document import SourceDocument
from app.models.enums import (
    ActorKind,
    AircraftCategory,
    Availability,
    ProposalStatus,
    QuoteStatus,
    TripStatus,
)
from app.models.operator import Operator
from app.models.proposal import Proposal, ProposalOption
from app.models.quote import Quote, QuoteField
from app.models.trip import Trip
from app.models.workspace import Workspace
from app.permissions import RequestContext, scoped
from app.schemas.meta import AIRCRAFT_CATEGORY_LABELS
from app.schemas.proposal import (
    BrokerFeeLineOut,
    ProposalCreate,
    ProposalOptionOut,
    ProposalOut,
    ProposalPatch,
    ProposalSummaryOut,
    PublicLegOut,
    PublicOptionOut,
    PublicProposalOut,
)
from app.schemas.quote import SourceRefOut
from app.schemas.recommendation import ReasonOut
from app.services import audit, money
from app.services.airports import get_airport
from app.services.contracts import (
    Eligibility,
    EligibilityReason,
    IneligibilityCode,
    is_material_key,
)

_PROPOSAL_FIELDS: Final = (
    "status",
    "title",
    "client_name",
    "message",
    "markup_pct",
    "share_enabled",
    "share_expires_at",
    "sent_at",
    "accepted_at",
    "accepted_option_id",
    "accepted_by_name",
    "booked_at",
    "declined_at",
    "cancelled_at",
    "supersedes_id",
)

#: Statuses whose share link can be rotated or revoked.
_LINK_STATUSES: Final = frozenset(
    {ProposalStatus.SENT, ProposalStatus.ACCEPTED, ProposalStatus.BOOKED, ProposalStatus.DECLINED}
)

_NOT_FOUND = "Proposal not found"
_TOKEN_SPLIT = re.compile(r"[^0-9A-Za-z]+")


# --------------------------------------------------------------------------- eligibility


def proposal_eligibility(
    db: Session, quote: Quote, trip: Trip, *, review_threshold: int
) -> Eligibility:
    """Spec §6 gate. Trusts the derived quote columns written by recompute."""
    reasons: list[EligibilityReason] = []

    def add(code: IneligibilityCode, message: str) -> None:
        reasons.append(EligibilityReason(code=code, message=message))

    if quote.status is not QuoteStatus.ACTIVE:
        add(IneligibilityCode.NOT_ACTIVE, f"Quote is {quote.status.value}")
    if quote.headline_cents is None:
        add(IneligibilityCode.NO_HEADLINE, "No headline price")
    if quote.open_blocking_flags > 0:
        n = quote.open_blocking_flags
        add(IneligibilityCode.BLOCKING_FLAGS, f"{n} open blocking flag{'s' if n != 1 else ''}")
    if not quote.is_fully_priced or quote.known_total_cents is None:
        add(IneligibilityCode.NOT_FULLY_PRICED, "Not fully priced")
    if quote.seats is None:
        add(IneligibilityCode.INSUFFICIENT_CAPACITY, "Seat count unknown")
    elif quote.seats < trip.pax:
        add(
            IneligibilityCode.INSUFFICIENT_CAPACITY,
            f"{quote.seats} seats for {trip.pax} passengers",
        )
    if quote.availability is Availability.UNAVAILABLE:
        add(IneligibilityCode.UNAVAILABLE, "Aircraft unavailable")

    unreviewed = _unreviewed_low_confidence(db, quote, review_threshold)
    if unreviewed:
        add(
            IneligibilityCode.UNREVIEWED_LOW_CONFIDENCE,
            "Needs review: " + ", ".join(unreviewed),
        )
    return Eligibility.blocked(*reasons)


def _unreviewed_low_confidence(db: Session, quote: Quote, threshold: int) -> list[str]:
    rows = db.scalars(
        select(QuoteField)
        .where(
            QuoteField.quote_id == quote.id,
            QuoteField.is_current.is_(True),
            QuoteField.locked.is_(False),
            QuoteField.confidence < threshold,
        )
        .order_by(QuoteField.key)
    )
    return [f"{f.label or f.key} ({f.confidence})" for f in rows if is_material_key(f.key)]


def _reasons_json(elig: Eligibility) -> list[dict[str, str]]:
    return [{"code": r.code.value, "message": r.message} for r in elig.reasons]


# --------------------------------------------------------------------------- pricing


def option_prices(cost_basis_cents: Sequence[int], markup_pct: Decimal) -> list[int]:
    """Client totals for several cost bases at one markup (whole dollars)."""
    return [money.apply_markup(c, markup_pct) for c in cost_basis_cents]


def _effective_markup(proposal: Proposal, option: ProposalOption) -> Decimal:
    if option.markup_pct_override is not None:
        return Decimal(option.markup_pct_override)
    return Decimal(proposal.markup_pct)


def _price_option(proposal: Proposal, option: ProposalOption, quote: Quote) -> None:
    """Reprice a draft option from the quote's current known total."""
    cost = quote.known_total_cents or 0
    (total,) = option_prices([cost], _effective_markup(proposal, option))
    option.cost_basis_cents = cost
    option.client_total_cents = total
    option.markup_cents = total - cost


# --------------------------------------------------------------------------- loading helpers


def _workspace(db: Session, workspace_id: uuid.UUID) -> Workspace:
    ws = db.get(Workspace, workspace_id)
    if ws is None:  # pragma: no cover - FK guarantees it
        raise NotFound("Workspace not found")
    return ws


def _trip(db: Session, proposal: Proposal) -> Trip:
    trip = db.get(Trip, proposal.trip_id)
    if trip is None:  # pragma: no cover - FK guarantees it
        raise NotFound("Trip not found")
    return trip


def _quotes_by_id(db: Session, ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, Quote]:
    wanted = list(set(ids))
    if not wanted:
        return {}
    return {q.id: q for q in db.scalars(select(Quote).where(Quote.id.in_(wanted)))}


def _trip_quotes(db: Session, ctx: RequestContext, trip: Trip) -> list[Quote]:
    stmt = scoped(select(Quote).where(Quote.trip_id == trip.id), ctx).order_by(
        Quote.created_at, Quote.id
    )
    return list(db.scalars(stmt))


def _snap(proposal: Proposal) -> dict[str, Any]:
    return audit.snapshot(proposal, _PROPOSAL_FIELDS)


def _record(
    db: Session,
    ctx: RequestContext,
    action: str,
    proposal: Proposal,
    before: dict[str, Any] | None,
) -> None:
    after = _snap(proposal)
    if before is not None:
        before, after = audit.diff(before, after)
    audit.record(db, ctx, action, proposal, before, after, trip_id=proposal.trip_id)


def _require_status(proposal: Proposal, allowed: Iterable[ProposalStatus], action: str) -> None:
    allowed = frozenset(allowed)
    if proposal.status not in allowed:
        code = "proposal_not_draft" if allowed == {ProposalStatus.DRAFT} else "invalid_transition"
        raise Conflict(f"Cannot {action} a {proposal.status.value} proposal", code=code)


# --------------------------------------------------------------------------- listing


def _summary(proposal: Proposal, trip_reference: str) -> ProposalSummaryOut:
    options = list(proposal.options)
    rec = next((o for o in options if o.is_recommended), options[0] if options else None)
    return ProposalSummaryOut(
        id=proposal.id,
        trip_id=proposal.trip_id,
        trip_reference=trip_reference,
        status=proposal.status,
        title=proposal.title,
        client_name=proposal.client_name,
        markup_pct=proposal.markup_pct,
        option_count=len(options),
        recommended_client_total_cents=rec.client_total_cents if rec else None,
        sent_at=proposal.sent_at,
        share_expires_at=proposal.share_expires_at,
        view_count=proposal.view_count,
        created_at=proposal.created_at,
        updated_at=proposal.updated_at,
    )


def list_proposals(
    db: Session,
    ctx: RequestContext,
    *,
    trip_id: uuid.UUID | None = None,
    status: ProposalStatus | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[ProposalSummaryOut], int]:
    base = scoped(select(Proposal), ctx)
    if trip_id is not None:
        base = base.where(Proposal.trip_id == trip_id)
    if status is not None:
        base = base.where(Proposal.status == status)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.execute(
        base.join(Trip, Trip.id == Proposal.trip_id)
        .add_columns(Trip.reference)
        .options(selectinload(Proposal.options))
        .order_by(Proposal.created_at.desc(), Proposal.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return [_summary(p, ref) for p, ref in rows], total


# --------------------------------------------------------------------------- create / edit


def _check_quotes(
    db: Session,
    trip: Trip,
    quote_ids: Sequence[uuid.UUID],
    threshold: int,
    *,
    error: type[Unprocessable] | type[Conflict] = Unprocessable,
) -> dict[uuid.UUID, Quote]:
    """Load the quotes (404 if not on this trip) and require every one eligible."""
    if len(set(quote_ids)) != len(quote_ids):
        raise Unprocessable("A quote appears more than once", code="duplicate_quotes")
    quotes = _quotes_by_id(db, quote_ids)
    for qid in quote_ids:
        q = quotes.get(qid)
        if q is None or q.trip_id != trip.id:
            raise NotFound("Quote not found")
    failures: dict[str, Any] = {}
    for qid in quote_ids:
        elig = proposal_eligibility(db, quotes[qid], trip, review_threshold=threshold)
        if not elig.eligible:
            failures[str(qid)] = _reasons_json(elig)
    if failures:
        raise error(
            "Some quotes cannot go into a proposal", code="ineligible_quotes", fields=failures
        )
    return quotes


def create_proposal(db: Session, ctx: RequestContext, trip: Trip, data: ProposalCreate) -> Proposal:
    """422 `ineligible_quotes` with reasons when an explicit quote is ineligible."""
    threshold = ctx.workspace.review_threshold
    markup = data.markup_pct if data.markup_pct is not None else ctx.workspace.default_markup_pct
    markup = Decimal(markup)

    if data.quote_ids is not None:
        quotes = _check_quotes(db, trip, data.quote_ids, threshold)
        ordered = [quotes[q] for q in data.quote_ids]
    else:
        eligible = [
            q
            for q in _trip_quotes(db, ctx, trip)
            if proposal_eligibility(db, q, trip, review_threshold=threshold).eligible
        ]
        if not eligible:
            raise Unprocessable("No quote is eligible for a proposal", code="no_eligible_quotes")
        ordered = sorted(
            eligible,
            key=lambda q: (
                not q.is_recommended,
                money.apply_markup(q.known_total_cents or 0, markup),
                q.created_at,
                q.id,
            ),
        )

    proposal = Proposal(
        workspace_id=ctx.workspace_id,
        trip_id=trip.id,
        created_by_id=ctx.user_id,
        status=ProposalStatus.DRAFT,
        title=data.title or f"{trip.reference} charter options",
        client_name=data.client_name if data.client_name is not None else trip.client_name,
        message=data.message,
        markup_pct=markup,
    )
    for i, quote in enumerate(ordered):
        option = ProposalOption(
            workspace_id=ctx.workspace_id,
            quote_id=quote.id,
            sort_order=i,
            is_recommended=quote.is_recommended,
        )
        _price_option(proposal, option, quote)
        proposal.options.append(option)
    db.add(proposal)
    db.flush()
    after = _snap(proposal)
    after["quote_ids"] = [str(q.id) for q in ordered]
    audit.record(db, ctx, "proposal.create", proposal, None, after, trip_id=trip.id)
    return proposal


def update_proposal(
    db: Session, ctx: RequestContext, proposal: Proposal, data: ProposalPatch
) -> Proposal:
    """Drafts only (409 `proposal_not_draft` otherwise)."""
    _require_status(proposal, {ProposalStatus.DRAFT}, "edit")
    trip = _trip(db, proposal)
    before = _snap(proposal)
    before["options"] = _options_audit(proposal)

    for attr in ("title", "client_name", "message"):
        if attr in data.model_fields_set:
            value = getattr(data, attr)
            if attr == "title" and not value:
                raise Unprocessable("Title cannot be empty", code="title_required")
            setattr(proposal, attr, value)
    if "markup_pct" in data.model_fields_set and data.markup_pct is not None:
        proposal.markup_pct = Decimal(data.markup_pct)

    if data.options is not None:
        ids = [o.quote_id for o in data.options]
        quotes = _check_quotes(db, trip, ids, ctx.workspace.review_threshold)
        existing = {o.quote_id: o for o in proposal.options}
        new_options: list[ProposalOption] = []
        for i, item in enumerate(data.options):
            option = existing.pop(item.quote_id, None)
            if option is None:
                option = ProposalOption(workspace_id=proposal.workspace_id, quote_id=item.quote_id)
            option.sort_order = i
            option.is_recommended = quotes[item.quote_id].is_recommended
            option.markup_pct_override = item.markup_pct_override
            _price_option(proposal, option, quotes[item.quote_id])
            new_options.append(option)
        for stale in existing.values():
            proposal.options.remove(stale)
        db.flush()  # delete removed rows before re-inserting any
        proposal.options = new_options

    _reprice(db, proposal)
    db.flush()
    after = _snap(proposal)
    after["options"] = _options_audit(proposal)
    b, a = audit.diff(before, after)
    audit.record(db, ctx, "proposal.update", proposal, b, a, trip_id=proposal.trip_id)
    return proposal


def _reprice(db: Session, proposal: Proposal) -> None:
    quotes = _quotes_by_id(db, (o.quote_id for o in proposal.options))
    for option in proposal.options:
        quote = quotes.get(option.quote_id)
        if quote is not None:
            _price_option(proposal, option, quote)


def _options_audit(proposal: Proposal) -> list[dict[str, Any]]:
    return [
        {
            "quote_id": str(o.quote_id),
            "sort_order": o.sort_order,
            "markup_pct_override": audit.jsonable(o.markup_pct_override),
            "client_total_cents": o.client_total_cents,
        }
        for o in sorted(proposal.options, key=lambda o: o.sort_order)
    ]


# --------------------------------------------------------------------------- send and links


def send_proposal(
    db: Session, ctx: RequestContext, proposal: Proposal, *, settings: Settings, now: datetime
) -> Proposal:
    _require_status(proposal, {ProposalStatus.DRAFT}, "send")
    if not proposal.options:
        raise Unprocessable("A proposal needs at least one option", code="no_options")
    trip = _trip(db, proposal)
    _check_quotes(
        db,
        trip,
        [o.quote_id for o in proposal.options],
        ctx.workspace.review_threshold,
        error=Conflict,
    )
    before = _snap(proposal)
    _reprice(db, proposal)
    _freeze_snapshots(db, proposal, trip, ctx.workspace, now=now)

    proposal.status = ProposalStatus.SENT
    proposal.sent_at = now
    proposal.sent_by_id = ctx.user_id
    _new_token(proposal, settings, now)

    if trip.status in (TripStatus.DRAFT, TripStatus.SOURCING, TripStatus.QUOTED):
        trip_before = {"status": trip.status.value}
        trip.status = TripStatus.PROPOSED
        after = {"status": trip.status.value}
        audit.record(db, ctx, "trip.update", trip, trip_before, after, trip_id=trip.id)
    db.flush()
    _record(db, ctx, "proposal.send", proposal, before)
    return proposal


def _new_token(proposal: Proposal, settings: Settings, now: datetime) -> None:
    proposal.share_token = secrets.token_urlsafe(32)
    proposal.share_enabled = True
    proposal.share_expires_at = now + timedelta(days=settings.share_link_ttl_days)


def rotate_link(
    db: Session, ctx: RequestContext, proposal: Proposal, *, settings: Settings, now: datetime
) -> Proposal:
    _require_status(proposal, _LINK_STATUSES, "rotate the link of")
    before = _snap(proposal)
    _new_token(proposal, settings, now)
    db.flush()
    _record(db, ctx, "proposal.rotate_link", proposal, before)
    return proposal


def revoke_link(db: Session, ctx: RequestContext, proposal: Proposal, *, now: datetime) -> Proposal:
    _require_status(proposal, _LINK_STATUSES, "revoke the link of")
    before = _snap(proposal)
    proposal.share_enabled = False
    db.flush()
    _record(db, ctx, "proposal.revoke_link", proposal, before)
    return proposal


# --------------------------------------------------------------------------- lifecycle


def _choose_option(proposal: Proposal, option_id: uuid.UUID | None) -> ProposalOption:
    options = list(proposal.options)
    if option_id is None:
        option_id = proposal.accepted_option_id
    if option_id is None:
        if len(options) == 1:
            return options[0]
        raise Unprocessable("Choose which option", code="option_required")
    option = next((o for o in options if o.id == option_id), None)
    if option is None:
        raise Unprocessable("That option is not part of this proposal", code="unknown_option")
    return option


def mark_accepted(
    db: Session,
    ctx: RequestContext,
    proposal: Proposal,
    *,
    option_id: uuid.UUID | None,
    now: datetime,
) -> Proposal:
    _require_status(proposal, {ProposalStatus.SENT}, "accept")
    option = _choose_option(proposal, option_id)
    before = _snap(proposal)
    proposal.status = ProposalStatus.ACCEPTED
    proposal.accepted_at = now
    proposal.accepted_option_id = option.id
    db.flush()
    _record(db, ctx, "proposal.mark_accepted", proposal, before)
    return proposal


def mark_booked(
    db: Session,
    ctx: RequestContext,
    proposal: Proposal,
    *,
    option_id: uuid.UUID | None,
    now: datetime,
) -> Proposal:
    """Sets the trip to booked with `booked_quote_id`."""
    _require_status(proposal, {ProposalStatus.SENT, ProposalStatus.ACCEPTED}, "book")
    option = _choose_option(proposal, option_id)
    trip = _trip(db, proposal)
    if trip.booked_quote_id is not None and trip.booked_quote_id != option.quote_id:
        raise Conflict("The trip is already booked with another quote", code="trip_booked")

    before = _snap(proposal)
    if proposal.accepted_at is None:
        proposal.accepted_at = now
    proposal.accepted_option_id = option.id
    proposal.status = ProposalStatus.BOOKED
    proposal.booked_at = now

    trip_fields = ("status", "booked_quote_id", "booked_at")
    trip_before = audit.snapshot(trip, trip_fields)
    trip.status = TripStatus.BOOKED
    trip.booked_quote_id = option.quote_id
    trip.booked_at = now
    db.flush()
    _record(db, ctx, "proposal.mark_booked", proposal, before)
    tb, ta = audit.diff(trip_before, audit.snapshot(trip, trip_fields))
    audit.record(db, ctx, "trip.book", trip, tb, ta, trip_id=trip.id)
    return proposal


def decline(db: Session, ctx: RequestContext, proposal: Proposal, *, now: datetime) -> Proposal:
    _require_status(proposal, {ProposalStatus.SENT, ProposalStatus.ACCEPTED}, "decline")
    before = _snap(proposal)
    proposal.status = ProposalStatus.DECLINED
    proposal.declined_at = now
    db.flush()
    _record(db, ctx, "proposal.decline", proposal, before)
    return proposal


def cancel(db: Session, ctx: RequestContext, proposal: Proposal, *, now: datetime) -> Proposal:
    allowed = {ProposalStatus.DRAFT, ProposalStatus.SENT, ProposalStatus.ACCEPTED}
    _require_status(proposal, allowed, "cancel")
    before = _snap(proposal)
    proposal.status = ProposalStatus.CANCELLED
    proposal.cancelled_at = now
    proposal.share_enabled = False
    db.flush()
    _record(db, ctx, "proposal.cancel", proposal, before)
    return proposal


def revise(db: Session, ctx: RequestContext, proposal: Proposal, *, now: datetime) -> Proposal:
    """Clone into a new draft and mark this one superseded."""
    allowed = {ProposalStatus.SENT, ProposalStatus.ACCEPTED, ProposalStatus.DECLINED}
    _require_status(proposal, allowed, "revise")
    before = _snap(proposal)

    draft = Proposal(
        workspace_id=proposal.workspace_id,
        trip_id=proposal.trip_id,
        created_by_id=ctx.user_id,
        status=ProposalStatus.DRAFT,
        title=proposal.title,
        client_name=proposal.client_name,
        message=proposal.message,
        markup_pct=proposal.markup_pct,
        supersedes_id=proposal.id,
    )
    for old in sorted(proposal.options, key=lambda o: o.sort_order):
        draft.options.append(
            ProposalOption(
                workspace_id=proposal.workspace_id,
                quote_id=old.quote_id,
                sort_order=old.sort_order,
                is_recommended=old.is_recommended,
                markup_pct_override=old.markup_pct_override,
                cost_basis_cents=old.cost_basis_cents,
                markup_cents=old.markup_cents,
                client_total_cents=old.client_total_cents,
            )
        )
    _reprice(db, draft)
    proposal.status = ProposalStatus.SUPERSEDED
    db.add(draft)
    db.flush()
    _record(db, ctx, "proposal.supersede", proposal, before)
    after = _snap(draft)
    audit.record(db, ctx, "proposal.revise", draft, None, after, trip_id=draft.trip_id)
    return draft


# --------------------------------------------------------------------------- snapshots


def _key(text: str) -> str:
    """Case- and punctuation-free form used to compare words."""
    return _TOKEN_SPLIT.sub("", text).casefold()


def _operator_tokens(operator: Operator | None) -> set[str]:
    """Keys of the operator's name and aliases: each word, and each whole name
    ("Wheels Up" -> {"wheels", "up", "wheelsup"})."""
    if operator is None:
        return set()
    names = [operator.name, *(operator.aliases or [])]
    tokens = {
        t.casefold()
        for name in names
        for t in _TOKEN_SPLIT.split(name)
        if len(t) >= 2 and not t.isdigit()
    }
    return tokens | {k for name in names if (k := _key(name))}


# Registration marks: US N-numbers ("N684AC", "N-684AC") and ICAO-style marks
# with a letter suffix ("G-LXRY", "VP-CXX").
_REGISTRATION = re.compile(r"N-?[1-9][0-9]{0,4}[A-Z]{0,2}|[A-Z]{1,2}-[A-Z]{3,4}", re.IGNORECASE)
# Free text after one of these is commentary ("- Wheels Up fleet", "(N684AC)").
_MODEL_COMMENTARY = re.compile(r"\s[-\u2013\u2014|/]\s|[(\[{,;]")
_HYPHEN_IN_WORD = re.compile(r"(?<=[A-Za-z0-9])-(?=[A-Za-z0-9])")


def client_aircraft_label(
    model: str | None,
    *,
    operator: Operator | None,
    tail_number: str | None = None,
    category_label: str | None = None,
) -> str:
    """Client-facing aircraft name, which must never name the operator or the tail.

    The canonical dictionary model when the text matches one (also with in-word
    hyphens dropped: "G-IV SP" -> "GIV SP"). Otherwise the text up to any
    commentary, without words that match the operator's name (compared without
    case and punctuation), the tail number or any registration mark. Falls back
    to the category label.
    """
    if model:
        canonical = _canonical_model(model) or _canonical_model(_HYPHEN_IN_WORD.sub("", model))
        if canonical:
            return canonical
        banned = _operator_tokens(operator)
        if tail_number and (tail := _key(tail_number)):
            banned.add(tail)
        head = _MODEL_COMMENTARY.split(model, maxsplit=1)[0]
        words = [
            w
            for w in head.split()
            if (k := _key(w))
            and k not in banned
            and not _REGISTRATION.fullmatch(w.strip(".,;:()[]'\"-"))
        ]
        label = " ".join(words).strip(" .,;:-/")
        if label:
            return label
    return category_label or "Private jet"


def _canonical_model(text: str) -> str | None:
    try:
        return canonical_model(text)
    except NotImplementedError:  # dictionary not built yet
        return None


def _airport_codes(icao: str) -> tuple[str, str]:
    """(display code, city) for an airport; falls back to the ICAO code."""
    try:
        info = get_airport(icao)
    except NotImplementedError:
        info = None
    if info is None:
        return icao, icao
    return info.iata or info.icao, info.city


def _category_label(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return AIRCRAFT_CATEGORY_LABELS[AircraftCategory(value)]
    except (KeyError, ValueError):
        return value


def _trip_snapshot(trip: Trip, workspace: Workspace) -> dict[str, Any]:
    legs = []
    for leg in sorted(trip.legs, key=lambda x: x.seq):
        o_code, o_city = _airport_codes(leg.origin_icao)
        d_code, d_city = _airport_codes(leg.destination_icao)
        legs.append(
            {
                "origin_code": o_code,
                "origin_city": o_city,
                "destination_code": d_code,
                "destination_city": d_city,
                "departure_local": leg.depart_local.isoformat(),
            }
        )
    return {"pax": trip.pax, "legs": legs, "prepared_by": workspace.name}


def _client_option(
    db: Session, option: ProposalOption, quote: Quote, trip: Trip, workspace: Workspace
) -> dict[str, Any]:
    operator = db.get(Operator, quote.operator_id)
    category = quote.aircraft_category.value if quote.aircraft_category else None
    return {
        "aircraft": client_aircraft_label(
            quote.aircraft_model,
            operator=operator,
            tail_number=quote.tail_number,
            category_label=_category_label(category),
        ),
        "category": category,
        "client_total_cents": option.client_total_cents,
        "seats": quote.seats,
        "wifi": quote.wifi,
        "flight_time_minutes": quote.flight_time_minutes,
        "recommended": option.is_recommended,
        "trip": _trip_snapshot(trip, workspace),
    }


def _broker_option(
    db: Session,
    proposal: Proposal,
    option: ProposalOption,
    quote: Quote | None,
    trip: Trip,
    threshold: int,
) -> dict[str, Any]:
    """Every field of `ProposalOptionOut` except the option's own identity."""
    markup = _effective_markup(proposal, option)
    base: dict[str, Any] = {
        "cost_basis_cents": option.cost_basis_cents,
        "markup_pct": markup,
        "markup_pct_override": option.markup_pct_override,
        "markup_cents": option.markup_cents,
        "client_total_cents": option.client_total_cents,
    }
    if quote is None:  # pragma: no cover - quote rows cascade with the option
        return {
            **base,
            "operator_name": "Unknown",
            "aircraft_model": None,
            "aircraft_category": None,
            "tail_number": None,
            "seats": None,
            "wifi": None,
            "flight_time_minutes": None,
            "headline_cents": None,
            "fee_lines": [],
            "added_charges_cents": None,
            "known_total_cents": None,
            "upper_total_cents": None,
            "quote_confidence": None,
            "sources": [],
            "eligible": False,
            "reasons": [{"code": "not_active", "message": "Quote no longer exists"}],
        }
    operator = db.get(Operator, quote.operator_id)
    elig = proposal_eligibility(db, quote, trip, review_threshold=threshold)
    docs = db.scalars(
        select(SourceDocument)
        .where(SourceDocument.quote_id == quote.id)
        .order_by(SourceDocument.received_at, SourceDocument.created_at)
    )
    added = (
        quote.known_total_cents - quote.headline_cents
        if quote.known_total_cents is not None and quote.headline_cents is not None
        else None
    )
    return {
        **base,
        "operator_name": operator.name if operator else "Unknown operator",
        "aircraft_model": quote.aircraft_model,
        "aircraft_category": quote.aircraft_category.value if quote.aircraft_category else None,
        "tail_number": quote.tail_number,
        "seats": quote.seats,
        "wifi": quote.wifi,
        "flight_time_minutes": quote.flight_time_minutes,
        "headline_cents": quote.headline_cents,
        "fee_lines": [
            BrokerFeeLineOut(
                category=f.category,
                label=f.label,
                amount_status=f.amount_status,
                amount_cents=f.amount_cents,
            ).model_dump(mode="json")
            for f in quote.fee_lines
        ],
        "added_charges_cents": added,
        "known_total_cents": quote.known_total_cents,
        "upper_total_cents": quote.upper_total_cents,
        "quote_confidence": quote.quote_confidence,
        "sources": [
            SourceRefOut(
                document_id=d.id,
                kind=d.kind,
                channel=d.channel,
                original_filename=d.original_filename,
                received_at=d.received_at,
            ).model_dump(mode="json")
            for d in docs
        ],
        "eligible": elig.eligible,
        "reasons": _reasons_json(elig),
    }


def _freeze_snapshots(
    db: Session, proposal: Proposal, trip: Trip, workspace: Workspace, *, now: datetime
) -> None:
    quotes = _quotes_by_id(db, (o.quote_id for o in proposal.options))
    for option in proposal.options:
        quote = quotes[option.quote_id]
        option.client_snapshot = audit.jsonable(_client_option(db, option, quote, trip, workspace))
        option.broker_snapshot = audit.jsonable(
            _broker_option(db, proposal, option, quote, trip, workspace.review_threshold)
        )
        option.snapshot_at = now


# --------------------------------------------------------------------------- views


def _share_url(proposal: Proposal, settings: Settings) -> str | None:
    if not proposal.share_token or not proposal.share_enabled:
        return None
    return f"{settings.public_app_url.rstrip('/')}/p/{proposal.share_token}"


def broker_view(db: Session, proposal: Proposal, *, settings: Settings) -> ProposalOut:
    trip = _trip(db, proposal)
    workspace = _workspace(db, proposal.workspace_id)
    live = proposal.status is ProposalStatus.DRAFT
    quotes = _quotes_by_id(db, (o.quote_id for o in proposal.options)) if live else {}
    options: list[ProposalOptionOut] = []
    for option in sorted(proposal.options, key=lambda o: o.sort_order):
        if live or option.broker_snapshot is None:
            quote = quotes.get(option.quote_id) or db.get(Quote, option.quote_id)
            data = _broker_option(db, proposal, option, quote, trip, workspace.review_threshold)
        else:
            data = dict(option.broker_snapshot)
        options.append(
            ProposalOptionOut.model_validate(
                {
                    **data,
                    "id": option.id,
                    "quote_id": option.quote_id,
                    "sort_order": option.sort_order,
                    "is_recommended": option.is_recommended,
                    "reasons": [ReasonOut.model_validate(r) for r in data.get("reasons", [])],
                    "snapshot_at": option.snapshot_at,
                }
            )
        )
    return ProposalOut(
        id=proposal.id,
        trip_id=proposal.trip_id,
        trip_reference=trip.reference,
        status=proposal.status,
        title=proposal.title,
        client_name=proposal.client_name,
        message=proposal.message,
        markup_pct=proposal.markup_pct,
        share_url=_share_url(proposal, settings),
        share_enabled=proposal.share_enabled,
        share_expires_at=proposal.share_expires_at,
        sent_at=proposal.sent_at,
        sent_by_id=proposal.sent_by_id,
        accepted_at=proposal.accepted_at,
        accepted_option_id=proposal.accepted_option_id,
        accepted_by_name=proposal.accepted_by_name,
        booked_at=proposal.booked_at,
        declined_at=proposal.declined_at,
        cancelled_at=proposal.cancelled_at,
        first_viewed_at=proposal.first_viewed_at,
        last_viewed_at=proposal.last_viewed_at,
        view_count=proposal.view_count,
        supersedes_id=proposal.supersedes_id,
        created_by_id=proposal.created_by_id,
        created_at=proposal.created_at,
        updated_at=proposal.updated_at,
        options=options,
    )


def public_view(db: Session, proposal: Proposal) -> PublicProposalOut:
    """Built only from client snapshots (live quotes for drafts in client-preview).
    Never includes operator, tail number, fees, confidence, markup or file names."""
    options = sorted(proposal.options, key=lambda o: o.sort_order)
    frozen = proposal.status is not ProposalStatus.DRAFT and all(
        o.client_snapshot is not None for o in options
    )
    snapshots: list[tuple[ProposalOption, dict[str, Any]]]
    if frozen and options:
        snapshots = [(o, dict(o.client_snapshot or {})) for o in options]
        trip_info: dict[str, Any] = snapshots[0][1]["trip"]
    else:
        trip = _trip(db, proposal)
        workspace = _workspace(db, proposal.workspace_id)
        quotes = _quotes_by_id(db, (o.quote_id for o in options))
        snapshots = [
            (o, audit.jsonable(_client_option(db, o, quotes[o.quote_id], trip, workspace)))
            for o in options
        ]
        trip_info = audit.jsonable(_trip_snapshot(trip, workspace))
    legs = [PublicLegOut.model_validate(leg) for leg in trip_info["legs"]]
    pax = int(trip_info["pax"])
    show_accepted = proposal.status in (ProposalStatus.ACCEPTED, ProposalStatus.BOOKED)
    return PublicProposalOut(
        title=proposal.title,
        prepared_for=proposal.client_name,
        prepared_by=trip_info["prepared_by"],
        legs=legs,
        date=legs[0].departure_local.date(),
        pax=pax,
        message=proposal.message,
        options=[
            PublicOptionOut(
                option_id=option.id,
                aircraft=snap["aircraft"],
                category=snap.get("category"),
                client_total_cents=snap["client_total_cents"],
                seats=snap.get("seats"),
                pax=pax,
                wifi=snap.get("wifi"),
                flight_time_minutes=snap.get("flight_time_minutes"),
                recommended=bool(snap.get("recommended")),
            )
            for option, snap in snapshots
        ],
        status=proposal.status,
        accepted_option_id=proposal.accepted_option_id if show_accepted else None,
        expires_at=proposal.share_expires_at,
    )


# --------------------------------------------------------------------------- public access


def get_public_proposal(db: Session, token: str, *, now: datetime) -> Proposal:
    """Unknown, revoked, draft and expired tokens -> the same 404; superseded -> 410.
    Scopes the session to the proposal's workspace."""
    proposal = db.scalar(select(Proposal).where(Proposal.share_token == token))
    if proposal is None:
        raise NotFound(_NOT_FOUND)
    if proposal.status is ProposalStatus.SUPERSEDED:
        raise Gone("This proposal has been replaced by a newer version", code="superseded")
    expired = proposal.share_expires_at is None or proposal.share_expires_at <= now
    if (
        not proposal.share_enabled
        or expired
        or proposal.status in (ProposalStatus.DRAFT, ProposalStatus.CANCELLED)
    ):
        raise NotFound(_NOT_FOUND)
    set_workspace(db, proposal.workspace_id)
    return proposal


def record_public_view(
    db: Session, proposal: Proposal, *, now: datetime, ip: str | None, user_agent: str | None
) -> None:
    """Count the view; the first one is audited as `public.proposal_view`."""
    first = proposal.first_viewed_at is None
    proposal.view_count = (proposal.view_count or 0) + 1
    proposal.last_viewed_at = now
    if first:
        proposal.first_viewed_at = now
        audit.record(
            db,
            None,
            "public.proposal_view",
            proposal,
            None,
            {"view_count": proposal.view_count, "first_viewed_at": now},
            trip_id=proposal.trip_id,
            workspace_id=proposal.workspace_id,
            actor_kind=ActorKind.PUBLIC,
            ip=ip,
            user_agent=user_agent,
        )
    db.flush()


def public_accept(
    db: Session,
    proposal: Proposal,
    *,
    option_id: uuid.UUID,
    name: str,
    now: datetime,
    ip: str | None,
    user_agent: str | None,
) -> Proposal:
    option = next((o for o in proposal.options if o.id == option_id), None)
    if option is None:
        raise Unprocessable("That option is not part of this proposal", code="unknown_option")
    if proposal.status is ProposalStatus.ACCEPTED and proposal.accepted_option_id == option_id:
        return proposal  # a repeated click is harmless
    if proposal.status is not ProposalStatus.SENT:
        raise Conflict("This proposal can no longer be accepted", code="invalid_transition")
    before = _snap(proposal)
    proposal.status = ProposalStatus.ACCEPTED
    proposal.accepted_at = now
    proposal.accepted_option_id = option.id
    proposal.accepted_by_name = name
    db.flush()
    b, a = audit.diff(before, _snap(proposal))
    audit.record(
        db,
        None,
        "public.proposal_accept",
        proposal,
        b,
        a,
        trip_id=proposal.trip_id,
        workspace_id=proposal.workspace_id,
        actor_kind=ActorKind.PUBLIC,
        actor_label=name,
        ip=ip,
        user_agent=user_agent,
    )
    return proposal
