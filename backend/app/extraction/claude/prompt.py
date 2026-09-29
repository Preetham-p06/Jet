"""System prompt and request content blocks.

The system prompt is byte-stable (no dates, sorted vocabulary) so prompt
caching hits; per-document context goes in the trailing user text block.
Document content is untrusted data, never instructions.
"""

from __future__ import annotations

from typing import Any

from app.extraction.base import DocumentInput, ExtractionContext


def system_prompt() -> str:
    raise NotImplementedError


def user_content_blocks(doc: DocumentInput, ctx: ExtractionContext) -> list[dict[str, Any]]:
    """Document/image block(s) first, then one text block with the trip context."""
    raise NotImplementedError


def extractor_version() -> str:
    """Hash of the system prompt plus the wire JSON schema."""
    raise NotImplementedError
