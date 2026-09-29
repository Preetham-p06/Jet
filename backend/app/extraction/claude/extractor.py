"""Claude extractor using the anthropic 1.x SDK (`messages.parse`).

Error mapping, caught in this order (spec §3.2): refusal -> `ExtractorRefused`
(with `stop_details.category`); max_tokens -> one streaming retry at 64k then
`ExtractorTruncated`; `parsed_output is None` -> `ExtractorInvalidOutput`;
`RateLimitError`, 5xx, `APIConnectionError` -> `ExtractorUnavailable`; other
4xx -> `ExtractorConfigError`. Never sends `thinking`, `temperature` or a
forced `tool_choice`.
"""

from __future__ import annotations

from typing import Any

from app.config import Settings
from app.extraction.base import DocumentInput, ExtractionContext
from app.extraction.types import ExtractionResult


class ClaudeExtractor:
    name = "claude"

    def __init__(self, settings: Settings, *, client: Any | None = None) -> None:
        """`client` is an `anthropic.Anthropic` (or a duck-typed fake in tests)."""
        self.settings = settings
        self.client = client

    def extract(self, doc: DocumentInput, ctx: ExtractionContext) -> ExtractionResult:
        raise NotImplementedError
