"""The whole broker flow through the API with the real rules extractor:

signup -> trip -> RFQ -> ingest the six demo files -> comparison -> review
queue -> proposal gate -> review -> proposal at 5% -> send -> public view and
accept -> booked -> audit trail.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import time_machine
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.extraction.registry import select_extractor
from tests.conftest import WEB_HEADERS

pytestmark = pytest.mark.integration

V = "/api/v1"
# Atlas's quote is valid until 2026-10-10; later, `quote_expired` drops it.
NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
DEMO = Path(__file__).resolve().parents[2] / "fixtures" / "demo"
MANIFEST = json.loads((DEMO / "manifest.json").read_text())
MEDIA = {".pdf": "application/pdf", ".eml": "message/rfc822", ".txt": "text/plain"}
FORBIDDEN_PUBLIC = ("Atlas", "Positioning", "N684AC", "confidence", "markup")


@pytest.fixture
def web(app: FastAPI, settings: Settings) -> Iterator[TestClient]:
    with time_machine.travel(NOW, tick=True), TestClient(app, headers=WEB_HEADERS) as client:
        app.state.extractor = select_extractor(settings)  # rules extractor, as in the seed
        yield client


def _ok(res: Any, status: int = 200) -> Any:
    assert res.status_code == status, f"{res.request.method} {res.request.url}: {res.text}"
    return res.json()


def _row(comparison: dict[str, Any], operator: str) -> dict[str, Any]:
    return next(r for r in comparison["rows"] if r["quote"]["operator_name"] == operator)


def test_ingest_verify_propose_book(web: TestClient, client: TestClient) -> None:
    # --- signup and trip
    _ok(
        web.post(
            f"{V}/auth/signup",
            json={
                "workspace_name": "JetStream Demo Brokerage",
                "full_name": "Demo Broker",
                "email": "demo@jetstream.example",
                "password": "a-long-enough-password",
            },
        ),
        201,
    )
    spec = MANIFEST["trip"]
    trip = _ok(
        web.post(
            f"{V}/trips",
            json={
                "reference": spec["reference"],
                "pax": spec["pax"],
                "client_name": "Private client",
                "preferences": {"wifi_required": True},
                "legs": [
                    {
                        "origin_icao": spec["origin"],
                        "destination_icao": spec["destination"],
                        "depart_local": spec["depart_local"],
                    }
                ],
            },
        ),
        201,
    )
    trip_id = trip["id"]
    assert trip["legs"][0]["depart_tz"] == "America/New_York"  # defaulted from the airport

    # --- RFQ: eight operators contacted
    t0 = datetime.now(UTC).replace(microsecond=0) - timedelta(days=1)
    rfq = _ok(
        web.post(
            f"{V}/trips/{trip_id}/operators",
            json={
                "new_operators": [{"name": r["operator"]} for r in MANIFEST["rfq"]],
                "requested_at": t0.isoformat(),
            },
        ),
        201,
    )
    assert rfq["total"] == 8
    operators = {r["operator_name"]: r for r in rfq["items"]}

    # --- ingest the six demo files in manifest order
    for entry in MANIFEST["files"]:
        path = DEMO / entry["file"]
        form = {
            "channel": entry["channel"],
            "sender": entry["sender"],
            "received_at": (t0 + timedelta(minutes=entry["received_offset_minutes"])).isoformat(),
            "operator_id": operators[entry["operator"]]["operator_id"],
        }
        if entry["subject"]:
            form["subject"] = entry["subject"]
        res = web.post(
            f"{V}/trips/{trip_id}/quotes/ingest",
            data=form,
            files={"file": (path.name, path.read_bytes(), MEDIA[path.suffix])},
        )
        body = _ok(res, 201)
        assert body["source_document"]["extraction_status"] == "succeeded", entry["file"]
        assert body["quote"] is not None, entry["file"]

    # --- comparison numbers
    comparison = _ok(web.get(f"{V}/trips/{trip_id}/comparison"))
    assert len(comparison["rows"]) == 4
    atlas = _row(comparison, "Atlas Air Charter")
    summit = _row(comparison, "Summit Executive Aviation")
    assert atlas["quote"]["known_total_cents"] == 4_482_000
    assert atlas["quote"]["is_fully_priced"] is True
    assert atlas["quote"]["is_recommended"] is True
    assert comparison["recommended_quote_id"] == atlas["quote"]["id"]
    assert comparison["rows"][0]["quote"]["id"] == atlas["quote"]["id"]
    assert summit["quote"]["known_total_cents"] == 4_198_000
    assert summit["quote"]["is_fully_priced"] is False
    assert _row(comparison, "SkyBridge Aviation")["quote"]["known_total_cents"] == 4_720_000
    assert _row(comparison, "Northstar Jets")["quote"]["known_total_cents"] == 5_240_000
    categories = [c["category"] for c in comparison["fee_columns"]]
    assert "positioning" in categories and "fuel_surcharge" in categories

    rec = _ok(web.get(f"{V}/trips/{trip_id}/recommendation"))
    assert rec["recommended_quote_id"] == atlas["quote"]["id"]
    assert rec["ranking"][0]["quote_id"] == atlas["quote"]["id"]
    assert rec["ranking"][0]["fit_score"] == 96
    assert len(rec["checks"]) == 5 and all(c["passed"] for c in rec["checks"])
    assert len(rec["ranking"][0]["signals"]) == 8

    detail = _ok(web.get(f"{V}/quotes/{atlas['quote']['id']}"))
    assert {s["original_filename"] for s in detail["sources"]} >= {"atlas_quote_01.pdf"}
    assert detail["fit_breakdown"]["fit"] == 96

    # --- review queue: Summit's fuel at 61
    queue = _ok(web.get(f"{V}/trips/{trip_id}/review-queue"))["items"]
    summit_fuel = next(
        i
        for i in queue
        if i["kind"] == "field"
        and i["operator_name"] == "Summit Executive Aviation"
        and i["field"]["key"] == "fee.fuel_surcharge"
    )
    assert summit_fuel["field"]["confidence"] == 61
    # The blocking flag rides on the same queue item as its field.
    assert summit_fuel["flag"]["type"] == "ambiguous_charge"
    assert summit_fuel["flag"]["blocking"] is True

    # --- a proposal naming Summit is refused with reasons
    res = web.post(
        f"{V}/trips/{trip_id}/proposals",
        json={"quote_ids": [atlas["quote"]["id"], summit["quote"]["id"]], "markup_pct": 5},
    )
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "ineligible_quotes"
    assert summit["quote"]["id"] in res.json()["fields"]

    # --- review: verify Atlas's headline, accept Summit's fuel estimate
    headline = next(f for f in detail["fields"] if f["key"] == "headline_price")
    verified = _ok(
        web.post(f"{V}/fields/{headline['id']}/verify", json={"version": headline["version"]})
    )
    assert verified["status"] == "verified" and verified["locked"] is True
    stale = web.post(f"{V}/fields/{headline['id']}/verify", json={"version": headline["version"]})
    assert stale.status_code == 409
    assert stale.json()["code"] == "stale_version"

    field = summit_fuel["field"]
    accepted = _ok(
        web.post(
            f"{V}/fields/{field['id']}/accept",
            json={"version": field["version"], "note": "Dan confirmed ~850 by phone"},
        )
    )
    assert accepted["status"] == "accepted"
    history = _ok(web.get(f"{V}/fields/{field['id']}/history"))
    assert history["total"] >= 1

    # --- the default proposal: every eligible quote, Atlas first, 5% markup
    proposal = _ok(web.post(f"{V}/trips/{trip_id}/proposals", json={"markup_pct": 5}), 201)
    assert proposal["status"] == "draft"
    first = proposal["options"][0]
    assert first["quote_id"] == atlas["quote"]["id"]
    assert first["is_recommended"] is True
    assert first["cost_basis_cents"] == 4_482_000
    assert first["client_total_cents"] == 4_706_100  # 44,820 x 1.05 = 47,061
    assert first["markup_cents"] == 224_100
    preview = _ok(web.get(f"{V}/proposals/{proposal['id']}/client-preview"))
    assert preview["options"][0]["client_total_cents"] == 4_706_100

    sent = _ok(web.post(f"{V}/proposals/{proposal['id']}/send"))
    assert sent["status"] == "sent"
    token = sent["share_url"].rsplit("/", 1)[1]

    # --- the client's view
    public = client.get(f"{V}/public/proposals/{token}")
    assert public.status_code == 200, public.text
    for word in FORBIDDEN_PUBLIC:
        assert word.lower() not in public.text.lower(), word
    option_id = public.json()["options"][0]["option_id"]
    accepted_p = client.post(
        f"{V}/public/proposals/{token}/accept",
        json={"option_id": option_id, "name": "Private client"},
        headers=WEB_HEADERS,
    )
    assert accepted_p.status_code == 200, accepted_p.text
    assert accepted_p.json()["status"] == "accepted"

    # --- booked
    booked = _ok(web.post(f"{V}/proposals/{proposal['id']}/mark-booked", json={}))
    assert booked["status"] == "booked"
    trip_after = _ok(web.get(f"{V}/trips/{trip_id}"))
    assert trip_after["status"] == "booked"
    assert trip_after["booked_quote_id"] == atlas["quote"]["id"]

    # --- the audit trail, with before/after for each step
    events = _ok(web.get(f"{V}/audit-events", params={"trip_id": trip_id, "limit": 200}))
    actions = [e["action"] for e in events["items"]]
    for expected in (
        "trip.create",
        "rfq.create",
        "document.ingest",
        "field.verify",
        "field.accept",
        "proposal.send",
        "public.proposal_view",
        "public.proposal_accept",
        "proposal.mark_booked",
        "trip.book",
    ):
        assert expected in actions, (expected, sorted(set(actions)))
    verify_event = next(e for e in events["items"] if e["action"] == "field.verify")
    assert verify_event["before"] and verify_event["after"]
    public_accept = next(e for e in events["items"] if e["action"] == "public.proposal_accept")
    assert public_accept["actor_kind"] == "public"
    assert public_accept["after"]["status"] == "accepted"

    funnel = _ok(
        web.get(
            f"{V}/analytics/funnel",
            params={"date_from": (t0 - timedelta(days=1)).date().isoformat()},
        )
    )
    assert (funnel["created"], funnel["quoted"], funnel["proposal_sent"], funnel["booked"]) == (
        1,
        1,
        1,
        1,
    )
