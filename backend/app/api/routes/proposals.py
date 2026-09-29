"""Proposals (admins and brokers only): builder, lifecycle and share links."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query, status
from sqlalchemy.orm import Session

from app.api.params import PageParams
from app.deps import AppSettings, DbSession, Reviewer
from app.models.enums import ProposalStatus
from app.models.proposal import Proposal
from app.models.trip import Trip
from app.permissions import get_owned
from app.schemas.common import Page
from app.schemas.proposal import (
    OptionChoiceIn,
    ProposalCreate,
    ProposalOut,
    ProposalPatch,
    ProposalSummaryOut,
    PublicProposalOut,
)
from app.services import proposals as svc

router = APIRouter(tags=["proposals"])


def _now() -> datetime:
    return datetime.now(UTC)


def _out(db: Session, proposal: Proposal, settings: AppSettings) -> ProposalOut:
    db.commit()
    db.refresh(proposal)
    return svc.broker_view(db, proposal, settings=settings)


@router.get("/proposals", summary="Every proposal in the workspace")
def list_proposals(
    ctx: Reviewer,
    db: DbSession,
    page: PageParams,
    trip_id: uuid.UUID | None = None,
    status_filter: Annotated[ProposalStatus | None, Query(alias="status")] = None,
) -> Page[ProposalSummaryOut]:
    if trip_id is not None:
        get_owned(db, Trip, trip_id, ctx)
    items, total = svc.list_proposals(
        db, ctx, trip_id=trip_id, status=status_filter, limit=page.limit, offset=page.offset
    )
    return Page(items=items, total=total)


@router.get("/trips/{trip_id}/proposals", summary="Proposals for a trip")
def list_trip_proposals(
    trip_id: uuid.UUID, ctx: Reviewer, db: DbSession, page: PageParams
) -> Page[ProposalSummaryOut]:
    trip = get_owned(db, Trip, trip_id, ctx)
    items, total = svc.list_proposals(
        db, ctx, trip_id=trip.id, limit=page.limit, offset=page.offset
    )
    return Page(items=items, total=total)


@router.post(
    "/trips/{trip_id}/proposals",
    status_code=status.HTTP_201_CREATED,
    summary="Create a draft (defaults to every eligible quote, recommended first)",
)
def create_proposal(
    trip_id: uuid.UUID, body: ProposalCreate, ctx: Reviewer, db: DbSession, settings: AppSettings
) -> ProposalOut:
    trip = get_owned(db, Trip, trip_id, ctx)
    return _out(db, svc.create_proposal(db, ctx, trip, body), settings)


@router.get("/proposals/{proposal_id}", summary="Broker view")
def get_proposal(
    proposal_id: uuid.UUID, ctx: Reviewer, db: DbSession, settings: AppSettings
) -> ProposalOut:
    return svc.broker_view(db, get_owned(db, Proposal, proposal_id, ctx), settings=settings)


@router.get(
    "/proposals/{proposal_id}/client-preview",
    summary="Exactly what the client will see (drafts included)",
)
def get_client_preview(proposal_id: uuid.UUID, ctx: Reviewer, db: DbSession) -> PublicProposalOut:
    return svc.public_view(db, get_owned(db, Proposal, proposal_id, ctx))


@router.patch("/proposals/{proposal_id}", summary="Edit a draft: options, order, markup, text")
def update_proposal(
    proposal_id: uuid.UUID,
    body: ProposalPatch,
    ctx: Reviewer,
    db: DbSession,
    settings: AppSettings,
) -> ProposalOut:
    proposal = get_owned(db, Proposal, proposal_id, ctx)
    return _out(db, svc.update_proposal(db, ctx, proposal, body), settings)


@router.post("/proposals/{proposal_id}/send", summary="Freeze snapshots and create the share link")
def send_proposal(
    proposal_id: uuid.UUID, ctx: Reviewer, db: DbSession, settings: AppSettings
) -> ProposalOut:
    proposal = get_owned(db, Proposal, proposal_id, ctx)
    sent = svc.send_proposal(db, ctx, proposal, settings=settings, now=_now())
    return _out(db, sent, settings)


@router.post("/proposals/{proposal_id}/rotate-link", summary="Issue a new share token")
def rotate_link(
    proposal_id: uuid.UUID, ctx: Reviewer, db: DbSession, settings: AppSettings
) -> ProposalOut:
    proposal = get_owned(db, Proposal, proposal_id, ctx)
    return _out(db, svc.rotate_link(db, ctx, proposal, settings=settings, now=_now()), settings)


@router.post("/proposals/{proposal_id}/revoke-link", summary="Disable the share link")
def revoke_link(
    proposal_id: uuid.UUID, ctx: Reviewer, db: DbSession, settings: AppSettings
) -> ProposalOut:
    proposal = get_owned(db, Proposal, proposal_id, ctx)
    return _out(db, svc.revoke_link(db, ctx, proposal, now=_now()), settings)


@router.post("/proposals/{proposal_id}/mark-accepted", summary="Record the client's acceptance")
def mark_accepted(
    proposal_id: uuid.UUID,
    body: OptionChoiceIn,
    ctx: Reviewer,
    db: DbSession,
    settings: AppSettings,
) -> ProposalOut:
    proposal = get_owned(db, Proposal, proposal_id, ctx)
    accepted = svc.mark_accepted(db, ctx, proposal, option_id=body.option_id, now=_now())
    return _out(db, accepted, settings)


@router.post("/proposals/{proposal_id}/mark-booked", summary="Book it; sets the trip to booked")
def mark_booked(
    proposal_id: uuid.UUID,
    body: OptionChoiceIn,
    ctx: Reviewer,
    db: DbSession,
    settings: AppSettings,
) -> ProposalOut:
    proposal = get_owned(db, Proposal, proposal_id, ctx)
    booked = svc.mark_booked(db, ctx, proposal, option_id=body.option_id, now=_now())
    return _out(db, booked, settings)


@router.post("/proposals/{proposal_id}/decline", summary="The client declined")
def decline_proposal(
    proposal_id: uuid.UUID, ctx: Reviewer, db: DbSession, settings: AppSettings
) -> ProposalOut:
    proposal = get_owned(db, Proposal, proposal_id, ctx)
    return _out(db, svc.decline(db, ctx, proposal, now=_now()), settings)


@router.post("/proposals/{proposal_id}/cancel", summary="Cancel a draft or sent proposal")
def cancel_proposal(
    proposal_id: uuid.UUID, ctx: Reviewer, db: DbSession, settings: AppSettings
) -> ProposalOut:
    proposal = get_owned(db, Proposal, proposal_id, ctx)
    return _out(db, svc.cancel(db, ctx, proposal, now=_now()), settings)


@router.post(
    "/proposals/{proposal_id}/revise",
    status_code=status.HTTP_201_CREATED,
    summary="Clone into a new draft; the old link then returns 410",
)
def revise_proposal(
    proposal_id: uuid.UUID, ctx: Reviewer, db: DbSession, settings: AppSettings
) -> ProposalOut:
    proposal = get_owned(db, Proposal, proposal_id, ctx)
    return _out(db, svc.revise(db, ctx, proposal, now=_now()), settings)
