"""Seed the demo workspace and trip JS184 through the real pipeline (design spec §9).

    uv run python scripts/seed_demo.py --reset
    uv run python scripts/seed_demo.py --reset --db sqlite:////tmp/demo.db --password s3cret

Creates workspace "JetStream Demo Brokerage" with an admin, a broker and an
assistant, trip JS184 (KTEB 2026-10-18 09:00 -> KOPF, 7 pax, Wi-Fi required),
the eight operators and RFQ rows of the landing page, then feeds every file in
`fixtures/demo/manifest.json` through `pipeline.ingest` with the rules
extractor. Offsets are relative to T0 = now - 1 day (the RFQ time). Prints the
comparison table and the logins.

Migrations run first (`alembic upgrade head`). `--reset` drops every table of
the target database before migrating, so only use it on a demo database.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from email.utils import parseaddr
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import inspect, select, text  # noqa: E402
from sqlalchemy.engine import Engine  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.config import ExtractorChoice, PipelineMode, Settings, get_settings  # noqa: E402
from app.db import make_engine, make_session_factory, set_workspace  # noqa: E402
from app.extraction.rules.extractor import RulesExtractor  # noqa: E402
from app.models import (  # noqa: E402
    Base,
    Operator,
    Quote,
    Trip,
    TripLeg,
    TripOperator,
    User,
    Workspace,
)
from app.models.enums import (  # noqa: E402
    DocumentChannel,
    OperatorSource,
    RequestChannel,
    Role,
    TripOperatorStatus,
    TripStatus,
    TripType,
)
from app.permissions import RequestContext  # noqa: E402
from app.security.passwords import hash_password  # noqa: E402
from app.services import pipeline  # noqa: E402
from app.services.money import format_usd  # noqa: E402
from app.services.operators import email_domain, normalize_operator_name  # noqa: E402
from app.services.storage import LocalStorage, Storage  # noqa: E402

FIXTURES = ROOT / "fixtures" / "demo"
WORKSPACE_NAME = "JetStream Demo Brokerage"
WORKSPACE_SLUG = "jetstream-demo"
DEFAULT_PASSWORD = "jetstream-demo-184"  # noqa: S105 - demo login, printed at the end
USERS: tuple[tuple[str, Role, str], ...] = (
    ("demo@jetstream.example", Role.ADMIN, "Demo Admin"),
    ("broker@jetstream.example", Role.BROKER, "Demo Broker"),
    ("assistant@jetstream.example", Role.ASSISTANT, "Demo Assistant"),
)


class AlreadySeeded(RuntimeError):
    """The demo workspace exists and `--reset` was not given."""


@dataclass
class SeedResult:
    workspace_id: Any
    trip_id: Any
    t0: datetime
    password: str
    users: list[tuple[str, str]] = field(default_factory=list)
    table: str = ""


# --------------------------------------------------------------------------- database


def migrate(url: str, *, reset: bool) -> None:
    """Drop everything (with `reset`) and bring the schema to head with Alembic."""
    from alembic.config import Config

    from alembic import command

    engine = make_engine(url)
    try:
        if reset:
            _drop_all(engine)
    finally:
        engine.dispose()
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    command.upgrade(cfg, "head")


def _drop_all(engine: Engine) -> None:
    Base.metadata.drop_all(engine)
    with engine.begin() as conn:
        if inspect(conn).has_table("alembic_version"):
            conn.execute(text("DROP TABLE alembic_version"))


# --------------------------------------------------------------------------- seeding


def _sender_email(sender: str | None) -> str | None:
    address = parseaddr(sender or "")[1]
    return address.lower() if "@" in address else None


def _manifest() -> dict[str, Any]:
    data: dict[str, Any] = json.loads((FIXTURES / "manifest.json").read_text())
    return data


def seed(
    db: Session,
    *,
    settings: Settings,
    storage: Storage,
    password: str = DEFAULT_PASSWORD,
    now: datetime | None = None,
) -> SeedResult:
    """Create the demo workspace and run every manifest file through the pipeline.

    The caller commits. Raises `AlreadySeeded` when the workspace exists.
    """
    now = now or datetime.now(UTC)
    t0 = (now - timedelta(days=1)).replace(microsecond=0)
    manifest = _manifest()
    if db.scalars(select(Workspace).where(Workspace.slug == WORKSPACE_SLUG)).first():
        raise AlreadySeeded("The demo workspace already exists; pass --reset to recreate it")

    ws = Workspace(name=WORKSPACE_NAME, slug=WORKSPACE_SLUG, review_threshold=75)
    db.add(ws)
    db.flush()
    set_workspace(db, ws.id)

    password_hash = hash_password(password)
    users: dict[Role, User] = {}
    for email, role, name in USERS:
        user = User(
            workspace_id=ws.id,
            email=email,
            full_name=name,
            password_hash=password_hash,
            role=role,
        )
        db.add(user)
        users[role] = user
    db.flush()
    admin = users[Role.ADMIN]
    ctx = RequestContext(user=admin, workspace=ws, role=Role.ADMIN, request_id="seed-demo")

    spec = manifest["trip"]
    trip = Trip(
        workspace_id=ws.id,
        reference=spec["reference"],
        status=TripStatus.SOURCING,
        trip_type=TripType.ONE_WAY,
        pax=spec["pax"],
        client_name="Private client",
        preferences={"wifi_required": True},
        created_by_id=admin.id,
        created_at=t0 - timedelta(hours=2),
    )
    trip.legs = [
        TripLeg(
            workspace_id=ws.id,
            seq=1,
            origin_icao=spec["origin"],
            destination_icao=spec["destination"],
            depart_local=datetime.fromisoformat(spec["depart_local"]),
            depart_tz=spec["depart_tz"],
        )
    ]
    db.add(trip)
    db.flush()

    senders = {f["operator"]: f.get("sender") for f in manifest["files"]}
    for row in manifest["rfq"]:
        name = row["operator"]
        email = _sender_email(senders.get(name))
        op = Operator(
            workspace_id=ws.id,
            name=name,
            normalized_name=normalize_operator_name(name),
            aliases=[],
            email=email,
            email_domain=email_domain(email),
            source=OperatorSource.MANUAL,
        )
        db.add(op)
        db.flush()
        status = TripOperatorStatus(row["status"])
        responded = row.get("responded_offset_minutes")
        db.add(
            TripOperator(
                workspace_id=ws.id,
                trip_id=trip.id,
                operator_id=op.id,
                # Quoting operators move to "quoted" when their first document arrives.
                status=TripOperatorStatus.REQUESTED
                if status is TripOperatorStatus.QUOTED
                else status,
                channel=RequestChannel.EMAIL,
                requested_at=t0,
                responded_at=t0 + timedelta(minutes=responded) if responded is not None else None,
                declined_reason="No aircraft available"
                if status is TripOperatorStatus.DECLINED
                else None,
                created_by_id=admin.id,
            )
        )
    db.flush()

    extractor = RulesExtractor()
    for entry in manifest["files"]:
        path = FIXTURES / entry["file"]
        received = t0 + timedelta(minutes=entry["received_offset_minutes"])
        cmd = pipeline.IngestCommand(
            data=path.read_bytes(),
            filename=entry["file"],
            channel=DocumentChannel(entry["channel"]),
            sender=entry.get("sender"),
            subject=entry.get("subject"),
            received_at=received,
        )
        pipeline.ingest(db, ctx, trip, cmd, settings=settings, storage=storage, extractor=extractor)
    db.flush()

    return SeedResult(
        workspace_id=ws.id,
        trip_id=trip.id,
        t0=t0,
        password=password,
        users=[(email, role.value) for email, role, _ in USERS],
        table=comparison_table(db, trip),
    )


# --------------------------------------------------------------------------- output


def comparison_table(db: Session, trip: Trip) -> str:
    quotes = db.scalars(select(Quote).where(Quote.trip_id == trip.id)).all()
    rows = []
    for q in quotes:
        op = db.get(Operator, q.operator_id)
        rfq = db.get(TripOperator, q.trip_operator_id) if q.trip_operator_id else None
        hours = (
            (rfq.responded_at - rfq.requested_at).total_seconds() / 3600
            if rfq is not None and rfq.responded_at is not None
            else None
        )
        known = format_usd(q.known_total_cents) if q.known_total_cents is not None else "-"
        rows.append(
            (
                q.fit_score if q.fit_score is not None else -1,
                [
                    op.name if op else "?",
                    known + ("" if q.is_fully_priced else "+"),
                    format_usd(q.upper_total_cents) if q.upper_total_cents is not None else "-",
                    str(q.quote_confidence if q.quote_confidence is not None else "-"),
                    str(q.open_blocking_flags),
                    str(q.fit_score if q.fit_score is not None else "-"),
                    "yes" if q.eligible_for_proposal else "no",
                    "*" if q.is_recommended else "",
                    f"{hours:.1f} h" if hours is not None else "-",
                ],
            )
        )
    rows.sort(key=lambda r: -r[0])
    header = [
        "Operator",
        "True cost",
        "Upper",
        "Conf",
        "Blocking",
        "Fit",
        "Proposal",
        "Rec",
        "Response",
    ]
    table = [header, *(r[1] for r in rows)]
    widths = [max(len(row[i]) for row in table) for i in range(len(header))]
    lines = ["  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)) for row in table]
    lines.insert(1, "  ".join("-" * w for w in widths))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--reset", action="store_true", help="drop all tables first")
    parser.add_argument("--db", help="database URL (default: DATABASE_URL)")
    parser.add_argument("--password", help=f"password for all users (default {DEFAULT_PASSWORD})")
    args = parser.parse_args(argv)

    base = get_settings()
    updates: dict[str, Any] = {
        "extractor": ExtractorChoice.RULES,
        "pipeline_mode": PipelineMode.INLINE,
    }
    if args.db:
        updates["database_url"] = args.db
    settings = base.model_copy(update=updates)

    migrate(settings.database_url, reset=args.reset)
    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)
    try:
        with factory() as db:
            try:
                result = seed(
                    db,
                    settings=settings,
                    storage=LocalStorage(settings.storage_dir),
                    password=args.password or DEFAULT_PASSWORD,
                )
            except AlreadySeeded as exc:
                print(str(exc), file=sys.stderr)
                return 1
            db.commit()
    finally:
        engine.dispose()

    print(f"Seeded {WORKSPACE_NAME}: trip JS184, RFQ sent {result.t0:%Y-%m-%d %H:%M} UTC\n")
    print(result.table)
    print("\nLogins (password for all: " + result.password + ")")
    for email, role in result.users:
        print(f"  {role:<9} {email}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
