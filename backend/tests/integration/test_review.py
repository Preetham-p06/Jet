"""Review actions on fields and flags, and the review queue (spec §4, §8)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.errors import Conflict, Unprocessable
from app.extraction.rules.extractor import RulesExtractor
from app.models import AuditEvent, Flag, Quote, QuoteField, Trip
from app.models.enums import (
    DocumentChannel,
    ExtractorKind,
    FeeCategory,
    FieldStatus,
    FlagResolution,
    FlagStatus,
    FlagType,
    Role,
)
from app.permissions import RequestContext
from app.services import merge, pipeline, recompute, review
from app.services.storage import LocalStorage
from tests import factories
from tests.factories_p5 import make_ctx
from tests.fakes import FakeExtractor, empty_result, fee, scalar

pytestmark = pytest.mark.integration

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "demo"
T0 = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)


class Env:
    def __init__(self, db: Session, settings: Settings) -> None:
        ws = factories.make_workspace(db, "Review Brokerage")
        self.db = db
        self.settings = settings
        self.storage = LocalStorage(settings.storage_dir)
        self.ctx: RequestContext = make_ctx(db, ws, Role.BROKER)
        self.trip: Trip = factories.make_trip(db, ws, reference="JS184")

    def ingest(self, name: str, minutes: int, **kw: object) -> Quote:
        out = pipeline.ingest(
            self.db,
            self.ctx,
            self.trip,
            pipeline.IngestCommand(
                data=(FIXTURES / name).read_bytes(),
                filename=name,
                received_at=T0 + timedelta(minutes=minutes),
                **kw,  # type: ignore[arg-type]
            ),
            settings=self.settings,
            storage=self.storage,
            extractor=RulesExtractor(),
        )
        assert out.quote is not None
        return out.quote

    def summit(self, *, sms: bool = True) -> Quote:
        quote = self.ingest(
            "revised-quote.pdf", 312, sender="Summit Executive Aviation <dan@summit-exec.example>"
        )
        if sms:
            quote = self.ingest(
                "summit_sms.txt",
                340,
                channel=DocumentChannel.SMS,
                sender="Summit Executive Aviation <+16175550142>",
            )
        return quote

    def field(self, quote: Quote, key: str) -> QuoteField:
        row = merge.current_field(self.db, quote.id, key)
        assert row is not None
        return row

    def flag(self, quote: Quote, fingerprint: str) -> Flag:
        return self.db.scalars(
            select(Flag).where(Flag.quote_id == quote.id, Flag.fingerprint == fingerprint)
        ).one()

    def actions(self) -> list[str]:
        return [
            a.action for a in self.db.scalars(select(AuditEvent).order_by(AuditEvent.created_at))
        ]


@pytest.fixture
def env(db: Session, settings: Settings) -> Env:
    return Env(db, settings)


# --------------------------------------------------------------------------- fields


def test_verify_checks_version_and_locks(env: Env) -> None:
    quote = env.summit()
    seats = env.field(quote, "seats")
    with pytest.raises(Conflict) as exc:
        review.verify_field(env.db, env.ctx, seats, version=seats.version + 1)
    assert exc.value.code == "stale_version"
    old_version = seats.version
    review.verify_field(env.db, env.ctx, seats, version=old_version)
    assert seats.status is FieldStatus.VERIFIED and seats.locked
    assert seats.reviewed_by_id == env.ctx.user_id and seats.version == old_version + 1
    assert "field.verify" in env.actions()


def test_accept_fuel_estimate_prices_summit(env: Env) -> None:
    quote = env.summit()
    assert not quote.is_fully_priced
    fuel = env.field(quote, "fee.fuel_surcharge")
    review.accept_field(env.db, env.ctx, fuel, version=fuel.version, note="ok per Dan")
    assert fuel.status is FieldStatus.ACCEPTED and fuel.review_note == "ok per Dan"
    assert quote.known_total_cents == 4_283_000 and quote.upper_total_cents == 4_283_000
    flag = env.flag(quote, "ambiguous_charge:fuel_surcharge")
    assert flag.status is FlagStatus.RESOLVED and flag.resolution is FlagResolution.AUTO_CLEARED
    assert quote.open_blocking_flags == 0 and quote.is_fully_priced
    assert quote.quote_confidence == 75  # accepted counts as max(conf, threshold)


def test_edit_validates_and_reset_restores(env: Env) -> None:
    quote = env.summit()
    seats = env.field(quote, "seats")
    with pytest.raises(Unprocessable):
        review.edit_field(env.db, env.ctx, seats, version=seats.version, value="many", note=None)
    review.edit_field(env.db, env.ctx, seats, version=seats.version, value=12, note="config")
    assert seats.current_value == 12 and seats.original_value == 13
    assert seats.status is FieldStatus.EDITED and quote.seats == 12
    review.reset_field(env.db, env.ctx, seats, version=seats.version)
    assert seats.current_value == 13 and seats.status is FieldStatus.EXTRACTED
    assert not seats.locked and seats.reviewed_by_id is None and quote.seats == 13

    fuel = env.field(quote, "fee.fuel_surcharge")
    with pytest.raises(Unprocessable):
        review.edit_field(
            env.db,
            env.ctx,
            fuel,
            version=fuel.version,
            value={"category": "catering", "status": "stated"},
            note=None,
        )
    review.edit_field(
        env.db,
        env.ctx,
        fuel,
        version=fuel.version,
        value={"status": "stated", "amount": {"amount_minor": 90000, "currency": "USD"}},
        note=None,
    )
    assert fuel.current_value["category"] == "fuel_surcharge"
    assert quote.known_total_cents == 4_288_000 and quote.is_fully_priced


def test_non_current_fields_cannot_be_reviewed(env: Env) -> None:
    quote = env.summit()
    seats = env.field(quote, "seats")
    new = review.add_manual_field(
        env.db, env.ctx, quote, key="seats", value=12, label=None, note=None
    )
    assert not seats.is_current and seats.superseded_by_id == new.id
    with pytest.raises(Conflict):
        review.verify_field(env.db, env.ctx, seats, version=seats.version)


def test_add_manual_field_and_history(env: Env) -> None:
    quote = env.summit()
    new = review.add_manual_field(
        env.db,
        env.ctx,
        quote,
        key="fee.fuel_surcharge",
        value={"status": "stated", "amount": {"amount_minor": 80000, "currency": "USD"}},
        label="Fuel (confirmed by phone)",
        note="Dan confirmed",
    )
    assert new.extractor is ExtractorKind.MANUAL and new.status is FieldStatus.EDITED
    assert new.locked and new.confidence == 100 and new.label == "Fuel (confirmed by phone)"
    history = review.field_history(env.db, new)
    assert [h.id for h in history][0] == new.id and len(history) == 2
    assert quote.known_total_cents == 4_278_000 and quote.is_fully_priced
    with pytest.raises(Unprocessable):
        review.add_manual_field(
            env.db, env.ctx, quote, key="nonsense", value=1, label=None, note=None
        )
    assert "field.add" in env.actions()


# --------------------------------------------------------------------------- flags


def test_invalid_resolutions_are_rejected(env: Env) -> None:
    quote = env.summit()
    flag = env.flag(quote, "ambiguous_charge:fuel_surcharge")
    with pytest.raises(Unprocessable) as exc:
        review.resolve_flag(
            env.db,
            env.ctx,
            flag,
            resolution=FlagResolution.USE_NEW_VALUE,
            amount_cents=None,
            note=None,
        )
    assert exc.value.code == "invalid_resolution"
    with pytest.raises(Unprocessable) as exc:
        review.resolve_flag(
            env.db,
            env.ctx,
            flag,
            resolution=FlagResolution.CONFIRMED_AMOUNT,
            amount_cents=None,
            note=None,
        )
    assert exc.value.code == "amount_required"


@pytest.mark.parametrize(
    ("resolution", "amount", "known", "status"),
    [
        (FlagResolution.ACCEPTED_ESTIMATE, None, 4_283_000, "estimated"),
        (FlagResolution.CONFIRMED_AMOUNT, 92_000, 4_290_000, "stated"),
        (FlagResolution.CONFIRMED_INCLUDED, None, 4_198_000, "included"),
        (FlagResolution.NOT_APPLICABLE, None, 4_198_000, "not_applicable"),
    ],
)
def test_fee_resolutions_write_the_field(
    env: Env, resolution: FlagResolution, amount: int | None, known: int, status: str
) -> None:
    quote = env.summit()
    flag = env.flag(quote, "ambiguous_charge:fuel_surcharge")
    review.resolve_flag(
        env.db, env.ctx, flag, resolution=resolution, amount_cents=amount, note="checked"
    )
    assert flag.status is FlagStatus.RESOLVED and flag.resolution is resolution
    assert flag.resolved_by_id == env.ctx.user_id and flag.resolution_note == "checked"
    fuel = env.field(quote, "fee.fuel_surcharge")
    assert fuel.locked and fuel.current_value["status"] == status
    assert quote.known_total_cents == known and quote.is_fully_priced
    assert quote.open_blocking_flags == 0
    assert "flag.resolve" in env.actions()


def test_dismiss_keeps_the_estimate_unpriced(env: Env) -> None:
    quote = env.summit()
    flag = env.flag(quote, "ambiguous_charge:fuel_surcharge")
    with pytest.raises(Unprocessable) as exc:
        review.resolve_flag(
            env.db, env.ctx, flag, resolution=FlagResolution.DISMISSED, amount_cents=None, note=""
        )
    assert exc.value.code == "note_required"
    review.resolve_flag(
        env.db, env.ctx, flag, resolution=FlagResolution.DISMISSED, amount_cents=None, note="n/a"
    )
    assert flag.status is FlagStatus.DISMISSED
    assert quote.open_blocking_flags == 0
    assert not quote.is_fully_priced  # the estimate still is not accepted
    review.reopen_flag(env.db, env.ctx, flag)
    assert flag.status is FlagStatus.OPEN and flag.resolution is None
    assert quote.open_blocking_flags == 1
    with pytest.raises(Conflict):
        review.reopen_flag(env.db, env.ctx, flag)
    assert "flag.reopen" in env.actions()


def test_expected_fee_confirmed_amount_creates_a_manual_field(env: Env) -> None:
    quote = env.summit(sms=False)  # the PDF alone does not mention FET
    flag = env.flag(quote, "expected_fee_missing:fet")
    assert flag.blocking and flag.status is FlagStatus.OPEN
    review.resolve_flag(
        env.db,
        env.ctx,
        flag,
        resolution=FlagResolution.CONFIRMED_AMOUNT,
        amount_cents=300_000,
        note=None,
    )
    fet = env.field(quote, "fee.fet")
    assert fet.extractor is ExtractorKind.MANUAL and fet.current_value["status"] == "stated"
    assert fet.current_value["amount"] == {"amount_minor": 300_000, "currency": "USD"}
    assert quote.known_total_cents == 3_890_000 + 190_000 + 48_000 + 300_000


def test_conditional_charge_is_acknowledged(env: Env) -> None:
    quote = env.summit()
    flag = env.flag(quote, "conditional_charge:deicing")
    assert FlagResolution.DISMISSED in review.flag_out(flag).allowed_resolutions
    review.resolve_flag(
        env.db, env.ctx, flag, resolution=FlagResolution.ACKNOWLEDGED, amount_cents=None, note=None
    )
    assert flag.status is FlagStatus.RESOLVED
    recompute.recompute_trip(env.db, env.trip)
    assert flag.status is FlagStatus.RESOLVED  # same data, stays resolved


def _conflict(env: Env) -> tuple[Quote, Flag]:
    quote = env.ingest("operator_quote_18.pdf", 216)
    later = factories.make_document(env.db, env.trip, received_at=T0 + timedelta(minutes=400))
    result = empty_result().model_copy(
        update={"fees": [fee(FeeCategory.POSITIONING, "estimated", 1_000, confidence=70)]}
    )
    merge.merge_result(env.db, quote, later, result, review_threshold=75, now=T0)
    recompute.recompute_trip(env.db, env.trip)
    return quote, env.flag(quote, "conflicting_values:fee.positioning")


def test_conflict_use_new_value(env: Env) -> None:
    quote, flag = _conflict(env)
    assert flag.blocking and quote.open_blocking_flags == 1
    review.resolve_flag(
        env.db, env.ctx, flag, resolution=FlagResolution.USE_NEW_VALUE, amount_cents=None, note=None
    )
    pos = env.field(quote, "fee.positioning")
    assert pos.current_value["status"] == "estimated" and pos.status is FieldStatus.ACCEPTED
    assert merge.open_candidates(env.db, quote.id, "fee.positioning") == []
    line = next(ln for ln in quote.fee_lines if ln.category is FeeCategory.POSITIONING)
    assert line.amount_cents == 100_000 and line.counts_in_known
    # The stated total ($52,400) is now above the itemized sum: flagged, stated kept.
    assert env.flag(quote, "total_mismatch").status is FlagStatus.OPEN
    assert quote.known_total_cents == 5_240_000


def test_conflict_keep_current(env: Env) -> None:
    quote, flag = _conflict(env)
    review.resolve_flag(
        env.db, env.ctx, flag, resolution=FlagResolution.KEEP_CURRENT, amount_cents=None, note=None
    )
    pos = env.field(quote, "fee.positioning")
    assert pos.current_value["status"] == "stated"
    assert merge.open_candidates(env.db, quote.id, "fee.positioning") == []
    assert flag.status is FlagStatus.RESOLVED and quote.open_blocking_flags == 0
    assert quote.known_total_cents == 5_240_000


# --------------------------------------------------------------------------- queue


def test_review_queue_lists_fields_and_blocking_flags_by_money(env: Env) -> None:
    env.ingest("atlas_quote_01.pdf", 84)
    summit = env.summit(sms=False)
    summit = env.ingest(
        "summit_sms.txt",
        340,
        channel=DocumentChannel.SMS,
        sender="Summit Executive Aviation <+16175550142>",
    )
    items = review.review_queue(env.db, env.ctx, env.trip)
    fuel = [i for i in items if i.field is not None and i.field.key == "fee.fuel_surcharge"]
    assert len(fuel) == 1
    item = fuel[0]
    assert item.quote_id == summit.id and item.operator_name == "Summit Executive Aviation"
    assert item.field is not None and item.field.confidence == 61
    assert item.flag is not None and item.flag.type is FlagType.AMBIGUOUS_CHARGE
    assert FlagResolution.ACCEPTED_ESTIMATE in item.flag.allowed_resolutions
    assert item.money_impact_cents == 85_000
    assert item.source is not None and item.source.original_filename == "summit_sms.txt"
    impacts = [i.money_impact_cents for i in items]
    assert impacts == sorted(impacts, reverse=True)
    assert all(i.field is None or not i.field.locked for i in items)

    fuel_field = env.field(summit, "fee.fuel_surcharge")
    review.accept_field(env.db, env.ctx, fuel_field, version=fuel_field.version, note=None)
    after = review.review_queue(env.db, env.ctx, env.trip)
    assert not [i for i in after if i.field is not None and i.field.key == "fee.fuel_surcharge"]


def test_hourly_estimate_confirmed_amount_writes_the_headline(env: Env) -> None:
    fake = FakeExtractor(
        result=empty_result().model_copy(
            update={
                "fields": [
                    scalar("operator_name", "Hourly Jets", 90),
                    scalar("hourly_rate", {"amount_minor": 500_000, "currency": "USD"}),
                    scalar("daily_minimum_hours", 2.0),
                    scalar("flight_time_minutes", 180),
                ],
                "fees": [
                    fee(FeeCategory.FET, "included", confidence=95),
                    fee(FeeCategory.SEGMENT_FEES, "included", confidence=95),
                ],
            }
        )
    )
    out = pipeline.ingest(
        env.db,
        env.ctx,
        env.trip,
        pipeline.IngestCommand(text="Hourly Jets: $5,000/hr, 2 hr daily minimum, 3h flight"),
        settings=env.settings,
        storage=env.storage,
        extractor=fake,
    )
    quote = out.quote
    assert quote is not None
    assert quote.headline_cents == 1_500_000 and not quote.is_fully_priced
    flag = env.flag(quote, "hourly_estimate")
    assert flag.type is FlagType.HOURLY_ESTIMATE and flag.status is FlagStatus.OPEN
    review.resolve_flag(
        env.db,
        env.ctx,
        flag,
        resolution=FlagResolution.CONFIRMED_AMOUNT,
        amount_cents=1_620_000,
        note="operator confirmed",
    )
    headline = env.field(quote, "headline_price")
    assert headline.extractor is ExtractorKind.MANUAL
    assert headline.current_value == {"amount_minor": 1_620_000, "currency": "USD"}
    assert quote.headline_cents == 1_620_000
    assert quote.known_total_cents == 1_620_000
    assert flag.status is FlagStatus.RESOLVED
