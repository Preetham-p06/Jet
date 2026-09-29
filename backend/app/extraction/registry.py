"""Choosing an extractor, and falling back to rules when Claude fails (spec §3.2).

`EXTRACTOR=auto` uses Claude when `ANTHROPIC_API_KEY` is set, otherwise rules.
Any `ExtractorError` from the primary (refusal, truncation after the streaming
retry, invalid output, unavailable, config error) falls back to the secondary
for that document, and the attempt reports the error so the pipeline can log a
processing event. `DocumentUnreadable` from rules is re-raised: the pipeline
marks the document `needs_manual`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.config import ExtractorChoice, Settings
from app.extraction.base import (
    DocumentInput,
    DocumentUnreadable,
    ExtractionContext,
    Extractor,
    ExtractorConfigError,
    ExtractorError,
    ExtractorInvalidOutput,
    ExtractorRefused,
    ExtractorTruncated,
    ExtractorUnavailable,
)
from app.extraction.types import ExtractionResult

logger = logging.getLogger("app.extraction.registry")

_ERROR_CODES: tuple[tuple[type[ExtractorError], str], ...] = (
    (ExtractorRefused, "refused"),
    (ExtractorTruncated, "truncated"),
    (ExtractorInvalidOutput, "invalid_output"),
    (ExtractorUnavailable, "unavailable"),
    (ExtractorConfigError, "config_error"),
    (DocumentUnreadable, "unreadable"),
)


def error_code(err: ExtractorError) -> str:
    """A short, stable code for an extractor failure (for events and warnings)."""
    for cls, code in _ERROR_CODES:
        if isinstance(err, cls):
            if isinstance(err, ExtractorRefused) and err.category:
                return f"{code}:{err.category}"
            return code
    return "error"


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
        try:
            return ExtractionAttempt(result=self.primary.extract(doc, ctx), used=self.primary.name)
        except DocumentUnreadable:
            raise
        except ExtractorError as err:
            code = error_code(err)
            log = logger.error if isinstance(err, ExtractorConfigError) else logger.warning
            log(
                "extractor %s failed (%s: %s); falling back to %s",
                self.primary.name,
                code,
                err,
                self.secondary.name,
            )
            result = self.secondary.extract(doc, ctx)
            note = f"{self.primary.name} failed ({code}); used {self.secondary.name}"
            result = result.model_copy(update={"warnings": [*result.warnings, note]})
            return ExtractionAttempt(result=result, used=self.secondary.name, fallback_error=err)


def _build_rules() -> Extractor:
    # Imported lazily: the rules package is built separately and may be heavy to load.
    from app.extraction.rules.extractor import RulesExtractor

    return RulesExtractor()


def _build_claude(settings: Settings, client: Any | None) -> Extractor:
    from app.extraction.claude.extractor import ClaudeExtractor

    return ClaudeExtractor(settings, client=client)


def select_extractor(settings: Settings, *, anthropic_client: Any | None = None) -> Extractor:
    """Build the configured extractor: rules, Claude, or Claude with rules fallback.

    `auto` and `claude` use Claude when an API key is set (or a client is
    injected); `claude` without a key logs an error and uses rules.
    """
    rules = _build_rules()
    if settings.extractor is ExtractorChoice.RULES:
        return rules
    if not settings.claude_enabled and anthropic_client is None:
        if settings.extractor is ExtractorChoice.CLAUDE:
            logger.error("EXTRACTOR=claude but ANTHROPIC_API_KEY is not set; using rules")
        return rules
    return FallbackExtractor(_build_claude(settings, anthropic_client), rules)


def run_extractor(
    extractor: Extractor, doc: DocumentInput, ctx: ExtractionContext
) -> ExtractionAttempt:
    """Uniform entry point for the pipeline, whatever `extractor` is."""
    if isinstance(extractor, FallbackExtractor):
        return extractor.extract_with_report(doc, ctx)
    return ExtractionAttempt(result=extractor.extract(doc, ctx), used=extractor.name)
