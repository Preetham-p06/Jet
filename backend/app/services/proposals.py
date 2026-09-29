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

import uuid
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.config import Settings
from app.models.enums import ProposalStatus
from app.models.proposal import Proposal
from app.models.quote import Quote
from app.models.trip import Trip
from app.permissions import RequestContext
from app.schemas.proposal import (
    ProposalCreate,
    ProposalOut,
    ProposalPatch,
    ProposalSummaryOut,
    PublicProposalOut,
)
from app.services.contracts import Eligibility


def proposal_eligibility(
    db: Session, quote: Quote, trip: Trip, *, review_threshold: int
) -> Eligibility:
    raise NotImplementedError


def list_proposals(
    db: Session,
    ctx: RequestContext,
    *,
    trip_id: uuid.UUID | None = None,
    status: ProposalStatus | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[ProposalSummaryOut], int]:
    raise NotImplementedError


def create_proposal(db: Session, ctx: RequestContext, trip: Trip, data: ProposalCreate) -> Proposal:
    """422 `ineligible_quotes` with reasons when an explicit quote is ineligible."""
    raise NotImplementedError


def update_proposal(
    db: Session, ctx: RequestContext, proposal: Proposal, data: ProposalPatch
) -> Proposal:
    """Drafts only (409 `proposal_not_draft` otherwise)."""
    raise NotImplementedError


def send_proposal(
    db: Session, ctx: RequestContext, proposal: Proposal, *, settings: Settings, now: datetime
) -> Proposal:
    raise NotImplementedError


def rotate_link(
    db: Session, ctx: RequestContext, proposal: Proposal, *, settings: Settings, now: datetime
) -> Proposal:
    raise NotImplementedError


def revoke_link(db: Session, ctx: RequestContext, proposal: Proposal, *, now: datetime) -> Proposal:
    raise NotImplementedError


def mark_accepted(
    db: Session,
    ctx: RequestContext,
    proposal: Proposal,
    *,
    option_id: uuid.UUID | None,
    now: datetime,
) -> Proposal:
    raise NotImplementedError


def mark_booked(
    db: Session,
    ctx: RequestContext,
    proposal: Proposal,
    *,
    option_id: uuid.UUID | None,
    now: datetime,
) -> Proposal:
    """Sets the trip to booked with `booked_quote_id`."""
    raise NotImplementedError


def decline(db: Session, ctx: RequestContext, proposal: Proposal, *, now: datetime) -> Proposal:
    raise NotImplementedError


def cancel(db: Session, ctx: RequestContext, proposal: Proposal, *, now: datetime) -> Proposal:
    raise NotImplementedError


def revise(db: Session, ctx: RequestContext, proposal: Proposal, *, now: datetime) -> Proposal:
    """Clone into a new draft and mark this one superseded."""
    raise NotImplementedError


def broker_view(db: Session, proposal: Proposal, *, settings: Settings) -> ProposalOut:
    raise NotImplementedError


def public_view(db: Session, proposal: Proposal) -> PublicProposalOut:
    """Built only from client snapshots (live quotes for drafts in client-preview).
    Never includes operator, tail number, fees, confidence, markup or file names."""
    raise NotImplementedError


def get_public_proposal(db: Session, token: str, *, now: datetime) -> Proposal:
    """Unknown, revoked, draft and expired tokens -> the same 404; superseded -> 410.
    Scopes the session to the proposal's workspace."""
    raise NotImplementedError


def record_public_view(
    db: Session, proposal: Proposal, *, now: datetime, ip: str | None, user_agent: str | None
) -> None:
    """Count the view; the first one is audited as `public.proposal_view`."""
    raise NotImplementedError


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
    raise NotImplementedError


def option_prices(cost_basis_cents: Sequence[int], markup_pct: Decimal) -> list[int]:
    """Client totals for several cost bases at one markup (whole dollars)."""
    raise NotImplementedError
