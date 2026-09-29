"""Checking extractor snippets against the text layer (design spec §3.4).

* Snippets are matched after whitespace and case normalization.
* Found on the claimed page: `verified=True`.
* Found on another page: the page is corrected and the snippet verified.
* Not found while a text layer exists: confidence -15, stays unverified
  (recompute raises the info flag `snippet_unverified`).
* Scanned documents (no text layer): confidence is capped at 90.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

from app.extraction.base import DocumentInput, PageText
from app.extraction.types import ExtractionResult

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


def normalize_for_match(text: str) -> str:
    """Collapse whitespace and casefold, keeping a mapping-friendly form."""
    raise NotImplementedError


def locate(
    snippet: str, pages: tuple[PageText, ...], *, hint_page: int | None
) -> SnippetLocation | None:
    """Find a snippet, trying `hint_page` first; char offsets index the page text."""
    raise NotImplementedError


def verify(
    result: ExtractionResult, doc: DocumentInput
) -> tuple[ExtractionResult, ProvenanceReport]:
    """Return a copy of `result` with evidence verified, pages fixed and confidence adjusted."""
    raise NotImplementedError
