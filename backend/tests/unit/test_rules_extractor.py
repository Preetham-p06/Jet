"""The rules extractor end to end: demo fixtures, Summit's confidences, status rules."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from app.extraction.base import (
    DocumentInput,
    DocumentUnreadable,
    ExtractionContext,
    LegContext,
    PageText,
)
from app.extraction.rules import confidence
from app.extraction.rules.extractor import RulesExtractor
from app.extraction.rules.segment import LineKind, segment
from app.extraction.types import ExtractedFee, ExtractionResult
from app.models.enums import DocumentChannel, DocumentKind, FeeCategory
from scripts.eval_extraction import compare, load_case_document, load_cases

ROOT = Path(__file__).resolve().parents[2]
SUMMIT_SMS = (
    "Hi it's Dan at Summit re JS184 KTEB-KOPF 18 Oct. quote is 38,900 all in, crew overnight "
    "700 extra. fuel may be extra, est. 850 depending on uplift at KOPF. Thx"
)
CTX = ExtractionContext(
    legs=(LegContext("KTEB", "KOPF", datetime(2026, 10, 18, 9, 0)),),
    pax=7,
    known_operator_names=("Atlas Air Charter", "Summit Executive Aviation"),
)


def text_doc(
    text: str, kind: DocumentKind = DocumentKind.TEXT, channel: DocumentChannel | None = None
) -> DocumentInput:
    return DocumentInput(
        kind=kind,
        channel=channel or DocumentChannel.PASTE,
        media_type="text/plain",
        pages=(PageText(1, text),),
    )


def extract(text: str, kind: DocumentKind = DocumentKind.TEXT) -> ExtractionResult:
    channel = DocumentChannel.SMS if kind is DocumentKind.SMS else None
    return RulesExtractor().extract(text_doc(text, kind, channel), CTX)


def fee(result: ExtractionResult, category: FeeCategory) -> ExtractedFee:
    [match] = [f for f in result.fees if f.category is category]
    return match


def field_value(result: ExtractionResult, key: str) -> object:
    values = [f.value for f in result.fields if f.key == key]
    return values[0] if values else None


# --------------------------------------------------------------------------- demo fixtures

DEMO_CASES = [c for c in load_cases() if c.demo]


@pytest.mark.parametrize("case", DEMO_CASES, ids=[c.case_id for c in DEMO_CASES])
def test_demo_fixture_matches_expected(case: object) -> None:
    from app.config import Settings
    from app.extraction.provenance import verify

    doc = load_case_document(case, Settings())  # type: ignore[arg-type]
    raw = RulesExtractor().extract(doc, CTX)
    result, report = verify(raw, doc)
    outcome = compare(case, result, None, strict=True)  # type: ignore[arg-type]
    misses = [i for i in outcome.items if not i["correct"]]
    assert misses == []
    assert outcome.strict_failures == []
    assert report.unverified == []


def test_manifest_lists_every_demo_file_with_offsets() -> None:
    manifest = json.loads((ROOT / "fixtures/demo/manifest.json").read_text())
    files = {entry["file"]: entry for entry in manifest["files"]}
    assert set(files) == {
        "atlas_quote_01.pdf",
        "atlas_email_catering.eml",
        "quote-final-v7.pdf",
        "operator_quote_18.pdf",
        "revised-quote.pdf",
        "summit_sms.txt",
    }
    first_response = {
        op: min(e["received_offset_minutes"] for e in files.values() if e["operator"] == op)
        for op in {e["operator"] for e in files.values()}
    }
    hours = sorted(round(minutes / 60, 1) for minutes in first_response.values())
    assert hours == [1.4, 2.1, 3.6, 5.2]
    for entry in files.values():
        assert (ROOT / "fixtures/demo" / entry["file"]).is_file()
        stem = entry["file"].rsplit(".", 1)[0]
        assert (ROOT / "fixtures/demo/expected" / f"{stem}.json").is_file()


# --------------------------------------------------------------------------- Summit


def test_summit_sms_confidences() -> None:
    result = extract(SUMMIT_SMS, DocumentKind.SMS)
    fuel = fee(result, FeeCategory.FUEL_SURCHARGE)
    assert fuel.status == "estimated"
    assert fuel.amount is not None
    assert fuel.amount.amount_minor == 85_000
    assert fuel.hedged
    assert not fuel.explicitly_extra
    assert fuel.confidence == 61  # 82 - 15 - 6
    crew = fee(result, FeeCategory.CREW_OVERNIGHT)
    assert crew.status == "stated"
    assert crew.amount is not None
    assert crew.amount.amount_minor == 70_000
    assert crew.explicitly_extra
    assert crew.confidence == 84  # 82 + 2
    headline = field_value(result, "headline_price")
    assert getattr(headline, "amount_minor", None) == 3_890_000
    assert field_value(result, "all_in") is True
    assert result.intent == "quote"


def test_confidence_table() -> None:
    assert confidence.score(LineKind.INFORMAL, hedge=True, estimate=True) == 61
    assert confidence.score(LineKind.INFORMAL, explicit_extra=True) == 84
    assert confidence.score(LineKind.LABELLED, currency_marker=True) == 95
    assert confidence.score(LineKind.QUOTED, hedge=True, far_from_anchor=True, conflict=True) == 25
    assert confidence.clamp(140) == 99
    assert confidence.clamp(-3) == 5


# --------------------------------------------------------------------------- segmentation


def test_clause_split_keeps_est_and_thousands_together() -> None:
    clauses = segment(text_doc(SUMMIT_SMS, DocumentKind.SMS, DocumentChannel.SMS))
    texts = [c.text for c in clauses]
    assert "quote is 38,900 all in" in texts
    assert "est. 850 depending on uplift at KOPF." in texts
    fuel_clause = texts.index("fuel may be extra")
    assert clauses[fuel_clause].sentence_index == clauses[fuel_clause + 1].sentence_index
    assert all(c.line_kind is LineKind.INFORMAL for c in clauses)
    for clause in clauses:
        assert SUMMIT_SMS[clause.char_start : clause.char_end] == clause.text


def test_dot_leaders_do_not_split_lines() -> None:
    doc = DocumentInput(
        kind=DocumentKind.PDF,
        channel=DocumentChannel.PDF_UPLOAD,
        media_type="application/pdf",
        pages=(PageText(1, "Charter price ........ $41,800.00\nPositioning: $900"),),
    )
    clauses = segment(doc)
    assert [c.text for c in clauses] == ["Charter price ........ $41,800.00", "Positioning: $900"]
    assert {c.line_kind for c in clauses} == {LineKind.LABELLED}
    assert {c.page for c in clauses} == {1}


# --------------------------------------------------------------------------- status rules


def test_included_and_not_included() -> None:
    result = extract("Catering: included\nDe-icing not included\nLanding fees incl.")
    catering = fee(result, FeeCategory.CATERING)
    assert (catering.status, catering.confidence) == ("included", 95)
    deicing = fee(result, FeeCategory.DEICING)
    assert deicing.status == "not_stated"
    assert deicing.explicitly_extra
    landing = fee(result, FeeCategory.LANDING)
    assert (landing.status, landing.confidence) == ("included", 93)


def test_one_qualifier_covers_every_moneyless_anchor() -> None:
    result = extract("Price includes FET and segment fees.")
    assert {(f.category, f.status) for f in result.fees} == {
        (FeeCategory.FET, "included"),
        (FeeCategory.SEGMENT_FEES, "included"),
    }


def test_anchor_without_amount_or_qualifier_yields_nothing() -> None:
    result = extract("dep 09:30 (earliest crew availability)")
    assert result.fees == []


def test_included_amount_is_kept_but_status_included() -> None:
    result = extract("Catering $450 included in the charter price.")
    catering = fee(result, FeeCategory.CATERING)
    assert catering.status == "included"
    assert catering.amount is not None
    assert catering.amount.amount_minor == 45_000


def test_waived_and_hedged_without_amount() -> None:
    result = extract("Positioning: waived\nDe-icing at cost if required.\nCatering: TBD")
    assert fee(result, FeeCategory.POSITIONING).status == "waived"
    deicing = fee(result, FeeCategory.DEICING)
    assert (deicing.status, deicing.hedged, deicing.confidence) == ("not_stated", True, 73)
    assert fee(result, FeeCategory.CATERING).status == "not_stated"


def test_percent_fee_and_hourly_rate() -> None:
    result = extract("Rate: $4,950/hr x 3.2 hrs, 2 hr daily minimum.\nFET 7.5% extra")
    assert getattr(field_value(result, "hourly_rate"), "amount_minor", None) == 495_000
    assert field_value(result, "billable_hours") == 3.2
    assert field_value(result, "daily_minimum_hours") == 2.0
    fet = fee(result, FeeCategory.FET)
    assert fet.amount is None
    assert str(fet.percent) == "7.5"
    assert fet.unit.value == "percent"
    assert fet.explicitly_extra


def test_unmapped_labelled_charge_becomes_other() -> None:
    result = extract("Charter price: $20,000\nPet fee: $150")
    other = fee(result, FeeCategory.OTHER)
    assert other.label == "Pet fee"
    assert other.amount is not None
    assert other.amount.amount_minor == 15_000


def test_far_anchor_penalty() -> None:
    result = extract(
        "Positioning for the empty leg from our Boston base as discussed with Mark is $900"
    )
    positioning = fee(result, FeeCategory.POSITIONING)
    assert positioning.confidence == confidence.score(
        LineKind.PROSE, currency_marker=True, far_from_anchor=True
    )


def test_conflicting_values_lose_20() -> None:
    result = extract("Charter price: $20,000\nCharter price: $21,000")
    [headline] = [f for f in result.fields if f.key == "headline_price"]
    assert headline.confidence == 95 - confidence.CONFLICT_PENALTY


def test_chat_messages_keep_their_sequence() -> None:
    from app.extraction.base import ChatMessage

    doc = DocumentInput(
        kind=DocumentKind.WHATSAPP,
        channel=DocumentChannel.WHATSAPP,
        media_type="text/plain",
        pages=(PageText(1, "positioning 1,200\nsorry positioning 900 not 1,200"),),
        messages=(
            ChatMessage(sequence=0, text="price is 42,500, positioning 1,200"),
            ChatMessage(sequence=1, text="sorry positioning 900 not 1,200"),
        ),
    )
    result = RulesExtractor().extract(doc, CTX)
    amounts = sorted(
        (f.sequence, f.amount.amount_minor if f.amount else None)
        for f in result.fees
        if f.category is FeeCategory.POSITIONING
    )
    assert amounts == [(0, 120_000), (1, 90_000)]


def test_decline_and_revision_intent() -> None:
    assert extract("We are unable to support this trip, no availability.").intent == "decline"
    assert extract("REVISED QUOTE\nCharter price: $38,900").intent == "revision"
    assert extract("Hello there").intent == "other"


def test_scanned_documents_are_unreadable() -> None:
    doc = DocumentInput(
        kind=DocumentKind.PDF,
        channel=DocumentChannel.PDF_UPLOAD,
        media_type="application/pdf",
        pages=(PageText(1, ""),),
        is_scanned=True,
    )
    with pytest.raises(DocumentUnreadable) as info:
        RulesExtractor().extract(doc, CTX)
    assert info.value.reason == "no_text_layer"
    assert not info.value.retryable


def test_result_metadata() -> None:
    result = extract("Charter price: $10,000")
    assert result.extractor == "rules"
    assert result.extractor_version == "rules-1"
    assert result.model is None


def test_all_in_amount_after_an_included_fee_is_the_headline() -> None:
    # Regression (live demo): the pasted Summit revision gave the all-in price to the
    # fuel anchor on its left, storing "fuel surcharge $38,900 (included)" and no headline.
    result = extract(
        "Hi it's Dan at Summit re JS184 KTEB-KOPF 18 Oct. Revised: fuel confirmed included, "
        "38,900 all in, crew overnight 700 extra. Thx",
        DocumentKind.SMS,
    )
    headline = field_value(result, "headline_price")
    assert headline is not None and headline.amount_minor == 3_890_000  # type: ignore[attr-defined]
    assert field_value(result, "all_in") is True
    fuel = fee(result, FeeCategory.FUEL_SURCHARGE)
    assert (fuel.status, fuel.amount) == ("included", None)
    crew = fee(result, FeeCategory.CREW_OVERNIGHT)
    assert crew.status == "stated" and crew.amount is not None
    assert crew.amount.amount_minor == 70_000


def test_fee_amount_followed_by_all_in_stays_a_fee() -> None:
    result = extract("Catering 450 all in.")
    catering = fee(result, FeeCategory.CATERING)
    assert catering.amount is not None and catering.amount.amount_minor == 45_000
    assert field_value(result, "headline_price") is None
