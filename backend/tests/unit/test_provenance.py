"""Provenance: snippets found, not found, and found on another page (spec §3.4)."""

from __future__ import annotations

from app.extraction.base import DocumentInput, PageText
from app.extraction.provenance import (
    SCANNED_CONFIDENCE_CAP,
    UNVERIFIED_PENALTY,
    locate,
    normalize_for_match,
    verify,
)
from app.extraction.types import Evidence, ExtractedFee, ExtractedField, ExtractionResult, Money
from app.models.enums import DocumentChannel, DocumentKind, FeeCategory

PAGES = (
    PageText(1, "Atlas Air Charter\nCharter price ...... $41,800.00"),
    PageText(2, "Ramp / handling fee (KOPF) ...... $420.00\nTotal ...... $44,820.00"),
)
PDF = DocumentInput(
    kind=DocumentKind.PDF,
    channel=DocumentChannel.PDF_UPLOAD,
    media_type="application/pdf",
    pages=PAGES,
)


def result(*items: tuple[str, int | None, int]) -> ExtractionResult:
    fields = [
        ExtractedField(
            key="headline_price",
            value=Money(amount_minor=4_180_000, currency="USD"),
            confidence=conf,
            evidence=Evidence(snippet=snippet, page=page),
        )
        for snippet, page, conf in items
    ]
    return ExtractionResult(
        extractor="claude", extractor_version="t", intent="quote", fields=fields, fees=[]
    )


def test_normalize_for_match() -> None:
    assert normalize_for_match("  Charter\n  PRICE\t…  ") == "charter price ..."
    assert normalize_for_match("> quoted\n>> line") == "quoted line"


def test_locate_returns_page_offsets() -> None:
    location = locate("charter  PRICE ...... $41,800.00", PAGES, hint_page=None)
    assert location is not None
    assert location.page == 1
    assert PAGES[0].text[location.char_start : location.char_end] == (
        "Charter price ...... $41,800.00"
    )
    assert locate("nowhere", PAGES, hint_page=1) is None
    assert locate("   ", PAGES, hint_page=1) is None


def test_found_on_claimed_page_is_verified() -> None:
    verified, report = verify(result(("Charter price ...... $41,800.00", 1, 92)), PDF)
    [item] = verified.fields
    assert item.evidence.verified
    assert item.evidence.page == 1
    assert item.confidence == 92
    assert (report.verified, report.pages_corrected, report.unverified) == (1, 0, [])


def test_found_on_another_page_is_corrected() -> None:
    verified, report = verify(result(("Total ...... $44,820.00", 1, 90)), PDF)
    [item] = verified.fields
    assert item.evidence.verified
    assert item.evidence.page == 2
    assert PAGES[1].text[item.evidence.char_start : item.evidence.char_end] == (
        "Total ...... $44,820.00"
    )
    assert report.pages_corrected == 1


def test_not_found_loses_confidence() -> None:
    fee = ExtractedFee(
        category=FeeCategory.FUEL_SURCHARGE,
        label="Fuel",
        status="stated",
        amount=Money(amount_minor=100_000, currency="USD"),
        confidence=80,
        evidence=Evidence(snippet="Fuel surcharge $1,000", page=2),
    )
    raw = result(("invented text", 1, 10)).model_copy(update={"fees": [fee]})
    verified, report = verify(raw, PDF)
    assert not verified.fields[0].evidence.verified
    assert verified.fields[0].confidence == 0  # 10 - 15, floored at 0
    assert verified.fees[0].confidence == 80 - UNVERIFIED_PENALTY
    assert report.unverified == ["headline_price", "fee.fuel_surcharge"]


def test_scanned_documents_are_capped_not_penalized() -> None:
    scanned = DocumentInput(
        kind=DocumentKind.PDF,
        channel=DocumentChannel.PDF_UPLOAD,
        media_type="application/pdf",
        pages=(PageText(1, ""),),
        is_scanned=True,
    )
    verified, report = verify(result(("Charter price $41,800", 1, 97)), scanned)
    [item] = verified.fields
    assert item.confidence == SCANNED_CONFIDENCE_CAP
    assert not item.evidence.verified
    assert report.unverified == []


def test_text_sources_keep_page_none() -> None:
    sms = DocumentInput(
        kind=DocumentKind.SMS,
        channel=DocumentChannel.SMS,
        media_type="text/plain",
        pages=(PageText(1, "quote is 38,900 all in, crew overnight 700 extra."),),
    )
    verified, _ = verify(result(("quote is 38,900 all in", None, 82)), sms)
    [item] = verified.fields
    assert item.evidence.verified
    assert item.evidence.page is None
    assert (item.evidence.char_start, item.evidence.char_end) == (0, 22)


def test_quoted_email_snippet_matches_body() -> None:
    email = DocumentInput(
        kind=DocumentKind.EMAIL,
        channel=DocumentChannel.EMAIL,
        media_type="message/rfc822",
        pages=(PageText(1, "New price below.\n\n> Charter price:\n> $38,000"),),
    )
    verified, _ = verify(result(("Charter price: $38,000", None, 70)), email)
    assert verified.fields[0].evidence.verified
