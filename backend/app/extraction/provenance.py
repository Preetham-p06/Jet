"""Checking extractor snippets against the text layer (design spec §3.4).

* Snippets are matched after whitespace and case normalization.
* Found on the claimed page: `verified=True`.
* Found on another page: the page is corrected and the snippet verified.
* Not found while a text layer exists: confidence -15, stays unverified
  (recompute raises the info flag `snippet_unverified`).
* Scanned documents (no text layer): confidence is capped at 90.

Matching also applies NFKC and drops `>` quote markers at line starts, so a
snippet taken from a quoted email line still matches the stored body.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from typing import Final

from app.extraction.base import DocumentInput, PageText
from app.extraction.types import Evidence, ExtractedFee, ExtractedField, ExtractionResult
from app.models.enums import DocumentKind

UNVERIFIED_PENALTY: Final = 15
SCANNED_CONFIDENCE_CAP: Final = 90


@dataclass(frozen=True, slots=True)
class SnippetLocation:
    page: int | None
    char_start: int
    char_end: int


@dataclass(slots=True)
class ProvenanceReport:
    verified: int = 0
    pages_corrected: int = 0
    unverified: list[str] = field(default_factory=list)  # field keys / fee categories


def _normalize_with_map(text: str) -> tuple[str, list[int]]:
    """Normalized text plus, for each normalized char, the index of its source char."""
    out: list[str] = []
    index_map: list[int] = []
    at_line_start = True
    pending_space = False
    for i, ch in enumerate(text):
        if ch == "\n":
            at_line_start = True
            pending_space = bool(out)
            continue
        if at_line_start and ch in "> \t":
            continue  # quote markers and indentation at the start of a line
        at_line_start = False
        if ch.isspace():
            pending_space = bool(out)
            continue
        if pending_space:
            out.append(" ")
            index_map.append(i)
            pending_space = False
        for norm in unicodedata.normalize("NFKC", ch).casefold():
            if norm.isspace():
                if out and out[-1] != " ":
                    out.append(" ")
                    index_map.append(i)
                continue
            out.append(norm)
            index_map.append(i)
    return "".join(out), index_map


def normalize_for_match(text: str) -> str:
    """Collapse whitespace and casefold, keeping a mapping-friendly form."""
    return _normalize_with_map(text)[0]


def _find(snippet_norm: str, page: PageText) -> SnippetLocation | None:
    norm, index_map = _normalize_with_map(page.text)
    pos = norm.find(snippet_norm)
    if pos < 0:
        return None
    start = index_map[pos]
    end = index_map[pos + len(snippet_norm) - 1] + 1
    return SnippetLocation(page=page.page, char_start=start, char_end=end)


def locate(
    snippet: str, pages: tuple[PageText, ...], *, hint_page: int | None
) -> SnippetLocation | None:
    """Find a snippet, trying `hint_page` first; char offsets index the page text."""
    snippet_norm = normalize_for_match(snippet)
    if not snippet_norm:
        return None
    ordered = sorted(pages, key=lambda p: (p.page != hint_page, p.page))
    for page in ordered:
        found = _find(snippet_norm, page)
        if found is not None:
            return found
    return None


def _check(
    evidence: Evidence, confidence: int, doc: DocumentInput, report: ProvenanceReport, label: str
) -> tuple[Evidence, int]:
    has_text = doc.has_text_layer and not doc.is_scanned
    is_pdf = doc.kind is DocumentKind.PDF
    location = locate(evidence.snippet, doc.pages, hint_page=evidence.page) if doc.pages else None
    if location is not None:
        page = location.page if is_pdf else None
        if is_pdf and evidence.page is not None and page != evidence.page:
            report.pages_corrected += 1
        report.verified += 1
        evidence = evidence.model_copy(
            update={
                "verified": True,
                "page": page,
                "char_start": location.char_start,
                "char_end": location.char_end,
            }
        )
    elif has_text:
        report.unverified.append(label)
        confidence = max(0, confidence - UNVERIFIED_PENALTY)
        evidence = evidence.model_copy(update={"verified": False})
    if not has_text:
        confidence = min(confidence, SCANNED_CONFIDENCE_CAP)
    return evidence, confidence


def verify(
    result: ExtractionResult, doc: DocumentInput
) -> tuple[ExtractionResult, ProvenanceReport]:
    """Return a copy of `result` with evidence verified, pages fixed and confidence adjusted."""
    report = ProvenanceReport()
    fields: list[ExtractedField] = []
    for item in result.fields:
        evidence, confidence = _check(item.evidence, item.confidence, doc, report, item.key)
        fields.append(item.model_copy(update={"evidence": evidence, "confidence": confidence}))
    fees: list[ExtractedFee] = []
    for fee in result.fees:
        label = f"fee.{fee.category.value}"
        evidence, confidence = _check(fee.evidence, fee.confidence, doc, report, label)
        fees.append(fee.model_copy(update={"evidence": evidence, "confidence": confidence}))
    return result.model_copy(update={"fields": fields, "fees": fees}), report
