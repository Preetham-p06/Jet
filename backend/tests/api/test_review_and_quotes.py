"""Review, flags, quote edits, document moves and the proposal lifecycle, on
quotes produced by the real pipeline (rules extractor, demo fixtures)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import time_machine
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import Settings
from app.extraction.registry import select_extractor
from app.models.enums import Role
from tests import factories
from tests.conftest import ClientFactory

V = "/api/v1"
# Atlas's quote is valid until 2026-10-10; later, `quote_expired` drops it.
NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
DEMO = Path(__file__).resolve().parents[2] / "fixtures" / "demo"
FILES = [
    ("atlas_quote_01.pdf", "Atlas Air Charter", "pdf_upload", 84),
    ("revised-quote.pdf", "Summit Executive Aviation", "pdf_upload", 312),
    ("summit_sms.txt", "Summit Executive Aviation", "sms", 340),
]


@pytest.fixture(autouse=True)
def frozen_time() -> Iterator[None]:
    with time_machine.travel(NOW, tick=True):
        yield


@pytest.fixture
def demo(
    frozen_time: None, app: FastAPI, settings: Settings, client_as: ClientFactory, db: Session
) -> Iterator[dict[str, Any]]:
    app.state.extractor = select_extractor(settings)
    broker = client_as(Role.BROKER)
    ws = broker.user.workspace  # type: ignore[attr-defined]
    trip = factories.make_trip(db, ws, reference="JS184")
    db.commit()
    t0 = datetime.now(UTC).replace(microsecond=0) - timedelta(days=1)
    ops = broker.post(
        f"{V}/trips/{trip.id}/operators",
        json={
            "new_operators": [{"name": "Atlas Air Charter"}, {"name": "Summit Executive Aviation"}],
            "requested_at": t0.isoformat(),
        },
    ).json()["items"]
    op_ids = {r["operator_name"]: r["operator_id"] for r in ops}
    docs: dict[str, str] = {}
    quotes: dict[str, str] = {}
    for name, operator, channel, offset in FILES:
        res = broker.post(
            f"{V}/trips/{trip.id}/quotes/ingest",
            data={
                "channel": channel,
                "operator_id": op_ids[operator],
                "received_at": (t0 + timedelta(minutes=offset)).isoformat(),
            },
            files={"file": (name, (DEMO / name).read_bytes())},
        )
        assert res.status_code == 201, res.text
        docs[name] = res.json()["source_document"]["id"]
        quotes[operator] = res.json()["quote"]["id"]
    yield {
        "broker": broker,
        "trip_id": str(trip.id),
        "docs": docs,
        "atlas": quotes["Atlas Air Charter"],
        "summit": quotes["Summit Executive Aviation"],
        "operators": op_ids,
        "assistant": client_as(Role.ASSISTANT),
    }


def _field(client: TestClient, quote_id: str, key: str) -> dict[str, Any]:
    detail = client.get(f"{V}/quotes/{quote_id}").json()
    return next(f for f in detail["fields"] if f["key"] == key)


def test_edit_reset_and_stale_versions(demo: dict[str, Any]) -> None:
    broker: TestClient = demo["broker"]
    seats = _field(broker, demo["atlas"], "seats")
    edited = broker.patch(
        f"{V}/fields/{seats['id']}", json={"version": seats["version"], "value": 9, "note": "call"}
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["current_value"] == 9
    assert edited.json()["status"] == "edited" and edited.json()["locked"] is True
    assert edited.json()["review_note"] == "call"

    stale = broker.patch(
        f"{V}/fields/{seats['id']}", json={"version": seats["version"], "value": 7}
    )
    assert stale.status_code == 409 and stale.json()["code"] == "stale_version"

    bad = broker.patch(
        f"{V}/fields/{seats['id']}", json={"version": edited.json()["version"], "value": "lots"}
    )
    assert bad.status_code == 422

    reset = broker.post(
        f"{V}/fields/{seats['id']}/reset", json={"version": edited.json()["version"]}
    )
    assert reset.status_code == 200
    assert reset.json()["current_value"] == reset.json()["original_value"] == 8
    assert reset.json()["status"] == "extracted" and reset.json()["locked"] is False

    # Assistants read but never review.
    assistant: TestClient = demo["assistant"]
    assert assistant.get(f"{V}/fields/{seats['id']}/history").status_code == 200
    denied = assistant.post(
        f"{V}/fields/{seats['id']}/verify", json={"version": reset.json()["version"]}
    )
    assert denied.status_code == 403


def test_resolve_and_reopen_the_fuel_flag(demo: dict[str, Any]) -> None:
    broker: TestClient = demo["broker"]
    flags = broker.get(
        f"{V}/trips/{demo['trip_id']}/flags", params={"quote_id": demo["summit"], "status": "open"}
    ).json()["items"]
    fuel = next(f for f in flags if f["type"] == "ambiguous_charge")
    assert fuel["blocking"] is True
    assert "confirmed_amount" in fuel["allowed_resolutions"]

    missing = broker.post(
        f"{V}/flags/{fuel['id']}/resolve", json={"resolution": "confirmed_amount"}
    )
    assert missing.status_code == 422
    resolved = broker.post(
        f"{V}/flags/{fuel['id']}/resolve",
        json={"resolution": "confirmed_amount", "amount_cents": 85_000, "note": "Dan on phone"},
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["status"] == "resolved"
    assert resolved.json()["resolution"] == "confirmed_amount"

    summit = broker.get(f"{V}/quotes/{demo['summit']}").json()
    assert summit["open_blocking_flags"] == 0
    assert summit["known_total_cents"] == 4_198_000 + 85_000
    assert summit["is_fully_priced"] is True

    again = broker.post(f"{V}/flags/{fuel['id']}/resolve", json={"resolution": "not_applicable"})
    assert again.status_code in {409, 422}

    # Reopening re-evaluates: the confirmed amount still settles the fuel question.
    assert broker.post(f"{V}/flags/{fuel['id']}/reopen").status_code == 200
    assert demo["assistant"].post(f"{V}/flags/{fuel['id']}/reopen").status_code == 403

    # An info note whose condition still holds: acknowledge, then reopen.
    info = next(f for f in flags if f["type"] == "all_in_itemized_conflict")
    wrong = broker.post(f"{V}/flags/{info['id']}/resolve", json={"resolution": "not_applicable"})
    assert wrong.status_code == 422
    assert wrong.json()["code"] == "invalid_resolution"
    acked = broker.post(f"{V}/flags/{info['id']}/resolve", json={"resolution": "acknowledged"})
    assert acked.status_code == 200, acked.text
    assert acked.json()["status"] != "open"
    reopened = broker.post(f"{V}/flags/{info['id']}/reopen")
    assert reopened.status_code == 200
    assert reopened.json()["status"] == "open"


def test_manual_fields_and_history(demo: dict[str, Any]) -> None:
    broker: TestClient = demo["broker"]
    added = broker.post(
        f"{V}/quotes/{demo['atlas']}/fields",
        json={
            "key": "fee.catering",
            "value": {"category": "catering", "label": "Catering", "status": "included"},
            "note": "Confirmed by email",
        },
    )
    assert added.status_code == 201, added.text
    assert added.json()["extractor"] == "manual"
    assert added.json()["locked"] is True
    unknown = broker.post(
        f"{V}/quotes/{demo['atlas']}/fields", json={"key": "fee.bogus", "value": 1}
    )
    assert unknown.status_code == 422

    seats = _field(broker, demo["atlas"], "seats")
    replaced = broker.post(f"{V}/quotes/{demo['atlas']}/fields", json={"key": "seats", "value": 9})
    assert replaced.status_code == 201
    history = broker.get(f"{V}/fields/{replaced.json()['id']}/history").json()
    assert history["total"] >= 2
    assert seats["id"] in {f["id"] for f in history["items"]}
    assert history["items"][0]["id"] == replaced.json()["id"]  # newest first


def test_quote_patch_withdraw_and_recompute(demo: dict[str, Any]) -> None:
    broker: TestClient = demo["broker"]
    res = broker.patch(f"{V}/quotes/{demo['summit']}", json={"status": "withdrawn"})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "withdrawn"
    comparison = broker.get(f"{V}/trips/{demo['trip_id']}/comparison").json()
    assert [r["quote"]["id"] for r in comparison["rows"]] == [demo["atlas"]]
    assert (
        broker.patch(f"{V}/quotes/{demo['summit']}", json={"status": "superseded"}).status_code
        == 422
    )
    assert (
        demo["assistant"]
        .patch(f"{V}/quotes/{demo['summit']}", json={"status": "active"})
        .status_code
        == 403
    )

    rec = broker.post(f"{V}/trips/{demo['trip_id']}/recompute")
    assert rec.status_code == 200, rec.text
    assert rec.json()["recommended_quote_id"] == demo["atlas"]
    assert rec.json()["algorithm_version"]

    events = broker.get(f"{V}/trips/{demo['trip_id']}/events").json()
    assert events["total"] > 0


def test_reprocess_and_move_documents(demo: dict[str, Any]) -> None:
    broker: TestClient = demo["broker"]
    sms = demo["docs"]["summit_sms.txt"]
    res = broker.post(f"{V}/source-documents/{sms}/reprocess")
    assert res.status_code == 200, res.text
    assert res.json()["extraction_status"] == "succeeded"

    moved = broker.post(f"{V}/source-documents/{sms}/move", json={"quote_id": demo["atlas"]})
    assert moved.status_code == 200, moved.text
    assert moved.json()["quote_id"] == demo["atlas"]
    both = broker.post(
        f"{V}/source-documents/{sms}/move",
        json={"quote_id": demo["atlas"], "operator_id": demo["operators"]["Atlas Air Charter"]},
    )
    assert both.status_code == 422
    assert demo["assistant"].post(f"{V}/source-documents/{sms}/reprocess").status_code == 403


def test_proposal_lifecycle_rules(demo: dict[str, Any]) -> None:
    broker: TestClient = demo["broker"]
    trip_id = demo["trip_id"]
    draft = broker.post(f"{V}/trips/{trip_id}/proposals", json={"title": "JS184 options"})
    assert draft.status_code == 201, draft.text
    pid = draft.json()["id"]
    assert [o["quote_id"] for o in draft.json()["options"]] == [demo["atlas"]]

    patched = broker.patch(f"{V}/proposals/{pid}", json={"markup_pct": 10, "client_name": "Pat"})
    assert patched.status_code == 200
    assert patched.json()["options"][0]["client_total_cents"] == 4_930_200  # 44,820 x 1.1

    # Not sent yet: no lifecycle moves but cancel/send.
    assert broker.post(f"{V}/proposals/{pid}/mark-accepted", json={}).status_code == 409
    assert broker.post(f"{V}/proposals/{pid}/decline").status_code == 409
    assert broker.post(f"{V}/proposals/{pid}/rotate-link").status_code == 409

    sent = broker.post(f"{V}/proposals/{pid}/send").json()
    assert sent["status"] == "sent" and sent["share_url"]
    assert broker.patch(f"{V}/proposals/{pid}", json={"title": "x"}).status_code == 409
    assert broker.post(f"{V}/proposals/{pid}/decline").json()["status"] == "declined"

    listing = broker.get(f"{V}/proposals", params={"status": "declined"}).json()
    assert [p["id"] for p in listing["items"]] == [pid]
    assert broker.get(f"{V}/trips/{trip_id}/proposals").json()["total"] == 1
    assert broker.get(f"{V}/proposals", params={"trip_id": trip_id}).json()["total"] == 1

    trip = broker.get(f"{V}/trips/{trip_id}").json()
    assert trip["status"] == "proposed"
    assert demo["assistant"].get(f"{V}/proposals/{pid}").status_code == 403


def test_analytics_metrics(demo: dict[str, Any]) -> None:
    broker: TestClient = demo["broker"]
    window = {"date_from": (datetime.now(UTC) - timedelta(days=30)).date().isoformat()}
    for metric in (
        "quote-volume",
        "response-times",
        "true-cost-distribution",
        "fee-types",
        "aircraft-mix",
        "funnel",
    ):
        res = broker.get(f"{V}/analytics/{metric}", params=window)
        assert res.status_code == 200, (metric, res.text)
        assert res.json()["metric"] == metric
    assert broker.get(f"{V}/analytics/nope").status_code == 422
    backwards = broker.get(
        f"{V}/analytics/funnel", params={"date_from": "2026-12-01", "date_to": "2026-01-01"}
    )
    assert backwards.status_code == 422
    overview = broker.get(f"{V}/analytics/overview", params=window).json()
    assert overview["funnel"]["quoted"] == 1
    assert overview["aircraft_mix"]["n_quotes"] == 2
    assert overview["response_times"]["n"] == 2
