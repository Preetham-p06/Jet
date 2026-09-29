"""Document loading: PDFs, scanned detection, email, WhatsApp, SMS and upload checks."""

from __future__ import annotations

import io
from datetime import UTC, datetime
from email.message import EmailMessage
from pathlib import Path

import pytest
from pydantic import SecretStr
from pypdf import PdfWriter

from app.config import Settings
from app.errors import PayloadTooLarge, Unprocessable
from app.extraction.documents import (
    LoadedDocument,
    is_scanned,
    load_document,
    load_email,
    load_pdf,
    load_text,
    load_whatsapp,
    sniff,
    split_quoted,
)
from app.models.enums import DocumentChannel, DocumentKind

DEMO = Path(__file__).resolve().parents[2] / "fixtures" / "demo"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def settings(**kw: object) -> Settings:
    return Settings(_env_file=None, **kw)  # type: ignore[call-arg]


def load(
    data: bytes | None = None,
    text: str | None = None,
    *,
    config: Settings | None = None,
    **kw: object,
) -> LoadedDocument:
    args: dict[str, object] = {
        "filename": None,
        "channel": None,
        "sender": None,
        "subject": None,
        "received_at": None,
        **kw,
    }
    return load_document(data=data, text=text, settings=config or settings(), **args)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- PDF


def test_pdf_text_per_page() -> None:
    loaded = load_pdf((DEMO / "atlas_quote_01.pdf").read_bytes(), max_pages=50)
    doc = loaded.input
    assert loaded.page_count == 2
    assert doc.kind is DocumentKind.PDF
    assert doc.channel is DocumentChannel.PDF_UPLOAD
    assert [p.page for p in doc.pages] == [1, 2]
    assert "Charter price" in doc.pages[0].text
    assert "Fuel surcharge" in doc.pages[1].text
    assert "Fuel surcharge" not in doc.pages[0].text
    assert "…" not in doc.full_text  # NFKC-normalized dot leaders
    assert not doc.is_scanned
    assert doc.raw_bytes is not None


def test_scanned_pdf_is_detected() -> None:
    doc = load_pdf((DEMO / "scanned_quote.pdf").read_bytes(), max_pages=50).input
    assert doc.is_scanned
    assert not doc.has_text_layer


def test_is_scanned_threshold() -> None:
    assert is_scanned([])
    assert is_scanned(["", "Page 2"])
    assert not is_scanned(["x" * 40])
    assert is_scanned(["x" * 79, ""])


def _encrypted(user_password: str) -> bytes:
    writer = PdfWriter(clone_from=str(DEMO / "atlas_quote_01.pdf"))
    writer.encrypt(user_password=user_password, owner_password="owner", algorithm="RC4-128")
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def test_encrypted_pdf_with_empty_password_opens() -> None:
    doc = load_pdf(_encrypted(""), max_pages=50).input
    assert "Charter price" in doc.pages[0].text


def test_password_protected_pdf_is_rejected() -> None:
    with pytest.raises(Unprocessable) as info:
        load_pdf(_encrypted("secret"), max_pages=50)
    assert info.value.code == "pdf_encrypted"


def test_too_many_pages() -> None:
    writer = PdfWriter()
    for _ in range(3):
        writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)
    with pytest.raises(Unprocessable) as info:
        load_pdf(buffer.getvalue(), max_pages=2)
    assert info.value.code == "too_many_pages"


def test_garbage_after_pdf_magic() -> None:
    with pytest.raises(Unprocessable) as info:
        load_pdf(b"%PDF-1.7\nnot really a pdf", max_pages=50)
    assert info.value.code == "pdf_unreadable"


# --------------------------------------------------------------------------- sniffing / limits


def test_sniff_uses_magic_bytes_not_filename() -> None:
    pdf = (DEMO / "revised-quote.pdf").read_bytes()
    assert sniff(pdf, "notes.txt") == (DocumentKind.PDF, "application/pdf")
    assert sniff(PNG, "quote.pdf") == (DocumentKind.IMAGE, "image/png")
    assert sniff(b"\xff\xd8\xff\xe0rest", None) == (DocumentKind.IMAGE, "image/jpeg")
    eml = (DEMO / "atlas_email_catering.eml").read_bytes()
    assert sniff(eml, "x.pdf")[0] is DocumentKind.EMAIL
    assert sniff((DEMO / "summit_sms.txt").read_bytes(), None)[0] is DocumentKind.TEXT


def test_sniff_rejects_binary() -> None:
    with pytest.raises(Unprocessable) as info:
        sniff(b"PK\x03\x04\x00\x00zipfile", "quote.zip")
    assert info.value.code == "unsupported_type"


def test_exactly_one_of_file_or_text() -> None:
    with pytest.raises(Unprocessable):
        load(data=b"x", text="y")
    with pytest.raises(Unprocessable):
        load()


def test_upload_size_limit() -> None:
    with pytest.raises(PayloadTooLarge):
        load(data=b"a" * (1024 * 1024 + 1), config=settings(max_upload_mb=1))


def test_page_limit_comes_from_settings() -> None:
    with pytest.raises(Unprocessable) as info:
        load(data=(DEMO / "atlas_quote_01.pdf").read_bytes(), config=settings(max_pdf_pages=1))
    assert info.value.code == "too_many_pages"


def test_images_need_claude() -> None:
    with pytest.raises(Unprocessable) as info:
        load(data=PNG, config=settings(extractor="rules"))
    assert info.value.code == "image_requires_claude"
    doc = load(data=PNG, config=settings(anthropic_api_key=SecretStr("k"))).input
    assert doc.kind is DocumentKind.IMAGE
    assert doc.is_scanned
    assert doc.raw_bytes == PNG


# --------------------------------------------------------------------------- email


def test_demo_email() -> None:
    loaded = load(data=(DEMO / "atlas_email_catering.eml").read_bytes())
    doc = loaded.input
    assert doc.kind is DocumentKind.EMAIL
    assert doc.channel is DocumentChannel.EMAIL
    assert doc.sender == "Atlas Air Charter <quotes@atlas-air-charter.example>"
    assert doc.subject == "RE: JS184 KTEB-KOPF 18 Oct"
    assert doc.received_at == datetime(2026, 10, 2, 18, 12, tzinfo=UTC)
    assert "catering is included" in doc.pages[0].text
    assert "\r" not in doc.pages[0].text
    assert [m.is_quoted for m in doc.messages] == [False]


def test_email_with_pdf_attachment_and_quoted_reply() -> None:
    msg = EmailMessage()
    msg["From"] = "Summit Executive Aviation <dan@summit.example>"
    msg["To"] = "broker@example.com"
    msg["Subject"] = "Revised quote"
    msg["Date"] = "Sat, 03 Oct 2026 09:00:00 +0000"
    msg.set_content(
        "Revised quote attached.\n\nOn Fri, 2 Oct 2026, Dan wrote:\n> Charter price: $40,000\n"
    )
    pdf = (DEMO / "revised-quote.pdf").read_bytes()
    msg.add_attachment(pdf, maintype="application", subtype="pdf", filename="revised-quote.pdf")
    msg.add_attachment(b"not a pdf", maintype="text", subtype="csv", filename="notes.csv")
    loaded = load_email(msg.as_bytes())
    assert [(a.filename, a.media_type) for a in loaded.attachments] == [
        ("revised-quote.pdf", "application/pdf")
    ]
    assert loaded.attachments[0].data == pdf
    quoted, fresh = loaded.input.messages
    assert quoted.is_quoted
    assert quoted.sequence < fresh.sequence
    assert quoted.text == "Charter price: $40,000"
    assert fresh.text == "Revised quote attached."


def test_html_only_email_is_stripped() -> None:
    msg = EmailMessage()
    msg["From"] = "ops@example.com"
    msg["Subject"] = "Quote"
    msg.set_content(
        "<html><head><style>p{}</style></head><body><p>Charter price: $9,000</p>"
        "<p>Catering &amp; ice included</p></body></html>",
        subtype="html",
    )
    body = load_email(msg.as_bytes()).input.pages[0].text
    assert "Charter price: $9,000" in body
    assert "Catering & ice included" in body
    assert "<p>" not in body
    assert "p{}" not in body


def test_split_quoted_with_markers_only() -> None:
    fresh, quoted = split_quoted("New price $36,500\n> old price $38,000\n>> older")
    assert fresh == "New price $36,500"
    assert quoted == "old price $38,000\nolder"


# --------------------------------------------------------------------------- chat and SMS


def test_whatsapp_export() -> None:
    text = (
        "[10/2/26, 11:02:45] Lena - Meridian Air: Morning! Praetor 500 for JS184\n"
        "[10/2/26, 11:03:10] Lena - Meridian Air: $39,500 incl. standard charges\n"
        "and a second line\n"
        "10/2/26, 2:21 PM - Priya Shah: thanks!\n"
    )
    loaded = load(text=text)
    doc = loaded.input
    assert doc.kind is DocumentKind.WHATSAPP
    assert doc.channel is DocumentChannel.WHATSAPP
    assert [m.sequence for m in doc.messages] == [0, 1, 2]
    assert doc.messages[1].text == "$39,500 incl. standard charges\nand a second line"
    assert doc.messages[0].author == "Lena - Meridian Air"
    assert doc.messages[0].sent_at == datetime(2026, 10, 2, 11, 2, 45, tzinfo=UTC)
    assert doc.messages[2].sent_at == datetime(2026, 10, 2, 14, 21, tzinfo=UTC)
    assert doc.sender == "Lena - Meridian Air"
    assert load_whatsapp(text).input.messages == doc.messages


def test_sms_headers() -> None:
    doc = load(data=(DEMO / "summit_sms.txt").read_bytes()).input
    assert doc.kind is DocumentKind.SMS
    assert doc.channel is DocumentChannel.SMS
    assert doc.sender == "Summit Executive Aviation <+16175550142>"
    assert doc.received_at == datetime(2026, 10, 2, 20, 40, tzinfo=UTC)
    assert doc.pages[0].text.startswith("Hi it's Dan at Summit")
    assert "From:" not in doc.full_text


def test_explicit_metadata_wins_over_headers() -> None:
    received = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)
    doc = load(
        data=(DEMO / "summit_sms.txt").read_bytes(),
        sender="+16175550142",
        received_at=received,
        channel=DocumentChannel.SMS,
    ).input
    assert doc.sender == "+16175550142"
    assert doc.received_at == received


def test_pasted_text_without_headers() -> None:
    doc = load(text="Charter price: $12,000\nFrom: our Boston base").input
    assert doc.kind is DocumentKind.TEXT
    assert doc.channel is DocumentChannel.PASTE
    assert doc.full_text.startswith("Charter price")
    sms = load(text="quote is 12k", channel=DocumentChannel.SMS).input
    assert sms.kind is DocumentKind.SMS


def test_load_text_normalizes() -> None:
    doc = load_text("Price $41,800 – incl.", channel=DocumentChannel.PASTE).input
    assert doc.pages[0].text == "Price $41,800 - incl."
