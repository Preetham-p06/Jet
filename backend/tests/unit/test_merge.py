"""Quote resolution, operator matching and the field-merge table (spec §3.5)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import NotFound
from app.extraction.types import ExtractionResult
from app.models import Operator, Quote, QuoteField, SourceDocument, Trip, TripOperator, Workspace
from app.models.enums import (
    DocumentChannel,
    FeeCategory,
    FieldStatus,
    OperatorSource,
    TripOperatorStatus,
)
from app.services import merge
from app.services.operators import match_operator, parse_sender, sender_label
from tests import factories
from tests.fakes import empty_result, fee, scalar

T0 = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)
NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


def result(*items: Any, intent: str = "quote") -> ExtractionResult:
    base = empty_result(intent)
    fields = [i for i in items if hasattr(i, "key")]
    fees = [i for i in items if hasattr(i, "category")]
    return base.model_copy(update={"fields": fields, "fees": fees})


@pytest.fixture
def ws(db: Session) -> Workspace:
    return factories.make_workspace(db, "Merge Brokerage")


@pytest.fixture
def trip(db: Session, ws: Workspace) -> Trip:
    return factories.make_trip(db, ws, reference="JS184")


def doc(db: Session, trip: Trip, minutes: int, **kw: Any) -> SourceDocument:
    return factories.make_document(db, trip, received_at=T0 + timedelta(minutes=minutes), **kw)


def current(db: Session, quote: Quote, key: str) -> QuoteField:
    row = merge.current_field(db, quote.id, key)
    assert row is not None
    return row


def rows(db: Session, quote: Quote, key: str) -> list[QuoteField]:
    return list(
        db.scalars(
            select(QuoteField)
            .where(QuoteField.quote_id == quote.id, QuoteField.key == key)
            .order_by(QuoteField.created_at)
        )
    )


@pytest.fixture
def quote(db: Session, trip: Trip, ws: Workspace) -> Quote:
    op = factories.make_operator(db, ws, "Summit Executive Aviation")
    return factories.make_quote(db, trip, op)


def run(db: Session, quote: Quote, d: SourceDocument, r: ExtractionResult) -> merge.MergeReport:
    return merge.merge_result(db, quote, d, r, review_threshold=75, now=NOW)


# --------------------------------------------------------------------------- keys


def test_key_for_fields_and_fees() -> None:
    assert merge.key_for(scalar("seats", 8)) == "seats"
    assert merge.key_for(fee(FeeCategory.FUEL_SURCHARGE, "stated", 1)) == "fee.fuel_surcharge"
    assert (
        merge.key_for(fee(FeeCategory.OTHER, "stated", 1, label="Cleaning fee"))
        == "fee.other.cleaning_fee"
    )


# --------------------------------------------------------------------------- merge table


def test_insert_when_absent(db: Session, trip: Trip, quote: Quote) -> None:
    d = doc(db, trip, 10)
    report = run(
        db, quote, d, result(scalar("seats", 13), fee(FeeCategory.POSITIONING, "stated", 1900))
    )
    assert sorted(report.inserted) == ["fee.positioning", "seats"]
    f = current(db, quote, "fee.positioning")
    assert f.current_value["amount"] == {"amount_minor": 190000, "currency": "USD"}
    assert f.source_document_id == d.id and f.status is FieldStatus.EXTRACTED


def test_same_value_corroborates(db: Session, trip: Trip, quote: Quote) -> None:
    pdf, sms = doc(db, trip, 312), doc(db, trip, 340)
    run(
        db,
        quote,
        pdf,
        result(scalar("headline_price", {"amount_minor": 3890000, "currency": "USD"}, 95)),
    )
    report = run(
        db,
        quote,
        sms,
        result(scalar("headline_price", {"amount_minor": 3890000, "currency": "USD"}, 82)),
    )
    assert report.corroborated == ["headline_price"]
    f = current(db, quote, "headline_price")
    assert f.confidence == 98  # min(99, max(95, 82) + 3)
    assert f.corroborating_source_ids == [str(sms.id)]
    assert len(rows(db, quote, "headline_price")) == 1


def test_corroboration_caps_at_99(db: Session, trip: Trip, quote: Quote) -> None:
    run(db, quote, doc(db, trip, 1), result(scalar("seats", 9, 98)))
    run(db, quote, doc(db, trip, 2), result(scalar("seats", 9, 98)))
    assert current(db, quote, "seats").confidence == 99


def test_newer_source_supersedes_with_event(db: Session, trip: Trip, quote: Quote) -> None:
    old, new = doc(db, trip, 10), doc(db, trip, 60, channel=DocumentChannel.WHATSAPP)
    run(db, quote, old, result(fee(FeeCategory.POSITIONING, "stated", 1200)))
    report = run(db, quote, new, result(fee(FeeCategory.POSITIONING, "stated", 900)))
    assert report.superseded == ["fee.positioning"]
    assert report.events == ["Revised: positioning 1,200 → 900 (WhatsApp)"]
    first, second = rows(db, quote, "fee.positioning")
    assert not first.is_current and first.superseded_by_id == second.id
    assert second.is_current and second.source_document_id == new.id


def test_older_source_processed_later_is_history(db: Session, trip: Trip, quote: Quote) -> None:
    newer, older = doc(db, trip, 60), doc(db, trip, 10)
    run(db, quote, newer, result(fee(FeeCategory.POSITIONING, "stated", 900)))
    report = run(db, quote, older, result(fee(FeeCategory.POSITIONING, "stated", 1200)))
    assert report.history_only == ["fee.positioning"]
    cur = current(db, quote, "fee.positioning")
    assert cur.source_document_id == newer.id
    hist = [r for r in rows(db, quote, "fee.positioning") if not r.is_current]
    assert hist[0].superseded_by_id == cur.id  # history, not an open conflict
    assert merge.open_candidates(db, quote.id, "fee.positioning") == []


def test_locked_value_conflict(db: Session, trip: Trip, quote: Quote) -> None:
    run(db, quote, doc(db, trip, 10), result(scalar("seats", 8)))
    f = current(db, quote, "seats")
    f.status, f.locked = FieldStatus.VERIFIED, True
    db.flush()
    report = run(db, quote, doc(db, trip, 60), result(scalar("seats", 9)))
    assert report.conflicts == ["seats"]
    assert current(db, quote, "seats").current_value == 8
    [cand] = merge.open_candidates(db, quote.id, "seats")
    assert cand.current_value == 9 and not cand.is_current


def test_locked_same_value_still_corroborates(db: Session, trip: Trip, quote: Quote) -> None:
    run(db, quote, doc(db, trip, 10), result(scalar("seats", 8, 80)))
    f = current(db, quote, "seats")
    f.status, f.locked = FieldStatus.VERIFIED, True
    db.flush()
    report = run(db, quote, doc(db, trip, 60), result(scalar("seats", 8, 80)))
    assert report.corroborated == ["seats"]


def test_weaker_newer_value_is_a_conflict(db: Session, trip: Trip, quote: Quote) -> None:
    run(db, quote, doc(db, trip, 10), result(fee(FeeCategory.FUEL_SURCHARGE, "stated", 1400)))
    report = run(
        db,
        quote,
        doc(db, trip, 60),
        result(fee(FeeCategory.FUEL_SURCHARGE, "estimated", 850, confidence=61, hedged=True)),
    )
    assert report.conflicts == ["fee.fuel_surcharge"]
    assert current(db, quote, "fee.fuel_surcharge").current_value["status"] == "stated"
    assert len(merge.open_candidates(db, quote.id, "fee.fuel_surcharge")) == 1


def test_weaker_value_supersedes_a_low_confidence_stated(
    db: Session, trip: Trip, quote: Quote
) -> None:
    run(
        db,
        quote,
        doc(db, trip, 10),
        result(fee(FeeCategory.FUEL_SURCHARGE, "stated", 1400, confidence=60)),
    )
    report = run(
        db, quote, doc(db, trip, 60), result(fee(FeeCategory.FUEL_SURCHARGE, "estimated", 850))
    )
    assert report.superseded == ["fee.fuel_surcharge"]


def test_same_document_reprocess_replaces_unless_locked(
    db: Session, trip: Trip, quote: Quote
) -> None:
    d = doc(db, trip, 10)
    run(db, quote, d, result(scalar("seats", 8)))
    report = run(db, quote, d, result(scalar("seats", 9)))
    assert report.replaced == ["seats"]
    assert current(db, quote, "seats").current_value == 9
    # The same reading again is a no-op.
    again = run(db, quote, d, result(scalar("seats", 9)))
    assert again.replaced == [] and again.inserted == [] and again.corroborated == []

    f = current(db, quote, "seats")
    f.status, f.locked = FieldStatus.EDITED, True
    db.flush()
    locked = run(db, quote, d, result(scalar("seats", 12)))
    assert locked.conflicts == ["seats"]
    assert current(db, quote, "seats").current_value == 9


def test_later_message_in_the_same_document_wins(db: Session, trip: Trip, quote: Quote) -> None:
    quoted = scalar("headline_price", {"amount_minor": 4000000, "currency": "USD"})
    fresh = scalar("headline_price", {"amount_minor": 3950000, "currency": "USD"}).model_copy(
        update={"sequence": 1}
    )
    report = run(db, quote, doc(db, trip, 10), result(fresh, quoted))
    assert report.inserted == ["headline_price"] and report.superseded == ["headline_price"]
    assert current(db, quote, "headline_price").current_value["amount_minor"] == 3950000


def test_invalid_value_is_skipped_with_an_event(db: Session, trip: Trip, quote: Quote) -> None:
    report = run(
        db,
        quote,
        doc(db, trip, 10),
        result(scalar("aircraft_category", "spaceship"), scalar("seats", 9)),
    )
    assert report.inserted == ["seats"]
    assert any(e.startswith("Skipped an invalid value") for e in report.events)
    assert merge.current_field(db, quote.id, "aircraft_category") is None


def test_same_value_at_a_new_sequence_is_a_no_op(db: Session, trip: Trip, quote: Quote) -> None:
    d = doc(db, trip, 10)
    first = scalar("seats", 9)
    run(db, quote, d, result(first))
    later = first.model_copy(update={"sequence": 3})
    report = run(db, quote, d, result(later))
    assert (report.inserted, report.replaced, report.superseded, report.corroborated) == (
        [],
        [],
        [],
        [],
    )
    assert len(rows(db, quote, "seats")) == 1
    assert current(db, quote, "seats").sequence == 0


def test_superseding_clears_stale_conflicts(db: Session, trip: Trip, quote: Quote) -> None:
    run(db, quote, doc(db, trip, 10), result(fee(FeeCategory.RAMP_HANDLING, "stated", 480)))
    run(db, quote, doc(db, trip, 20), result(fee(FeeCategory.RAMP_HANDLING, "estimated", 500)))
    assert len(merge.open_candidates(db, quote.id, "fee.ramp_handling")) == 1
    run(db, quote, doc(db, trip, 30), result(fee(FeeCategory.RAMP_HANDLING, "stated", 520)))
    assert merge.open_candidates(db, quote.id, "fee.ramp_handling") == []


# --------------------------------------------------------------------------- resolution


def test_resolve_by_sender_email_and_marks_rfq_quoted(
    db: Session, trip: Trip, ws: Workspace
) -> None:
    op = factories.make_operator(db, ws, "Atlas Air Charter", email="quotes@atlas.example")
    rfq = factories.make_trip_operator(db, trip, op, requested_at=T0)
    d = doc(db, trip, 84, sender="Atlas Air Charter <quotes@atlas.example>")
    res = merge.resolve_quote(db, trip, d, empty_result(), now=NOW)
    assert res.operator is op and res.created_quote and res.quote is not None
    assert rfq.status is TripOperatorStatus.QUOTED
    assert rfq.responded_at == T0 + timedelta(minutes=84)
    assert res.quote.first_received_at == d.received_at
    # A later document keeps the earliest response time and reuses the quote.
    d2 = doc(db, trip, 180, sender="quotes@atlas.example")
    res2 = merge.resolve_quote(db, trip, d2, empty_result(), now=NOW)
    assert res2.quote is res.quote and not res2.created_quote
    assert rfq.responded_at == T0 + timedelta(minutes=84)
    assert res.quote.last_received_at == d2.received_at


def test_resolve_by_extracted_name_variants(db: Session, trip: Trip, ws: Workspace) -> None:
    op = factories.make_operator(db, ws, "Summit Executive Aviation", aliases=["Summit Exec"])
    for name in (
        "Summit Executive Aviation",
        "SUMMIT EXEC",
        "Summit Jets",
        "Sumit Executive Aviation",
    ):
        m = match_operator(db, ws.id, sender=None, name=name)
        assert m is not None and m.operator is op, name
    assert match_operator(db, ws.id, sender=None, name="Northstar Jets") is None


def test_resolve_by_phone_and_domain(db: Session, ws: Workspace) -> None:
    op = factories.make_operator(
        db,
        ws,
        "Summit",
        phone="+16175550142",
        email="dan@summit-exec.example",
        email_domain="summit-exec.example",
    )
    assert match_operator(db, ws.id, sender="Dan <+1 (617) 555-0142>", name=None).method == "phone"  # type: ignore[union-attr]
    m = match_operator(db, ws.id, sender="ops@summit-exec.example", name=None)
    assert m is not None and m.operator is op and m.method == "domain"
    # Webmail domains never match on domain alone.
    factories.make_operator(db, ws, "Solo", email="solo@gmail.com", email_domain=None)
    assert match_operator(db, ws.id, sender="other@gmail.com", name=None) is None


def test_parse_sender() -> None:
    assert parse_sender("Atlas <Q@Atlas.example>") == ("Atlas", "q@atlas.example", None)
    assert parse_sender("+1 617 555 0142") == (None, None, "16175550142")
    assert sender_label("Summit <+16175550142>") == "Summit"


def test_new_operator_from_confident_name(db: Session, trip: Trip, ws: Workspace) -> None:
    d = doc(db, trip, 10, sender="someone@newco.example")
    res = merge.resolve_quote(
        db, trip, d, result(scalar("operator_name", "NewCo Aviation", 90)), now=NOW
    )
    assert res.created_operator and res.operator is not None
    assert res.operator.name == "NewCo Aviation"
    assert res.operator.source is OperatorSource.EXTRACTION
    assert res.operator.email_domain == "newco.example"
    rfq = db.scalars(select(TripOperator).where(TripOperator.operator_id == res.operator.id)).one()
    assert rfq.status is TripOperatorStatus.QUOTED


def test_low_confidence_name_uses_sender_label(db: Session, trip: Trip) -> None:
    d = doc(db, trip, 10, sender="Jet Guy <jet@guy.example>")
    res = merge.resolve_quote(db, trip, d, result(scalar("operator_name", "Blurry", 40)), now=NOW)
    assert res.operator is not None and res.operator.name == "Jet Guy"
    assert res.created_operator
    assert res.operator.source is OperatorSource.EXTRACTION
    assert res.operator.email == "jet@guy.example"
    assert db.scalars(select(Operator).where(Operator.name == "Blurry")).first() is None


def test_decline_marks_rfq_declined_without_quote(db: Session, trip: Trip, ws: Workspace) -> None:
    op = factories.make_operator(db, ws, "Harbor Jet Group", email="ops@harbor.example")
    rfq = factories.make_trip_operator(db, trip, op, requested_at=T0)
    d = doc(db, trip, 240, sender="ops@harbor.example")
    res = merge.resolve_quote(db, trip, d, empty_result("decline"), now=NOW)
    assert res.quote is None and res.operator is op
    assert rfq.status is TripOperatorStatus.DECLINED
    assert rfq.responded_at == T0 + timedelta(minutes=240)
    assert db.scalars(select(Quote).where(Quote.trip_id == trip.id)).all() == []


def test_explicit_ids_are_scoped(db: Session, trip: Trip, ws: Workspace) -> None:
    other_ws = factories.make_workspace(db, "Other")
    other_trip = factories.make_trip(db, other_ws, reference="JS999")
    other_op = factories.make_operator(db, other_ws, "Foreign")
    other_quote = factories.make_quote(db, other_trip, other_op)
    d = doc(db, trip, 10)
    with pytest.raises(NotFound):
        merge.resolve_quote(db, trip, d, empty_result(), quote_id=other_quote.id, now=NOW)
    with pytest.raises(NotFound):
        merge.resolve_quote(db, trip, d, empty_result(), operator_id=other_op.id, now=NOW)
    op = factories.make_operator(db, ws, "Atlas")
    res = merge.resolve_quote(db, trip, d, empty_result(), operator_id=op.id, now=NOW)
    assert isinstance(res.operator, Operator) and res.operator.id == op.id
    # An RFQ-row id works as an operator id.
    rfq = db.scalars(select(TripOperator).where(TripOperator.operator_id == op.id)).one()
    res2 = merge.resolve_quote(
        db, trip, doc(db, trip, 20), empty_result(), operator_id=rfq.id, now=NOW
    )
    assert res2.quote is res.quote
