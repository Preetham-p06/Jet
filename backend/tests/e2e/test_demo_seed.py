"""The demo seed oracle (spec §9): the real pipeline with the rules extractor must
reproduce the landing page's JS184 comparison."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
import time_machine
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Flag, Operator, Quote, Recommendation, TripOperator, User, Workspace
from app.models.enums import FlagStatus, FlagType, Role, TripOperatorStatus
from app.permissions import RequestContext
from app.services import merge, review
from app.services.storage import LocalStorage
from scripts.seed_demo import AlreadySeeded, SeedResult, seed

pytestmark = pytest.mark.e2e

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
ATLAS, SKY, NORTH, SUMMIT = (
    "Atlas Air Charter",
    "SkyBridge Aviation",
    "Northstar Jets",
    "Summit Executive Aviation",
)


@pytest.fixture
def seeded(db: Session, settings: Settings) -> Iterator[SeedResult]:
    with time_machine.travel(NOW, tick=False):
        result = seed(db, settings=settings, storage=LocalStorage(settings.storage_dir))
        db.commit()
        yield result


def quotes(db: Session) -> dict[str, Quote]:
    out: dict[str, Quote] = {}
    for q in db.scalars(select(Quote)):
        op = db.get(Operator, q.operator_id)
        assert op is not None
        out[op.name] = q
    return out


def test_demo_seed_oracle(db: Session, settings: Settings, seeded: SeedResult) -> None:
    q = quotes(db)
    assert set(q) == {ATLAS, SKY, NORTH, SUMMIT}

    # True cost.
    assert q[ATLAS].known_total_cents == 4_482_000 and q[ATLAS].is_fully_priced
    assert q[SKY].known_total_cents == 4_720_000 and q[SKY].is_fully_priced
    assert q[NORTH].known_total_cents == 5_240_000 and q[NORTH].is_fully_priced
    assert q[SUMMIT].known_total_cents == 4_198_000
    assert q[SUMMIT].upper_total_cents == 4_283_000
    assert not q[SUMMIT].is_fully_priced

    # Summit: one blocking flag, fuel at 61; info notes for all-in and de-icing.
    summit_flags = db.scalars(
        select(Flag).where(Flag.quote_id == q[SUMMIT].id, Flag.status == FlagStatus.OPEN)
    ).all()
    blocking = [f for f in summit_flags if f.blocking]
    assert [f.fingerprint for f in blocking] == ["ambiguous_charge:fuel_surcharge"]
    assert blocking[0].type is FlagType.AMBIGUOUS_CHARGE
    fuel = merge.current_field(db, q[SUMMIT].id, "fee.fuel_surcharge")
    assert fuel is not None and fuel.confidence == 61
    assert blocking[0].field_id == fuel.id
    assert {f.fingerprint for f in summit_flags if not f.blocking} == {
        "all_in_itemized_conflict",
        "conditional_charge:deicing",
    }
    assert q[SUMMIT].quote_confidence == 61
    for name in (ATLAS, SKY, NORTH):
        open_flags = db.scalars(
            select(Flag).where(Flag.quote_id == q[name].id, Flag.status == FlagStatus.OPEN)
        ).all()
        assert [f.fingerprint for f in open_flags] == ["conditional_charge:deicing"], name
        assert q[name].open_blocking_flags == 0

    # Recommendation: Atlas at ~96 with all five checks.
    assert q[ATLAS].is_recommended
    assert [n for n, x in q.items() if x.is_recommended] == [ATLAS]
    assert q[ATLAS].fit_score == 96
    assert (q[SKY].fit_score, q[NORTH].fit_score, q[SUMMIT].fit_score) == (93, 82, 77)
    rec = db.scalars(select(Recommendation).order_by(Recommendation.computed_at.desc())).first()
    assert rec is not None and rec.recommended_quote_id == q[ATLAS].id
    checks = rec.ranking["checks"]
    assert len(checks) == 5 and all(c["passed"] for c in checks)

    # Proposal eligibility.
    assert {n for n, x in q.items() if x.eligible_for_proposal} == {ATLAS, SKY, NORTH}

    # RFQ response times: 1.4, 2.1, 3.6 and 5.2 h; two declines, two still requested.
    rfqs = {
        db.get(Operator, r.operator_id).name: r  # type: ignore[union-attr]
        for r in db.scalars(select(TripOperator))
    }
    hours = {
        name: round((r.responded_at - r.requested_at).total_seconds() / 3600, 1)
        for name, r in rfqs.items()
        if r.status is TripOperatorStatus.QUOTED and r.responded_at is not None
    }
    assert hours == {ATLAS: 1.4, SKY: 2.1, NORTH: 3.6, SUMMIT: 5.2}
    statuses = sorted(r.status.value for r in rfqs.values())
    assert statuses == ["declined"] * 2 + ["quoted"] * 4 + ["requested"] * 2

    # The printed table carries the headline numbers.
    assert "$41,980+" in seeded.table and "$44,820" in seeded.table


def test_accepting_summit_fuel_keeps_atlas_recommended(db: Session, seeded: SeedResult) -> None:
    ws = db.get(Workspace, seeded.workspace_id)
    broker = db.scalars(select(User).where(User.email == "broker@jetstream.example")).one()
    assert ws is not None
    ctx = RequestContext(user=broker, workspace=ws, role=Role.BROKER, request_id="oracle")
    q = quotes(db)
    fuel = merge.current_field(db, q[SUMMIT].id, "fee.fuel_surcharge")
    assert fuel is not None
    with time_machine.travel(NOW, tick=False):
        review.accept_field(db, ctx, fuel, version=fuel.version, note="estimate accepted")
    assert q[SUMMIT].known_total_cents == 4_283_000 and q[SUMMIT].is_fully_priced
    assert q[SUMMIT].open_blocking_flags == 0
    assert q[SUMMIT].fit_score == 82
    assert q[ATLAS].is_recommended and q[ATLAS].fit_score == 96
    # Summit still lacks Wi-Fi, so the proposal set is unchanged apart from review gates.
    assert not q[SUMMIT].is_recommended


def test_seeding_twice_is_refused(db: Session, settings: Settings, seeded: SeedResult) -> None:
    with pytest.raises(AlreadySeeded):
        seed(db, settings=settings, storage=LocalStorage(settings.storage_dir))
