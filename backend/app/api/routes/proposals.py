"""Proposals (admins and brokers only): builder, lifecycle and share links."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.params import PageParams
from app.deps import DbSession, Reviewer
from app.errors import not_implemented
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

router = APIRouter(tags=["proposals"])


@router.get("/proposals", summary="Every proposal in the workspace")
def list_proposals(
    ctx: Reviewer,
    db: DbSession,
    page: PageParams,
    trip_id: uuid.UUID | None = None,
    status_filter: Annotated[ProposalStatus | None, Query(alias="status")] = None,
) -> Page[ProposalSummaryOut]:
    not_implemented("Proposal list")


@router.get("/trips/{trip_id}/proposals", summary="Proposals for a trip")
def list_trip_proposals(
    trip_id: uuid.UUID, ctx: Reviewer, db: DbSession, page: PageParams
) -> Page[ProposalSummaryOut]:
    get_owned(db, Trip, trip_id, ctx)
    not_implemented("Proposal list")


@router.post(
    "/trips/{trip_id}/proposals",
    status_code=status.HTTP_201_CREATED,
    summary="Create a draft (defaults to every eligible quote, recommended first)",
)
def create_proposal(
    trip_id: uuid.UUID, body: ProposalCreate, ctx: Reviewer, db: DbSession
) -> ProposalOut:
    get_owned(db, Trip, trip_id, ctx)
    not_implemented("Proposal create")


@router.get("/proposals/{proposal_id}", summary="Broker view")
def get_proposal(proposal_id: uuid.UUID, ctx: Reviewer, db: DbSession) -> ProposalOut:
    get_owned(db, Proposal, proposal_id, ctx)
    not_implemented("Proposal detail")


@router.get(
    "/proposals/{proposal_id}/client-preview",
    summary="Exactly what the client will see (drafts included)",
)
def get_client_preview(proposal_id: uuid.UUID, ctx: Reviewer, db: DbSession) -> PublicProposalOut:
    get_owned(db, Proposal, proposal_id, ctx)
    not_implemented("Client preview")


@router.patch("/proposals/{proposal_id}", summary="Edit a draft: options, order, markup, text")
def update_proposal(
    proposal_id: uuid.UUID, body: ProposalPatch, ctx: Reviewer, db: DbSession
) -> ProposalOut:
    get_owned(db, Proposal, proposal_id, ctx)
    not_implemented("Proposal update")


@router.post("/proposals/{proposal_id}/send", summary="Freeze snapshots and create the share link")
def send_proposal(proposal_id: uuid.UUID, ctx: Reviewer, db: DbSession) -> ProposalOut:
    get_owned(db, Proposal, proposal_id, ctx)
    not_implemented("Proposal send")


@router.post("/proposals/{proposal_id}/rotate-link", summary="Issue a new share token")
def rotate_link(proposal_id: uuid.UUID, ctx: Reviewer, db: DbSession) -> ProposalOut:
    get_owned(db, Proposal, proposal_id, ctx)
    not_implemented("Share link rotation")


@router.post("/proposals/{proposal_id}/revoke-link", summary="Disable the share link")
def revoke_link(proposal_id: uuid.UUID, ctx: Reviewer, db: DbSession) -> ProposalOut:
    get_owned(db, Proposal, proposal_id, ctx)
    not_implemented("Share link revocation")


@router.post("/proposals/{proposal_id}/mark-accepted", summary="Record the client's acceptance")
def mark_accepted(
    proposal_id: uuid.UUID, body: OptionChoiceIn, ctx: Reviewer, db: DbSession
) -> ProposalOut:
    get_owned(db, Proposal, proposal_id, ctx)
    not_implemented("Proposal acceptance")


@router.post("/proposals/{proposal_id}/mark-booked", summary="Book it; sets the trip to booked")
def mark_booked(
    proposal_id: uuid.UUID, body: OptionChoiceIn, ctx: Reviewer, db: DbSession
) -> ProposalOut:
    get_owned(db, Proposal, proposal_id, ctx)
    not_implemented("Proposal booking")


@router.post("/proposals/{proposal_id}/decline", summary="The client declined")
def decline_proposal(proposal_id: uuid.UUID, ctx: Reviewer, db: DbSession) -> ProposalOut:
    get_owned(db, Proposal, proposal_id, ctx)
    not_implemented("Proposal decline")


@router.post("/proposals/{proposal_id}/cancel", summary="Cancel a draft or sent proposal")
def cancel_proposal(proposal_id: uuid.UUID, ctx: Reviewer, db: DbSession) -> ProposalOut:
    get_owned(db, Proposal, proposal_id, ctx)
    not_implemented("Proposal cancel")


@router.post(
    "/proposals/{proposal_id}/revise",
    status_code=status.HTTP_201_CREATED,
    summary="Clone into a new draft; the old link then returns 410",
)
def revise_proposal(proposal_id: uuid.UUID, ctx: Reviewer, db: DbSession) -> ProposalOut:
    get_owned(db, Proposal, proposal_id, ctx)
    not_implemented("Proposal revise")
