"""Trip list rows carry what the trips table needs without a per-trip fetch."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Workspace
from app.models.enums import FlagSeverity, Role
from tests import factories
from tests.conftest import ClientFactory


def test_trip_summary_reports_pricing_and_blocking_flags(
    client_as: ClientFactory, db: Session, workspace: Workspace
) -> None:
    trip = factories.make_trip(db, workspace, reference="JS900")
    op = factories.make_operator(db, workspace, "Summit Executive Aviation")
    quote = factories.make_quote(
        db,
        trip,
        op,
        known_total_cents=4_198_000,
        upper_total_cents=4_283_000,
        is_fully_priced=False,
        is_recommended=True,
    )
    factories.make_flag(db, quote)  # warning, blocking
    factories.make_flag(db, quote, severity=FlagSeverity.INFO, blocking=False)
    empty = factories.make_trip(db, workspace, reference="JS901")
    db.commit()

    broker = client_as(Role.BROKER)
    rows = {t["reference"]: t for t in broker.get("/api/v1/trips").json()["items"]}

    row = rows["JS900"]
    assert row["recommended_total_cents"] == 4_198_000
    # Regression: the list had no pricing state, so "$41,980" lost its "+".
    assert row["is_fully_priced"] is False
    assert row["open_flag_count"] == 2
    assert row["open_blocking_flag_count"] == 1

    assert rows["JS901"]["is_fully_priced"] is None
    assert rows["JS901"]["open_blocking_flag_count"] == 0

    detail = broker.get(f"/api/v1/trips/{trip.id}").json()
    assert detail["is_fully_priced"] is False
    assert detail["open_blocking_flag_count"] == 1
    assert broker.get(f"/api/v1/trips/{empty.id}").json()["is_fully_priced"] is None
