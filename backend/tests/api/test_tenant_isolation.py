"""Workspace isolation: B gets 404 (never 403) on every by-id route of A's rows,
cannot reference A's rows in its own requests, and never sees them in lists."""

from __future__ import annotations

import re
import secrets
import uuid
from dataclasses import asdict
from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy.orm import Session

from app.models import Proposal, Quote, Trip
from tests import factories
from tests.api.routes import api_routes
from tests.api.seed import Seeded, seed_workspace
from tests.conftest import WEB_HEADERS, TwoWorkspaces

V = "/api/v1"
# Placeholders are filled from A's seeded ids; `{token}` gets an unknown token.
FIELD = {"version": 1}
MULTIPART = object()

#: (method, path) -> request body. Every path with an `{..._id}` or `{token}` is listed.
MATRIX: dict[tuple[str, str], Any] = {
    ("PATCH", "/users/{user_id}"): {"role": "broker"},
    ("DELETE", "/invites/{invite_id}"): None,
    ("GET", "/operators/{operator_id}"): None,
    ("PATCH", "/operators/{operator_id}"): {"notes": "x"},
    ("DELETE", "/operators/{operator_id}"): None,
    ("GET", "/trips/{trip_id}"): None,
    ("PATCH", "/trips/{trip_id}"): {"pax": 2},
    ("DELETE", "/trips/{trip_id}"): None,
    ("POST", "/trips/{trip_id}/recompute"): None,
    ("GET", "/trips/{trip_id}/events"): None,
    ("GET", "/trips/{trip_id}/operators"): None,
    ("POST", "/trips/{trip_id}/operators"): {"new_operators": [{"name": "Intruder Jets"}]},
    ("PATCH", "/trips/{trip_id}/operators/{trip_operator_id}"): {"notes": "x"},
    ("DELETE", "/trips/{trip_id}/operators/{trip_operator_id}"): None,
    ("POST", "/trips/{trip_id}/quotes/ingest"): MULTIPART,
    ("GET", "/trips/{trip_id}/source-documents"): None,
    ("GET", "/source-documents/{document_id}"): None,
    ("GET", "/source-documents/{document_id}/file"): None,
    ("POST", "/source-documents/{document_id}/reprocess"): None,
    ("POST", "/source-documents/{document_id}/move"): {"quote_id": str(uuid.uuid4())},
    ("GET", "/trips/{trip_id}/quotes"): None,
    ("GET", "/trips/{trip_id}/comparison"): None,
    ("GET", "/quotes/{quote_id}"): None,
    ("PATCH", "/quotes/{quote_id}"): {"status": "withdrawn"},
    ("POST", "/quotes/{quote_id}/fields"): {"key": "seats", "value": 9},
    ("GET", "/trips/{trip_id}/review-queue"): None,
    ("GET", "/fields/{field_id}/history"): None,
    ("POST", "/fields/{field_id}/verify"): FIELD,
    ("POST", "/fields/{field_id}/accept"): FIELD,
    ("PATCH", "/fields/{field_id}"): {"version": 1, "value": 9},
    ("POST", "/fields/{field_id}/reset"): FIELD,
    ("GET", "/trips/{trip_id}/flags"): None,
    ("POST", "/flags/{flag_id}/resolve"): {"resolution": "accepted_estimate"},
    ("POST", "/flags/{flag_id}/reopen"): None,
    ("GET", "/trips/{trip_id}/recommendation"): None,
    ("GET", "/trips/{trip_id}/proposals"): None,
    ("POST", "/trips/{trip_id}/proposals"): {},
    ("GET", "/proposals/{proposal_id}"): None,
    ("GET", "/proposals/{proposal_id}/client-preview"): None,
    ("PATCH", "/proposals/{proposal_id}"): {"title": "x"},
    ("POST", "/proposals/{proposal_id}/send"): None,
    ("POST", "/proposals/{proposal_id}/rotate-link"): None,
    ("POST", "/proposals/{proposal_id}/revoke-link"): None,
    ("POST", "/proposals/{proposal_id}/mark-accepted"): {},
    ("POST", "/proposals/{proposal_id}/mark-booked"): {},
    ("POST", "/proposals/{proposal_id}/decline"): None,
    ("POST", "/proposals/{proposal_id}/cancel"): None,
    ("POST", "/proposals/{proposal_id}/revise"): None,
    ("GET", "/public/proposals/{token}"): None,
    ("POST", "/public/proposals/{token}/accept"): {"option_id": str(uuid.uuid4()), "name": "X"},
}

_ID_PARAM = re.compile(r"\{(\w+_id|token)\}")


def _fill(path: str, ids: dict[str, Any]) -> str:
    def sub(m: re.Match[str]) -> str:
        name = m.group(1)
        if name == "token":
            return secrets.token_urlsafe(32)
        return str(ids[name])

    return V + _ID_PARAM.sub(sub, path)


@pytest.fixture
def seeded(app: FastAPI, two_workspaces: TwoWorkspaces, db: Session) -> dict[str, Any]:
    a = two_workspaces.a
    s: Seeded = seed_workspace(db, a.workspace, a.trip, app.state.storage)
    return {**asdict(s), "trip_id": a.trip.id}


def test_matrix_covers_every_id_route(app: FastAPI) -> None:
    by_id = {
        (r.method, r.path.removeprefix(V)) for r in api_routes(app) if _ID_PARAM.search(r.path)
    }
    assert by_id, "no routes found"
    missing = sorted(by_id - MATRIX.keys())
    stale = sorted(MATRIX.keys() - by_id)
    assert missing == [], f"add these routes to the isolation matrix: {missing}"
    assert stale == [], f"routes no longer exist: {stale}"


@pytest.mark.parametrize(("method", "path"), sorted(MATRIX))
def test_other_workspace_gets_404(
    two_workspaces: TwoWorkspaces,
    seeded: dict[str, Any],
    method: str,
    path: str,
) -> None:
    a, b = two_workspaces.a, two_workspaces.b
    url = _fill(path, seeded)
    body = MATRIX[(method, path)]
    kwargs: dict[str, Any] = {"headers": WEB_HEADERS}
    if body is MULTIPART:
        kwargs["data"] = {"text": "Quote: $10,000"}
    elif body is not None:
        kwargs["json"] = body
    res = b.admin.request(method, url, **kwargs)
    assert res.status_code == 404, f"{method} {url}: {res.status_code} {res.text}"
    assert res.json()["code"] in {"not_found"}
    # A still sees its own trip untouched.
    assert a.admin.get(f"{V}/trips/{a.trip.id}").status_code == 200


def test_rows_survive_the_attempts(
    two_workspaces: TwoWorkspaces, seeded: dict[str, Any], db: Session
) -> None:
    b = two_workspaces.b
    for method, path in sorted(MATRIX):
        if method == "DELETE":
            b.admin.delete(_fill(path, seeded))
    db.expire_all()
    assert db.get(Trip, seeded["trip_id"]) is not None
    assert db.get(Quote, seeded["quote_id"]) is not None
    assert db.get(Proposal, seeded["proposal_id"]).status.value == "sent"  # type: ignore[union-attr]


def test_cannot_reference_other_workspace_rows(
    two_workspaces: TwoWorkspaces, seeded: dict[str, Any], db: Session
) -> None:
    b = two_workspaces.b
    b_trip = b.trip.id

    # Ingest into B's own trip but attach A's quote or operator.
    for key in ("quote_id", "operator_id"):
        res = b.admin.post(
            f"{V}/trips/{b_trip}/quotes/ingest",
            data={"text": "Quote: $10,000", key: str(seeded[key])},
        )
        assert res.status_code == 404, res.text

    # A proposal on B's trip that names A's quote.
    res = b.admin.post(
        f"{V}/trips/{b_trip}/proposals", json={"quote_ids": [str(seeded["quote_id"])]}
    )
    assert res.status_code == 404, res.text

    # RFQ entries for A's operator.
    res = b.admin.post(
        f"{V}/trips/{b_trip}/operators", json={"operator_ids": [str(seeded["operator_id"])]}
    )
    assert res.status_code == 404

    # Filter B's global lists by A's trip.
    assert (
        b.admin.get(f"{V}/proposals", params={"trip_id": str(seeded["trip_id"])}).status_code == 404
    )
    assert (
        b.admin.get(f"{V}/audit-events", params={"trip_id": str(seeded["trip_id"])}).status_code
        == 404
    )

    # Moving B's own document onto A's quote.
    doc = factories.make_document(db, db.get(Trip, b_trip))  # type: ignore[arg-type]
    db.commit()
    res = b.admin.post(
        f"{V}/source-documents/{doc.id}/move", json={"quote_id": str(seeded["quote_id"])}
    )
    assert res.status_code == 404


def test_lists_never_include_other_workspace_rows(
    two_workspaces: TwoWorkspaces, seeded: dict[str, Any]
) -> None:
    a, b = two_workspaces.a, two_workspaces.b
    a_ids = {str(v) for v in seeded.values()}

    def ids(res_json: dict[str, Any]) -> set[str]:
        return {str(item.get("id")) for item in res_json["items"]}

    assert a.admin.get(f"{V}/operators").json()["total"] == 1
    for url in (
        f"{V}/trips",
        f"{V}/operators",
        f"{V}/proposals",
        f"{V}/audit-events",
        f"{V}/users",
        f"{V}/invites",
        f"{V}/trips/{b.trip.id}/quotes",
        f"{V}/trips/{b.trip.id}/flags",
        f"{V}/trips/{b.trip.id}/source-documents",
        f"{V}/trips/{b.trip.id}/operators",
    ):
        res = b.admin.get(url)
        assert res.status_code == 200, url
        assert not ids(res.json()) & a_ids, url

    assert [t["id"] for t in b.admin.get(f"{V}/trips").json()["items"]] == [str(b.trip.id)]
    comparison = b.admin.get(f"{V}/trips/{b.trip.id}/comparison").json()
    assert comparison["rows"] == []

    window = {"date_from": "2026-01-01", "date_to": "2026-12-31"}  # the seed is dated 2026-10
    overview = b.admin.get(f"{V}/analytics/overview", params=window).json()
    assert overview["funnel"]["created"] == 1  # B's own JS184 only
    assert overview["aircraft_mix"]["n_quotes"] == 0
    assert overview["quote_volume"]["items"] == [] or all(
        m["count"] == 0 for m in overview["quote_volume"]["items"]
    )
    # A sees its own quote in the same metrics.
    assert a.admin.get(f"{V}/analytics/aircraft-mix", params=window).json()["n_quotes"] == 1
