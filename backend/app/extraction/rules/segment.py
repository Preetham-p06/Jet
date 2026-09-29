"""NFKC normalization and sentence/clause segmentation with provenance spans.

Abbreviations (`est.`, `approx.`, `incl.`, `excl.`, `e.g.`, `no.`, `hrs.`,
`min.`) are protected before sentence splitting; clauses split at ", "
followed by a letter, so "38,900" stays intact.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.extraction.base import DocumentInput


class LineKind(StrEnum):
    LABELLED = "labelled"  # "Label: value" or dot leaders -> base 92
    PROSE = "prose"  # PDF or email prose -> 88
    INFORMAL = "informal"  # SMS / WhatsApp -> 82
    QUOTED = "quoted"  # older quoted email text -> 70


@dataclass(frozen=True, slots=True)
class Clause:
    text: str
    page: int | None
    char_start: int  # offsets into the page (or message) text
    char_end: int
    sentence_index: int
    clause_index: int
    line_kind: LineKind
    sequence: int = 0  # message order for chats / quoted email


def normalize_text(text: str) -> str:
    """NFKC, non-breaking spaces and dashes normalized, line breaks kept."""
    raise NotImplementedError


def segment(doc: DocumentInput) -> list[Clause]:
    raise NotImplementedError
