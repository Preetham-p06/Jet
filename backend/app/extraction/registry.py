"""Choosing an extractor, and falling back to rules when Claude fails (spec §3.2).

`EXTRACTOR=auto` uses Claude when `ANTHROPIC_API_KEY` is set, otherwise rules.
Any `ExtractorError` from the primary (refusal, truncation after the streaming
retry, invalid output, unavailable, config error) falls back to the secondary
for that document, and the attempt reports the error so the pipeline can log a
processing event. `DocumentUnreadable` from rules is re-raised: the pipeline
marks the document `needs_manual`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.config import Settings
from app.extraction.base import DocumentInput, ExtractionContext, Extractor, ExtractorError
from app.extraction.types import ExtractionResult


@dataclass(frozen=True, slots=True)
class ExtractionAttempt:
    result: ExtractionResult
    used: str  # name of the extractor that produced `result`
    fallback_error: ExtractorError | None = None  # primary's failure, if any


class FallbackExtractor:
    """`primary`, then `secondary` on any `ExtractorError` except `DocumentUnreadable`."""

    name = "fallback"

    def __init__(self, primary: Extractor, secondary: Extractor) -> None:
        self.primary = primary
        self.secondary = secondary

    def extract(self, doc: DocumentInput, ctx: ExtractionContext) -> ExtractionResult:
        return self.extract_with_report(doc, ctx).result

    def extract_with_report(self, doc: DocumentInput, ctx: ExtractionContext) -> ExtractionAttempt:
        raise NotImplementedError


def select_extractor(settings: Settings, *, anthropic_client: Any | None = None) -> Extractor:
    """Build the configured extractor: rules, Claude, or Claude with rules fallback."""
    raise NotImplementedError


def run_extractor(
    extractor: Extractor, doc: DocumentInput, ctx: ExtractionContext
) -> ExtractionAttempt:
    """Uniform entry point for the pipeline, whatever `extractor` is."""
    raise NotImplementedError
