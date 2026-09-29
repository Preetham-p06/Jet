"""The rule-based extractor: segment, match lexicon, parse money, assign, score."""

from __future__ import annotations

from typing import Final

from app.extraction.base import DocumentInput, ExtractionContext
from app.extraction.types import ExtractionResult

RULES_VERSION: Final = "rules-1"


class RulesExtractor:
    """Deterministic, offline extractor.

    Raises `DocumentUnreadable` for documents without a text layer (scanned
    PDFs, images). Money assignment: nearest anchor to the left in the clause,
    else the previous clause's last anchor in the same sentence, else the
    nearest anchor to the right within 25 characters.
    """

    name = "rules"
    version = RULES_VERSION

    def extract(self, doc: DocumentInput, ctx: ExtractionContext) -> ExtractionResult:
        raise NotImplementedError
