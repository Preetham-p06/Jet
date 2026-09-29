"""Rows for API tests, built with the factories (no pipeline needed)."""

from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import FeeLine, Invite, Proposal, ProposalOption, Quote
from app.models.enums import (
    AmountStatus,
    FeeCategory,
    FlagSeverity,
    FlagType,
    ProposalStatus,
    Role,
    ValueType,
)
from app.models.trip import Trip
from app.models.workspace import Workspace
from app.services.storage import Storage
from tests import factories
from tests.factories_p5 import make_ready_quote


@dataclass
class Seeded:
    operator_id: uuid.UUID
    trip_operator_id: uuid.UUID
    quote_id: uuid.UUID
    field_id: uuid.UUID
    flag_id: uuid.UUID
    document_id: uuid.UUID
    proposal_id: uuid.UUID
    option_id: uuid.UUID
    invite_id: uuid.UUID
    user_id: uuid.UUID
    share_token: str


def add_fee_line(
    db: Session,
    quote: Quote,
    category: FeeCategory,
    status: AmountStatus,
    amount_cents: int | None,
    **kw: object,
) -> FeeLine:
    line = FeeLine(
        workspace_id=quote.workspace_id,
        quote_id=quote.id,
        category=category,
        label=str(kw.pop("label", category.value.replace("_", " ").capitalize())),
        amount_status=status,
        amount_cents=amount_cents,
        counts_in_known=status is AmountStatus.STATED,
        counts_in_upper=status in (AmountStatus.STATED, AmountStatus.ESTIMATED),
        **kw,
    )
    db.add(line)
    db.flush()
    return line


def add_option(db: Session, proposal: Proposal, quote: Quote, **kw: object) -> ProposalOption:
    cost = quote.known_total_cents or 0
    option = ProposalOption(
        workspace_id=proposal.workspace_id,
        proposal_id=proposal.id,
        quote_id=quote.id,
        cost_basis_cents=cost,
        markup_cents=kw.pop("markup_cents", 0),
        client_total_cents=kw.pop("client_total_cents", cost),
        **kw,
    )
    db.add(option)
    db.flush()
    return option


def seed_workspace(
    db: Session, workspace: Workspace, trip: Trip, storage: Storage, *, name: str = "Atlas"
) -> Seeded:
    """One of everything a by-id route can address, in `workspace`."""
    stored = storage.put(
        workspace.id, b"%PDF-1.7 demo", suffix=".pdf", content_type="application/pdf"
    )
    operator = factories.make_operator(db, workspace, f"{name} Air Charter")
    rfq = factories.make_trip_operator(db, trip, operator)
    quote = make_ready_quote(db, trip, operator, trip_operator_id=rfq.id)
    document = factories.make_document(
        db,
        trip,
        storage_key=stored.key,
        media_type="application/pdf",
        original_filename=f"{name.lower()}_quote_01.pdf",
        quote_id=quote.id,
    )
    field = factories.make_field(
        db, quote, "seats", 8, value_type=ValueType.INT, source_document_id=document.id
    )
    flag = factories.make_flag(
        db, quote, type=FlagType.AMBIGUOUS_CHARGE, severity=FlagSeverity.INFO, blocking=False
    )
    proposal = factories.make_proposal(
        db,
        trip,
        status=ProposalStatus.SENT,
        share_token=secrets.token_urlsafe(32),
        share_enabled=True,
        share_expires_at=factories.now() + timedelta(days=30),
        markup_pct=Decimal("5"),
    )
    option = add_option(db, proposal, quote)
    admin = factories.make_user(db, workspace, Role.BROKER)
    invite = Invite(
        workspace_id=workspace.id,
        email=f"invitee-{uuid.uuid4().hex[:6]}@example.com",
        role=Role.BROKER,
        token_hash=secrets.token_hex(32),
        invited_by_id=admin.id,
        expires_at=factories.now() + timedelta(days=7),
    )
    db.add(invite)
    db.commit()
    assert proposal.share_token is not None
    return Seeded(
        operator_id=operator.id,
        trip_operator_id=rfq.id,
        quote_id=quote.id,
        field_id=field.id,
        flag_id=flag.id,
        document_id=document.id,
        proposal_id=proposal.id,
        option_id=option.id,
        invite_id=invite.id,
        user_id=admin.id,
        share_token=proposal.share_token,
    )
