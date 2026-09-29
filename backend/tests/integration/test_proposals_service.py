"""Proposal service: eligibility, create/edit, send, lifecycle and the public view."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.errors import Conflict, Gone, NotFound, Unprocessable
from app.models import AuditEvent, Operator, Proposal, Quote, Trip, Workspace
from app.models.enums import (
    ActorKind,
    Availability,
    FieldStatus,
    ProposalStatus,
    QuoteStatus,
    TripStatus,
    ValueType,
)
from app.permissions import RequestContext
from app.schemas.proposal import ProposalCreate, ProposalOptionIn, ProposalPatch
from app.services import proposals as svc
from app.services.contracts import IneligibilityCode
from tests import factories
from tests.factories_p5 import NOW, make_ctx, make_ready_quote, p5_settings

SETTINGS = p5_settings()


@dataclass
class Env:
    ws: Workspace
    ctx: RequestContext
    trip: Trip
    atlas: Quote
    sky: Quote
    summit: Quote
    atlas_op: Operator


@pytest.fixture
def env(db: Session) -> Env:
    ws = factories.make_workspace(db, "Skyline Brokerage", default_markup_pct=Decimal("5"))
    ctx = make_ctx(db, ws)
    trip = factories.make_trip(db, ws, reference="JS184", pax=7, client_name="Dana Whitfield")
    atlas_op = factories.make_operator(db, ws, "Atlas Air Charter")
    sky_op = factories.make_operator(db, ws, "SkyBridge Jets")
    summit_op = factories.make_operator(db, ws, "Summit Aviation")
    atlas = make_ready_quote(
        db,
        trip,
        atlas_op,
        known_total_cents=4_398_000,
        is_recommended=True,
        aircraft_model="Atlas Citation Latitude",
    )
    sky = make_ready_quote(db, trip, sky_op, known_total_cents=4_283_000)
    summit = make_ready_quote(
        db, trip, summit_op, known_total_cents=4_100_000, open_blocking_flags=1
    )
    db.commit()
    return Env(ws, ctx, trip, atlas, sky, summit, atlas_op)


def _sent(db: Session, env: Env) -> Proposal:
    proposal = svc.create_proposal(db, env.ctx, env.trip, ProposalCreate())
    svc.send_proposal(db, env.ctx, proposal, settings=SETTINGS, now=NOW)
    db.commit()
    return proposal


def _actions(db: Session) -> list[str]:
    return list(db.scalars(select(AuditEvent.action).order_by(AuditEvent.created_at)))


# --------------------------------------------------------------------------- eligibility


def test_eligibility_reports_every_reason(db: Session, env: Env) -> None:
    q = env.sky
    q.status = QuoteStatus.WITHDRAWN
    q.headline_cents = None
    q.is_fully_priced = False
    q.open_blocking_flags = 2
    q.seats = 6
    q.availability = Availability.UNAVAILABLE
    factories.make_field(db, q, key="fee.fuel_surcharge", value=None, confidence=61)
    db.flush()
    elig = svc.proposal_eligibility(db, q, env.trip, review_threshold=75)
    assert not elig.eligible
    codes = {r.code for r in elig.reasons}
    assert codes == set(IneligibilityCode)
    by_code = {r.code: r.message for r in elig.reasons}
    assert "6 seats for 7" in by_code[IneligibilityCode.INSUFFICIENT_CAPACITY]
    assert "fee.fuel_surcharge (61)" in by_code[IneligibilityCode.UNREVIEWED_LOW_CONFIDENCE]


def test_locked_or_nonmaterial_low_confidence_fields_do_not_block(db: Session, env: Env) -> None:
    factories.make_field(
        db,
        env.sky,
        key="fee.fuel_surcharge",
        value=None,
        confidence=61,
        status=FieldStatus.ACCEPTED,
        locked=True,
    )
    factories.make_field(db, env.sky, key="tail_number", value="N1", confidence=40)
    factories.make_field(
        db, env.sky, key="seats", value=8, confidence=60, is_current=False, value_type=ValueType.INT
    )
    db.flush()
    assert svc.proposal_eligibility(db, env.sky, env.trip, review_threshold=75).eligible
    assert svc.proposal_eligibility(db, env.sky, env.trip, review_threshold=75).reasons == ()


def test_unknown_seats_is_insufficient_capacity(db: Session, env: Env) -> None:
    env.sky.seats = None
    elig = svc.proposal_eligibility(db, env.sky, env.trip, review_threshold=75)
    assert [r.code for r in elig.reasons] == [IneligibilityCode.INSUFFICIENT_CAPACITY]


# --------------------------------------------------------------------------- create / edit


def test_create_defaults_to_eligible_recommended_first(db: Session, env: Env) -> None:
    proposal = svc.create_proposal(db, env.ctx, env.trip, ProposalCreate())
    db.commit()
    assert proposal.status is ProposalStatus.DRAFT
    assert proposal.markup_pct == Decimal("5")
    assert proposal.client_name == "Dana Whitfield"
    assert proposal.title == "JS184 charter options"
    opts = sorted(proposal.options, key=lambda o: o.sort_order)
    assert [o.quote_id for o in opts] == [env.atlas.id, env.sky.id]  # Summit is blocked
    assert opts[0].is_recommended
    atlas = opts[0]
    assert atlas.cost_basis_cents == 4_398_000
    assert atlas.client_total_cents == 4_617_900  # 43,980 x 1.05 = 46,179
    assert atlas.markup_cents == 219_900
    assert _actions(db) == ["proposal.create"]


def test_create_orders_non_recommended_by_client_total(db: Session, env: Env) -> None:
    env.atlas.is_recommended = False
    proposal = svc.create_proposal(db, env.ctx, env.trip, ProposalCreate(markup_pct=Decimal("0")))
    opts = sorted(proposal.options, key=lambda o: o.sort_order)
    assert [o.quote_id for o in opts] == [env.sky.id, env.atlas.id]
    assert opts[0].client_total_cents == 4_283_000


def test_explicit_ineligible_quote_is_422_with_reasons(db: Session, env: Env) -> None:
    with pytest.raises(Unprocessable) as exc:
        svc.create_proposal(
            db, env.ctx, env.trip, ProposalCreate(quote_ids=[env.atlas.id, env.summit.id])
        )
    assert exc.value.code == "ineligible_quotes"
    assert exc.value.fields is not None
    reasons = exc.value.fields[str(env.summit.id)]
    assert reasons == [{"code": "blocking_flags", "message": "1 open blocking flag"}]
    assert str(env.atlas.id) not in exc.value.fields


def test_create_rejects_foreign_and_missing_quotes(db: Session, env: Env) -> None:
    other_trip = factories.make_trip(db, env.ws, reference="JS999")
    other = make_ready_quote(db, other_trip, env.atlas_op)
    with pytest.raises(NotFound):
        svc.create_proposal(db, env.ctx, env.trip, ProposalCreate(quote_ids=[other.id]))


def test_create_with_nothing_eligible_is_422(db: Session, env: Env) -> None:
    env.atlas.open_blocking_flags = 1
    env.sky.is_fully_priced = False
    with pytest.raises(Unprocessable) as exc:
        svc.create_proposal(db, env.ctx, env.trip, ProposalCreate())
    assert exc.value.code == "no_eligible_quotes"


def test_update_reorders_reprices_and_audits(db: Session, env: Env) -> None:
    proposal = svc.create_proposal(db, env.ctx, env.trip, ProposalCreate())
    db.commit()
    patch = ProposalPatch(
        options=[
            ProposalOptionIn(quote_id=env.sky.id, markup_pct_override=Decimal("10")),
            ProposalOptionIn(quote_id=env.atlas.id),
        ],
        markup_pct=Decimal("0"),
        title="Miami options",
    )
    svc.update_proposal(db, env.ctx, proposal, patch)
    db.commit()
    opts = sorted(proposal.options, key=lambda o: o.sort_order)
    assert [o.quote_id for o in opts] == [env.sky.id, env.atlas.id]
    assert opts[0].client_total_cents == 4_711_300  # 42,830 x 1.10
    assert opts[1].client_total_cents == 4_398_000
    assert proposal.title == "Miami options"

    # Drop one option, then add it back: no unique-constraint clash.
    patch = ProposalPatch(options=[ProposalOptionIn(quote_id=env.sky.id)])
    svc.update_proposal(db, env.ctx, proposal, patch)
    db.commit()
    assert [o.quote_id for o in proposal.options] == [env.sky.id]
    svc.update_proposal(
        db,
        env.ctx,
        proposal,
        ProposalPatch(
            options=[ProposalOptionIn(quote_id=env.atlas.id), ProposalOptionIn(quote_id=env.sky.id)]
        ),
    )
    db.commit()
    assert len(proposal.options) == 2

    event = db.scalars(select(AuditEvent).where(AuditEvent.action == "proposal.update")).first()
    assert event is not None and event.before is not None and event.after is not None
    assert event.after["title"] == "Miami options"


def test_update_rejects_ineligible_and_non_drafts(db: Session, env: Env) -> None:
    proposal = svc.create_proposal(db, env.ctx, env.trip, ProposalCreate())
    with pytest.raises(Unprocessable):
        svc.update_proposal(
            db, env.ctx, proposal, ProposalPatch(options=[ProposalOptionIn(quote_id=env.summit.id)])
        )
    svc.send_proposal(db, env.ctx, proposal, settings=SETTINGS, now=NOW)
    with pytest.raises(Conflict) as exc:
        svc.update_proposal(db, env.ctx, proposal, ProposalPatch(title="x"))
    assert exc.value.code == "proposal_not_draft"


# --------------------------------------------------------------------------- send


def test_send_freezes_snapshots_and_creates_link(db: Session, env: Env) -> None:
    proposal = _sent(db, env)
    assert proposal.status is ProposalStatus.SENT
    assert proposal.sent_at == NOW and proposal.sent_by_id == env.ctx.user_id
    assert proposal.share_token is not None and len(proposal.share_token) >= 43
    assert proposal.share_enabled
    assert proposal.share_expires_at == NOW + timedelta(days=30)
    for option in proposal.options:
        assert option.client_snapshot is not None and option.broker_snapshot is not None
        assert option.snapshot_at == NOW
    assert env.trip.status is TripStatus.PROPOSED
    assert "proposal.send" in _actions(db)

    # Later quote changes do not reach the frozen views.
    env.atlas.known_total_cents = 9_999_900
    env.atlas.aircraft_model = "Gulfstream G650"
    db.commit()
    view = svc.public_view(db, proposal)
    assert view.options[0].client_total_cents == 4_617_900
    broker = svc.broker_view(db, proposal, settings=SETTINGS)
    assert broker.options[0].known_total_cents == 4_398_000
    assert broker.options[0].operator_name == "Atlas Air Charter"
    assert broker.share_url == f"https://app.example.test/p/{proposal.share_token}"


def test_send_rechecks_eligibility(db: Session, env: Env) -> None:
    proposal = svc.create_proposal(db, env.ctx, env.trip, ProposalCreate())
    env.sky.open_blocking_flags = 1
    with pytest.raises(Conflict) as exc:
        svc.send_proposal(db, env.ctx, proposal, settings=SETTINGS, now=NOW)
    assert exc.value.code == "ineligible_quotes"
    assert exc.value.fields is not None and str(env.sky.id) in exc.value.fields
    assert proposal.status is ProposalStatus.DRAFT


def test_send_reprices_from_current_quote(db: Session, env: Env) -> None:
    proposal = svc.create_proposal(db, env.ctx, env.trip, ProposalCreate())
    env.atlas.known_total_cents = 4_400_000
    svc.send_proposal(db, env.ctx, proposal, settings=SETTINGS, now=NOW)
    atlas = next(o for o in proposal.options if o.quote_id == env.atlas.id)
    assert atlas.client_total_cents == 4_620_000


# --------------------------------------------------------------------------- views


def test_broker_view_of_a_draft_is_live(db: Session, env: Env) -> None:
    doc = factories.make_document(db, env.trip, quote_id=env.atlas.id, original_filename="a.pdf")
    proposal = svc.create_proposal(db, env.ctx, env.trip, ProposalCreate())
    view = svc.broker_view(db, proposal, settings=SETTINGS)
    assert view.share_url is None
    first = view.options[0]
    assert first.operator_name == "Atlas Air Charter"
    assert first.tail_number == "N684AC"
    assert first.added_charges_cents == 300_000
    assert first.markup_pct == Decimal("5")
    assert first.markup_cents == 219_900
    assert first.eligible and first.reasons == []
    assert [s.document_id for s in first.sources] == [doc.id]


def test_public_view_is_a_whitelist(db: Session, env: Env) -> None:
    proposal = _sent(db, env)
    view = svc.public_view(db, proposal)
    body = view.model_dump_json()
    for leak in ("Atlas", "SkyBridge", "N684AC", "confidence", "markup", "fee", "4398000"):
        assert leak not in body, leak
    assert set(view.model_dump()) == {
        "title",
        "prepared_for",
        "prepared_by",
        "legs",
        "date",
        "pax",
        "message",
        "options",
        "disclaimer",
        "status",
        "accepted_option_id",
        "expires_at",
    }
    assert view.prepared_by == "Skyline Brokerage"
    assert view.prepared_for == "Dana Whitfield"
    assert view.pax == 7 and view.date.isoformat() == "2026-10-18"
    assert view.legs[0].origin_code in {"KTEB", "TEB"}
    assert view.options[0].aircraft == "Cessna Citation Latitude"
    assert view.options[0].recommended
    assert view.options[0].client_total_cents == 4_617_900


def test_client_preview_of_draft_uses_live_quotes(db: Session, env: Env) -> None:
    proposal = svc.create_proposal(db, env.ctx, env.trip, ProposalCreate())
    view = svc.public_view(db, proposal)
    assert view.status is ProposalStatus.DRAFT
    assert [o.option_id for o in view.options] == [
        o.id for o in sorted(proposal.options, key=lambda o: o.sort_order)
    ]
    assert all(o.client_snapshot is None for o in proposal.options)


# --------------------------------------------------------------------------- public access


def _fresh(session_factory: sessionmaker[Session]) -> Session:
    return session_factory()


def test_public_token_rules(db: Session, env: Env, session_factory: sessionmaker[Session]) -> None:
    proposal = _sent(db, env)
    token = proposal.share_token
    assert token is not None
    with _fresh(session_factory) as s:
        found = svc.get_public_proposal(s, token, now=NOW)
        assert found.id == proposal.id
        assert s.info["workspace_id"] == env.ws.id
    with _fresh(session_factory) as s, pytest.raises(NotFound):
        svc.get_public_proposal(s, "nope" * 8, now=NOW)
    with _fresh(session_factory) as s, pytest.raises(NotFound):
        svc.get_public_proposal(s, token, now=NOW + timedelta(days=31))

    svc.revoke_link(db, env.ctx, proposal, now=NOW)
    db.commit()
    with _fresh(session_factory) as s, pytest.raises(NotFound) as exc:
        svc.get_public_proposal(s, token, now=NOW)
    assert exc.value.detail == "Proposal not found"


def test_public_draft_token_is_404(
    db: Session, env: Env, session_factory: sessionmaker[Session]
) -> None:
    proposal = svc.create_proposal(db, env.ctx, env.trip, ProposalCreate())
    proposal.share_token = "draft-token-abcdefghijklmnop"
    proposal.share_enabled = True
    proposal.share_expires_at = NOW + timedelta(days=1)
    db.commit()
    with _fresh(session_factory) as s, pytest.raises(NotFound):
        svc.get_public_proposal(s, "draft-token-abcdefghijklmnop", now=NOW)


def test_revise_supersedes_and_old_link_is_gone(
    db: Session, env: Env, session_factory: sessionmaker[Session]
) -> None:
    proposal = _sent(db, env)
    token = proposal.share_token
    assert token is not None
    draft = svc.revise(db, env.ctx, proposal, now=NOW)
    db.commit()
    assert proposal.status is ProposalStatus.SUPERSEDED
    assert draft.status is ProposalStatus.DRAFT and draft.supersedes_id == proposal.id
    assert draft.share_token is None
    assert {o.quote_id for o in draft.options} == {o.quote_id for o in proposal.options}
    assert all(o.client_snapshot is None for o in draft.options)
    with _fresh(session_factory) as s, pytest.raises(Gone):
        svc.get_public_proposal(s, token, now=NOW)
    with pytest.raises(Conflict):
        svc.revise(db, env.ctx, draft, now=NOW)
    assert {"proposal.supersede", "proposal.revise"} <= set(_actions(db))


def test_rotate_link_invalidates_old_token(
    db: Session, env: Env, session_factory: sessionmaker[Session]
) -> None:
    proposal = _sent(db, env)
    old = proposal.share_token
    assert old is not None
    svc.rotate_link(db, env.ctx, proposal, settings=SETTINGS, now=NOW + timedelta(days=10))
    db.commit()
    assert proposal.share_token != old
    assert proposal.share_expires_at == NOW + timedelta(days=40)
    with _fresh(session_factory) as s, pytest.raises(NotFound):
        svc.get_public_proposal(s, old, now=NOW)
    with _fresh(session_factory) as s:
        svc.get_public_proposal(s, proposal.share_token or "", now=NOW)


def test_views_are_counted_and_first_is_audited(db: Session, env: Env) -> None:
    proposal = _sent(db, env)
    svc.record_public_view(db, proposal, now=NOW, ip="198.51.100.1", user_agent="UA")
    svc.record_public_view(db, proposal, now=NOW + timedelta(hours=1), ip=None, user_agent=None)
    db.commit()
    assert proposal.view_count == 2
    assert proposal.first_viewed_at == NOW
    assert proposal.last_viewed_at == NOW + timedelta(hours=1)
    events = list(db.scalars(select(AuditEvent).where(AuditEvent.action == "public.proposal_view")))
    assert len(events) == 1
    assert events[0].actor_kind is ActorKind.PUBLIC and events[0].ip == "198.51.100.1"


def test_public_accept(db: Session, env: Env) -> None:
    proposal = _sent(db, env)
    option = proposal.options[1]
    with pytest.raises(Unprocessable):
        svc.public_accept(
            db, proposal, option_id=env.atlas.id, name="Dana", now=NOW, ip=None, user_agent=None
        )
    svc.public_accept(
        db, proposal, option_id=option.id, name="Dana W", now=NOW, ip="1.2.3.4", user_agent="UA"
    )
    db.commit()
    assert proposal.status is ProposalStatus.ACCEPTED
    assert proposal.accepted_option_id == option.id
    assert proposal.accepted_by_name == "Dana W"
    view = svc.public_view(db, proposal)
    assert view.status is ProposalStatus.ACCEPTED and view.accepted_option_id == option.id
    # Same click again is harmless; a different option is a conflict.
    svc.public_accept(
        db, proposal, option_id=option.id, name="Dana W", now=NOW, ip=None, user_agent=None
    )
    with pytest.raises(Conflict):
        svc.public_accept(
            db,
            proposal,
            option_id=proposal.options[0].id,
            name="Dana W",
            now=NOW,
            ip=None,
            user_agent=None,
        )
    event = db.scalars(
        select(AuditEvent).where(AuditEvent.action == "public.proposal_accept")
    ).one()
    assert event.actor_label == "Dana W" and event.actor_kind is ActorKind.PUBLIC


# --------------------------------------------------------------------------- lifecycle


def test_accept_then_book_books_the_trip(db: Session, env: Env) -> None:
    proposal = _sent(db, env)
    with pytest.raises(Unprocessable) as exc:
        svc.mark_accepted(db, env.ctx, proposal, option_id=None, now=NOW)
    assert exc.value.code == "option_required"
    atlas_opt = next(o for o in proposal.options if o.quote_id == env.atlas.id)
    svc.mark_accepted(db, env.ctx, proposal, option_id=atlas_opt.id, now=NOW)
    later = NOW + timedelta(hours=2)
    svc.mark_booked(db, env.ctx, proposal, option_id=None, now=later)
    db.commit()
    assert proposal.status is ProposalStatus.BOOKED and proposal.booked_at == later
    assert env.trip.status is TripStatus.BOOKED
    assert env.trip.booked_quote_id == env.atlas.id
    assert env.trip.booked_at == later
    assert {"proposal.mark_accepted", "proposal.mark_booked", "trip.book"} <= set(_actions(db))
    with pytest.raises(Conflict):
        svc.decline(db, env.ctx, proposal, now=NOW)


def test_decline_and_cancel(db: Session, env: Env) -> None:
    proposal = _sent(db, env)
    svc.decline(db, env.ctx, proposal, now=NOW)
    assert proposal.status is ProposalStatus.DECLINED and proposal.declined_at == NOW
    with pytest.raises(Conflict):
        svc.cancel(db, env.ctx, proposal, now=NOW)

    draft = svc.create_proposal(db, env.ctx, env.trip, ProposalCreate())
    svc.cancel(db, env.ctx, draft, now=NOW)
    assert draft.status is ProposalStatus.CANCELLED and not draft.share_enabled
    with pytest.raises(Conflict):
        svc.send_proposal(db, env.ctx, draft, settings=SETTINGS, now=NOW)


def test_link_actions_need_a_sent_proposal(db: Session, env: Env) -> None:
    draft = svc.create_proposal(db, env.ctx, env.trip, ProposalCreate())
    with pytest.raises(Conflict):
        svc.rotate_link(db, env.ctx, draft, settings=SETTINGS, now=NOW)
    with pytest.raises(Conflict):
        svc.revoke_link(db, env.ctx, draft, now=NOW)
    with pytest.raises(Conflict):
        svc.mark_booked(db, env.ctx, draft, option_id=None, now=NOW)


def test_list_proposals_filters_and_counts(db: Session, env: Env) -> None:
    sent = _sent(db, env)
    svc.create_proposal(db, env.ctx, env.trip, ProposalCreate(quote_ids=[env.sky.id]))
    other_ws = factories.make_workspace(db)
    other_trip = factories.make_trip(db, other_ws)
    factories.make_proposal(db, other_trip)
    db.commit()

    items, total = svc.list_proposals(db, env.ctx)
    assert total == 2 and len(items) == 2
    items, total = svc.list_proposals(db, env.ctx, status=ProposalStatus.SENT)
    assert total == 1 and items[0].id == sent.id
    assert items[0].trip_reference == "JS184"
    assert items[0].option_count == 2
    assert items[0].recommended_client_total_cents == 4_617_900
    items, total = svc.list_proposals(db, env.ctx, trip_id=env.trip.id, limit=1)
    assert total == 2 and len(items) == 1
