"""Ingest and `process_source_document` end to end with the real loader, rules
extractor, merge and recompute (spec §0 "Pipeline", §3)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.config import PipelineMode, Settings
from app.errors import NotFound, PayloadTooLarge, Unprocessable
from app.extraction.base import ExtractorUnavailable
from app.extraction.registry import FallbackExtractor
from app.extraction.rules.extractor import RulesExtractor
from app.models import (
    AuditEvent,
    Flag,
    ProcessingEvent,
    Quote,
    QuoteField,
    SourceDocument,
    Trip,
    TripOperator,
    Workspace,
)
from app.models.enums import (
    DocumentChannel,
    DocumentKind,
    ExtractionStatus,
    FlagStatus,
    FlagType,
    ProcessingStep,
    Role,
    TripOperatorStatus,
)
from app.permissions import RequestContext
from app.services import pipeline
from app.services.storage import LocalStorage
from tests import factories
from tests.factories_p5 import make_ctx
from tests.fakes import FakeExtractor, empty_result, scalar

pytestmark = pytest.mark.integration

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "demo"
T0 = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)
RULES = RulesExtractor()


@pytest.fixture
def storage(settings: Settings) -> LocalStorage:
    return LocalStorage(settings.storage_dir)


@pytest.fixture
def ws(db: Session) -> Workspace:
    return factories.make_workspace(db, "Pipeline Brokerage")


@pytest.fixture
def ctx(db: Session, ws: Workspace) -> RequestContext:
    return make_ctx(db, ws, Role.BROKER)


@pytest.fixture
def trip(db: Session, ws: Workspace) -> Trip:
    return factories.make_trip(db, ws, reference="JS184")


def cmd(name: str, minutes: int, **kw: object) -> pipeline.IngestCommand:
    return pipeline.IngestCommand(
        data=(FIXTURES / name).read_bytes(),
        filename=name,
        received_at=T0 + timedelta(minutes=minutes),
        **kw,  # type: ignore[arg-type]
    )


def ingest(
    db: Session,
    ctx: RequestContext,
    trip: Trip,
    c: pipeline.IngestCommand,
    settings: Settings,
    storage: LocalStorage,
    extractor: object = RULES,
) -> pipeline.IngestOutcome:
    return pipeline.ingest(
        db,
        ctx,
        trip,
        c,
        settings=settings,
        storage=storage,
        extractor=extractor,  # type: ignore[arg-type]
    )


def events(db: Session, trip: Trip) -> list[ProcessingEvent]:
    return list(
        db.scalars(
            select(ProcessingEvent)
            .where(ProcessingEvent.trip_id == trip.id)
            .order_by(ProcessingEvent.created_at, ProcessingEvent.id)
        )
    )


def test_ingest_pdf_creates_quote_fields_and_events(
    db: Session, ctx: RequestContext, trip: Trip, settings: Settings, storage: LocalStorage
) -> None:
    op = factories.make_operator(
        db, ctx.workspace, "Atlas Air Charter", email="quotes@atlas-air-charter.example"
    )
    rfq = factories.make_trip_operator(db, trip, op, requested_at=T0)
    out = ingest(
        db,
        ctx,
        trip,
        cmd(
            "atlas_quote_01.pdf",
            84,
            channel=DocumentChannel.PDF_UPLOAD,
            sender="Atlas Air Charter <quotes@atlas-air-charter.example>",
        ),
        settings,
        storage,
    )
    assert not out.duplicate and not out.queued and out.created_quote
    assert out.quote is not None and out.quote.operator_id == op.id
    doc = out.document
    assert doc.extraction_status is ExtractionStatus.SUCCEEDED
    assert doc.kind is DocumentKind.PDF and doc.page_count == 2
    assert doc.extractor == "rules" and doc.extraction_result is not None
    assert doc.quote_id == out.quote.id
    assert storage.open(doc.storage_key, workspace_id=trip.workspace_id).startswith(b"%PDF")
    assert out.quote.known_total_cents == 4_482_000 and out.quote.is_fully_priced
    assert out.quote.is_recommended and out.quote.fit_score is not None
    assert rfq.status is TripOperatorStatus.QUOTED
    assert rfq.responded_at == T0 + timedelta(minutes=84)

    steps = {e.step for e in events(db, trip)}
    assert steps == set(ProcessingStep)
    assert (
        db.scalars(select(AuditEvent).where(AuditEvent.action == "document.ingest")).one().entity_id
        == doc.id
    )


def test_duplicate_upload_returns_existing_document(
    db: Session, ctx: RequestContext, trip: Trip, settings: Settings, storage: LocalStorage
) -> None:
    first = ingest(db, ctx, trip, cmd("operator_quote_18.pdf", 216), settings, storage)
    again = ingest(db, ctx, trip, cmd("operator_quote_18.pdf", 300), settings, storage)
    assert again.duplicate and again.document.id == first.document.id
    assert again.quote is not None and first.quote is not None
    assert again.quote.id == first.quote.id
    assert len(db.scalars(select(SourceDocument)).all()) == 1
    # Another trip may hold the same bytes.
    other = factories.make_trip(db, ctx.workspace, reference="JS185")
    third = ingest(db, ctx, other, cmd("operator_quote_18.pdf", 216), settings, storage)
    assert not third.duplicate


def test_multi_source_merge_for_summit(
    db: Session, ctx: RequestContext, trip: Trip, settings: Settings, storage: LocalStorage
) -> None:
    pdf = ingest(
        db,
        ctx,
        trip,
        cmd("revised-quote.pdf", 312, sender="Summit Executive Aviation <dan@summit-exec.example>"),
        settings,
        storage,
    )
    sms = ingest(
        db,
        ctx,
        trip,
        cmd(
            "summit_sms.txt",
            340,
            channel=DocumentChannel.SMS,
            sender="Summit Executive Aviation <+16175550142>",
        ),
        settings,
        storage,
    )
    assert pdf.quote is not None and sms.quote is not None
    assert sms.quote.id == pdf.quote.id and not sms.created_quote
    quote = sms.quote
    assert quote.known_total_cents == 4_198_000
    assert quote.upper_total_cents == 4_283_000
    assert not quote.is_fully_priced
    assert quote.quote_confidence == 61
    headline = db.scalars(
        select(QuoteField).where(
            QuoteField.quote_id == quote.id,
            QuoteField.key == "headline_price",
            QuoteField.is_current.is_(True),
        )
    ).one()
    assert headline.confidence == 98 and headline.corroborating_source_ids == [str(sms.document.id)]
    open_flags = {
        f.fingerprint: f
        for f in db.scalars(
            select(Flag).where(Flag.quote_id == quote.id, Flag.status == FlagStatus.OPEN)
        )
    }
    assert open_flags["ambiguous_charge:fuel_surcharge"].blocking
    # The PDF alone raised FET as missing; the SMS's "all in" covers it, so it auto-cleared.
    fet = db.scalars(
        select(Flag).where(
            Flag.quote_id == quote.id, Flag.fingerprint == "expected_fee_missing:fet"
        )
    ).one()
    assert fet.status is FlagStatus.RESOLVED and fet.resolution.value == "auto_cleared"  # type: ignore[union-attr]


def test_email_attachment_becomes_child_document(
    db: Session, ctx: RequestContext, trip: Trip, settings: Settings, storage: LocalStorage
) -> None:
    msg = EmailMessage()
    msg["From"] = "Northstar Jets <charter@northstarjets.example>"
    msg["To"] = "broker@example.com"
    msg["Subject"] = "Quote attached"
    msg["Date"] = "Wed, 30 Sep 2026 15:36:00 +0000"
    msg["Message-ID"] = "<abc@northstarjets.example>"
    msg.set_content("Hi, please find our quote attached.\nNorthstar Jets")
    msg.add_attachment(
        (FIXTURES / "operator_quote_18.pdf").read_bytes(),
        maintype="application",
        subtype="pdf",
        filename="operator_quote_18.pdf",
    )
    out = ingest(
        db,
        ctx,
        trip,
        pipeline.IngestCommand(data=msg.as_bytes(), filename="quote.eml"),
        settings,
        storage,
    )
    assert out.document.kind is DocumentKind.EMAIL
    child = db.scalars(
        select(SourceDocument).where(SourceDocument.parent_id == out.document.id)
    ).one()
    assert child.kind is DocumentKind.PDF and child.channel is DocumentChannel.EMAIL
    assert child.extraction_status is ExtractionStatus.SUCCEEDED
    assert out.quote is not None and child.quote_id == out.quote.id
    assert out.quote.known_total_cents == 5_240_000


def test_scanned_pdf_without_claude_needs_manual(
    db: Session, ctx: RequestContext, trip: Trip, settings: Settings, storage: LocalStorage
) -> None:
    out = ingest(db, ctx, trip, cmd("scanned_quote.pdf", 30), settings, storage)
    assert out.document.is_scanned
    assert out.document.extraction_status is ExtractionStatus.NEEDS_MANUAL
    assert out.quote is None
    flag = db.scalars(select(Flag).where(Flag.source_document_id == out.document.id)).one()
    assert flag.type is FlagType.OCR_UNAVAILABLE and flag.quote_id is None and flag.blocking


def test_scanned_pdf_for_a_known_quote_flags_the_quote(
    db: Session, ctx: RequestContext, trip: Trip, settings: Settings, storage: LocalStorage
) -> None:
    first = ingest(db, ctx, trip, cmd("operator_quote_18.pdf", 216), settings, storage)
    assert first.quote is not None
    out = ingest(
        db, ctx, trip, cmd("scanned_quote.pdf", 300, quote_id=first.quote.id), settings, storage
    )
    assert out.document.extraction_status is ExtractionStatus.NEEDS_MANUAL
    assert out.quote is not None and out.quote.id == first.quote.id
    flag = db.scalars(
        select(Flag).where(Flag.quote_id == first.quote.id, Flag.type == FlagType.OCR_UNAVAILABLE)
    ).one()
    assert flag.status is FlagStatus.OPEN
    assert first.quote.open_blocking_flags >= 1 and not first.quote.is_fully_priced


def test_extractor_failure_marks_failed_with_flag(
    db: Session, ctx: RequestContext, trip: Trip, settings: Settings, storage: LocalStorage
) -> None:
    broken = FakeExtractor(error=ExtractorUnavailable("overloaded"))
    out = ingest(db, ctx, trip, cmd("operator_quote_18.pdf", 216), settings, storage, broken)
    assert out.document.extraction_status is ExtractionStatus.FAILED
    assert "unavailable" in (out.document.extraction_error or "")
    flag = db.scalars(select(Flag).where(Flag.source_document_id == out.document.id)).one()
    assert flag.type is FlagType.EXTRACTION_FAILED


def test_claude_failure_falls_back_to_rules_and_logs(
    db: Session, ctx: RequestContext, trip: Trip, settings: Settings, storage: LocalStorage
) -> None:
    primary = FakeExtractor(error=ExtractorUnavailable("529"), name="claude")
    out = ingest(
        db,
        ctx,
        trip,
        cmd("operator_quote_18.pdf", 216),
        settings,
        storage,
        FallbackExtractor(primary, RULES),
    )
    assert out.document.extraction_status is ExtractionStatus.SUCCEEDED
    assert out.document.extractor == "rules"
    assert any("used rules" in e.message for e in events(db, trip))


def test_decline_email_declines_the_rfq(
    db: Session, ctx: RequestContext, trip: Trip, settings: Settings, storage: LocalStorage
) -> None:
    op = factories.make_operator(db, ctx.workspace, "Harbor Jet Group", email="ops@harbor.example")
    rfq = factories.make_trip_operator(db, trip, op, requested_at=T0)
    fake = FakeExtractor(result=empty_result("decline"))
    out = ingest(
        db,
        ctx,
        trip,
        pipeline.IngestCommand(
            text="Sorry, no aircraft available for JS184.",
            sender="Harbor <ops@harbor.example>",
            received_at=T0 + timedelta(minutes=240),
        ),
        settings,
        storage,
        fake,
    )
    assert out.quote is None and out.document.intent is not None
    assert rfq.status is TripOperatorStatus.DECLINED
    assert rfq.responded_at == T0 + timedelta(minutes=240)
    assert db.scalars(select(Quote)).all() == []


def test_explicit_ids_must_belong_to_the_trip(
    db: Session, ctx: RequestContext, trip: Trip, settings: Settings, storage: LocalStorage
) -> None:
    other_ws = factories.make_workspace(db, "Other")
    foreign_trip = factories.make_trip(db, other_ws, reference="JS777")
    foreign_quote = factories.make_quote(
        db, foreign_trip, factories.make_operator(db, other_ws, "Foreign")
    )
    with pytest.raises(NotFound):
        ingest(
            db,
            ctx,
            trip,
            pipeline.IngestCommand(text="x 1", quote_id=foreign_quote.id),
            settings,
            storage,
        )
    with pytest.raises(NotFound):
        ingest(db, ctx, foreign_trip, pipeline.IngestCommand(text="x 1"), settings, storage)


def test_upload_validation(
    db: Session, ctx: RequestContext, trip: Trip, settings: Settings, storage: LocalStorage
) -> None:
    with pytest.raises(Unprocessable):
        ingest(db, ctx, trip, pipeline.IngestCommand(data=b"\x00\x01binary"), settings, storage)
    with pytest.raises(Unprocessable):
        ingest(
            db, ctx, trip, pipeline.IngestCommand(data=b"%PDF-1", text="both"), settings, storage
        )
    small = settings.model_copy(update={"max_upload_mb": 1})
    with pytest.raises(PayloadTooLarge):
        ingest(db, ctx, trip, pipeline.IngestCommand(text="a" * (1024 * 1024 + 1)), small, storage)
    one_page = settings.model_copy(update={"max_pdf_pages": 1})
    with pytest.raises(Unprocessable) as exc:
        ingest(db, ctx, trip, cmd("atlas_quote_01.pdf", 1), one_page, storage)
    assert exc.value.code == "too_many_pages"
    assert db.scalars(select(SourceDocument)).all() == []


def test_background_mode_queues_then_processes(
    db: Session,
    ctx: RequestContext,
    trip: Trip,
    settings: Settings,
    storage: LocalStorage,
    session_factory: sessionmaker[Session],
) -> None:
    bg = settings.model_copy(update={"pipeline_mode": PipelineMode.BACKGROUND})
    out = ingest(db, ctx, trip, cmd("quote-final-v7.pdf", 126), bg, storage)
    assert out.queued and out.quote is None
    assert out.document.extraction_status is ExtractionStatus.PENDING
    db.commit()
    pipeline.run_in_background(
        session_factory,
        trip.workspace_id,
        out.document.id,
        settings=bg,
        storage=storage,
        extractor=RULES,
    )
    db.expire_all()
    doc = db.get(SourceDocument, out.document.id)
    assert doc is not None and doc.extraction_status is ExtractionStatus.SUCCEEDED
    quote = db.get(Quote, doc.quote_id)
    assert quote is not None and quote.known_total_cents == 4_720_000


def test_reprocess_is_idempotent_and_keeps_reviews(
    db: Session, ctx: RequestContext, trip: Trip, settings: Settings, storage: LocalStorage
) -> None:
    out = ingest(db, ctx, trip, cmd("operator_quote_18.pdf", 216), settings, storage)
    assert out.quote is not None
    before = len(db.scalars(select(QuoteField)).all())
    res = pipeline.reprocess_document(
        db, ctx, out.document, settings=settings, storage=storage, extractor=RULES
    )
    assert res.quote is not None and res.quote.id == out.quote.id
    assert len(db.scalars(select(QuoteField)).all()) == before
    assert res.quote.known_total_cents == 5_240_000
    assert db.scalars(select(AuditEvent).where(AuditEvent.action == "document.reprocess")).one()


def test_move_document_to_another_operator(
    db: Session, ctx: RequestContext, trip: Trip, settings: Settings, storage: LocalStorage
) -> None:
    wrong = factories.make_operator(db, ctx.workspace, "Wrong Operator", email="x@wrong.example")
    out = ingest(
        db, ctx, trip, cmd("operator_quote_18.pdf", 216, operator_id=wrong.id), settings, storage
    )
    assert out.quote is not None and out.quote.operator_id == wrong.id
    right = factories.make_operator(db, ctx.workspace, "Northstar Jets")
    moved = pipeline.move_document(
        db, ctx, out.document, quote_id=None, operator_id=right.id, settings=settings
    )
    new_quote = db.get(Quote, moved.quote_id)
    assert new_quote is not None and new_quote.operator_id == right.id
    assert new_quote.known_total_cents == 5_240_000
    old = db.get(Quote, out.quote.id)
    assert old is not None and old.status.value == "withdrawn"
    assert db.scalars(select(QuoteField).where(QuoteField.quote_id == old.id)).all() == []
    rfq = db.scalars(select(TripOperator).where(TripOperator.operator_id == right.id)).one()
    assert rfq.status is TripOperatorStatus.QUOTED


def test_fake_extractor_scalar_values_are_merged(
    db: Session, ctx: RequestContext, trip: Trip, settings: Settings, storage: LocalStorage
) -> None:
    fake = FakeExtractor(
        result=empty_result().model_copy(
            update={
                "fields": [
                    scalar("operator_name", "Pasted Jets", 90),
                    scalar("headline_price", {"amount_minor": 1_000_000, "currency": "USD"}),
                    scalar("seats", 8),
                ]
            }
        )
    )
    out = ingest(
        db,
        ctx,
        trip,
        pipeline.IngestCommand(text="Pasted Jets: $10,000, 8 seats"),
        settings,
        storage,
        fake,
    )
    assert out.quote is not None and out.created_quote
    assert out.quote.headline_cents == 1_000_000 and out.quote.seats == 8
    assert fake.calls and fake.calls[0][1].pax == 7
