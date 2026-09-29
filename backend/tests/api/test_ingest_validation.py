"""Ingest validation: one of file or text, size and type limits, scanned PDFs,
explicit targets, duplicates and the background path."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import PipelineMode, Settings
from app.extraction.registry import select_extractor
from app.models import Flag
from app.models.enums import Role
from tests import factories
from tests.conftest import ClientFactory

V = "/api/v1"
DEMO = Path(__file__).resolve().parents[2] / "fixtures" / "demo"
SMS = "Summit Executive: G200 KTEB-KOPF 18 Oct, $38,500 all in. Fuel surcharge TBD."


def _trip(client: TestClient, db: Session) -> uuid.UUID:
    trip = factories.make_trip(db, client.user.workspace)  # type: ignore[attr-defined]
    db.commit()
    return trip.id


def _ingest(client: TestClient, trip_id: uuid.UUID, **kw: object) -> object:
    return client.post(f"{V}/trips/{trip_id}/quotes/ingest", **kw)  # type: ignore[arg-type]


def test_exactly_one_of_file_or_text(client_as: ClientFactory, db: Session) -> None:
    assistant = client_as(Role.ASSISTANT)
    trip_id = _trip(assistant, db)
    both = _ingest(
        assistant, trip_id, data={"text": SMS}, files={"file": ("q.txt", b"quote", "text/plain")}
    )
    assert both.status_code == 422  # type: ignore[attr-defined]
    assert both.json()["code"] == "invalid_input"  # type: ignore[attr-defined]
    neither = _ingest(assistant, trip_id, data={"channel": "sms"})
    assert neither.status_code == 422  # type: ignore[attr-defined]
    blank = _ingest(assistant, trip_id, data={"text": "   "})
    assert blank.status_code == 422  # type: ignore[attr-defined]


def test_size_limit_and_empty_files(
    client_as: ClientFactory, db: Session, settings: Settings
) -> None:
    broker = client_as(Role.BROKER)
    trip_id = _trip(broker, db)
    settings.max_upload_mb = 1
    big = b"%PDF-1.7\n" + b"0" * (1024 * 1024)
    res = _ingest(broker, trip_id, files={"file": ("big.pdf", big, "application/pdf")})
    assert res.status_code == 413  # type: ignore[attr-defined]
    empty = _ingest(broker, trip_id, files={"file": ("empty.pdf", b"", "application/pdf")})
    assert empty.status_code == 422  # type: ignore[attr-defined]


def test_rejects_unknown_targets_and_bad_metadata(client_as: ClientFactory, db: Session) -> None:
    broker = client_as(Role.BROKER)
    trip_id = _trip(broker, db)
    ws = broker.user.workspace  # type: ignore[attr-defined]
    other_trip = factories.make_trip(db, ws)
    op = factories.make_operator(db, ws, "Atlas Air Charter")
    other_quote = factories.make_quote(db, other_trip, op)
    db.commit()

    # A quote of the same workspace but another trip is not attachable.
    res = _ingest(broker, trip_id, data={"text": SMS, "quote_id": str(other_quote.id)})
    assert res.status_code == 404  # type: ignore[attr-defined]
    res = _ingest(broker, trip_id, data={"text": SMS, "operator_id": str(uuid.uuid4())})
    assert res.status_code == 404  # type: ignore[attr-defined]
    res = _ingest(broker, uuid.uuid4(), data={"text": SMS})
    assert res.status_code == 404  # type: ignore[attr-defined]
    res = _ingest(broker, trip_id, data={"text": SMS, "channel": "carrier-pigeon"})
    assert res.status_code == 422  # type: ignore[attr-defined]
    res = _ingest(broker, trip_id, data={"text": SMS, "received_at": "2026-10-01T09:00:00"})
    assert res.status_code == 422, "naive received_at must be rejected"  # type: ignore[attr-defined]


def test_magic_bytes_decide_the_type(client_as: ClientFactory, db: Session) -> None:
    broker = client_as(Role.BROKER)
    trip_id = _trip(broker, db)
    fake_pdf = _ingest(
        broker, trip_id, files={"file": ("quote.pdf", b"MZ\x90\x00 not a pdf", "application/pdf")}
    )
    assert fake_pdf.status_code == 422, fake_pdf.text  # type: ignore[attr-defined]
    exe = _ingest(
        broker,
        trip_id,
        files={"file": ("x.exe", b"MZ\x90\x00\x03" + b"\x00" * 64, "application/octet-stream")},
    )
    assert exe.status_code == 422  # type: ignore[attr-defined]
    # A real PDF sent with a misleading name and type is still read as a PDF.
    data = (DEMO / "atlas_quote_01.pdf").read_bytes()
    res = _ingest(broker, trip_id, files={"file": ("quote.txt", data, "text/plain")})
    assert res.status_code == 201, res.text  # type: ignore[attr-defined]
    assert res.json()["source_document"]["media_type"] == "application/pdf"  # type: ignore[attr-defined]


def test_pasted_text_and_duplicates(client_as: ClientFactory, db: Session) -> None:
    assistant = client_as(Role.ASSISTANT)
    trip_id = _trip(assistant, db)
    first = _ingest(
        assistant, trip_id, data={"text": SMS, "channel": "sms", "sender": "+16175550142"}
    )
    assert first.status_code == 201, first.text  # type: ignore[attr-defined]
    body = first.json()  # type: ignore[attr-defined]
    assert body["duplicate"] is False
    assert body["source_document"]["channel"] == "sms"
    assert body["source_document"]["extraction_status"] != "pending"

    again = _ingest(
        assistant, trip_id, data={"text": SMS, "channel": "sms", "sender": "+16175550142"}
    )
    assert again.status_code in {200, 201}  # type: ignore[attr-defined]
    assert again.json()["duplicate"] is True  # type: ignore[attr-defined]
    assert again.json()["source_document"]["id"] == body["source_document"]["id"]  # type: ignore[attr-defined]
    listed = assistant.get(f"{V}/trips/{trip_id}/source-documents").json()
    assert listed["total"] == 1


def test_scanned_pdf_without_claude_needs_manual_entry(
    app: FastAPI, client_as: ClientFactory, db: Session, settings: Settings
) -> None:
    app.state.extractor = select_extractor(settings)  # the real rules extractor, no Claude
    broker = client_as(Role.BROKER)
    trip_id = _trip(broker, db)
    data = (DEMO / "scanned_quote.pdf").read_bytes()
    res = _ingest(broker, trip_id, files={"file": ("scanned_quote.pdf", data, "application/pdf")})
    assert res.status_code == 201, res.text  # type: ignore[attr-defined]
    doc = res.json()["source_document"]  # type: ignore[attr-defined]
    assert doc["is_scanned"] is True
    assert doc["extraction_status"] == "needs_manual"
    flags = db.scalars(select(Flag).where(Flag.source_document_id == uuid.UUID(doc["id"]))).all()
    assert "ocr_unavailable" in {f.type.value for f in flags}


def test_background_mode_returns_202_and_processes_after(
    client_as: ClientFactory, db: Session, settings: Settings
) -> None:
    broker = client_as(Role.BROKER)
    trip_id = _trip(broker, db)
    settings.pipeline_mode = PipelineMode.BACKGROUND
    res = _ingest(broker, trip_id, data={"text": SMS, "channel": "sms"})
    assert res.status_code == 202, res.text  # type: ignore[attr-defined]
    doc = res.json()["source_document"]  # type: ignore[attr-defined]
    assert doc["extraction_status"] == "pending"
    # TestClient runs background tasks before returning; poll once.
    polled = broker.get(f"{V}/source-documents/{doc['id']}").json()
    assert polled["extraction_status"] not in {"pending", "processing"}
    assert polled["text_pages"], "page texts are stored for the viewer"
