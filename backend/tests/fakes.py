"""Test doubles."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from app.extraction.base import DocumentInput, ExtractionContext, ExtractorError
from app.extraction.types import (
    Evidence,
    ExtractedFee,
    ExtractedField,
    ExtractionResult,
    Money,
)
from app.models.enums import FeeCategory

ResultFactory = Callable[[DocumentInput, ExtractionContext], ExtractionResult]


def empty_result(intent: str = "quote") -> ExtractionResult:
    return ExtractionResult(
        extractor="rules", extractor_version="fake-1", intent=intent, fields=[], fees=[]
    )


def scalar(
    key: str, value: object, confidence: int = 90, snippet: str | None = None
) -> ExtractedField:
    return ExtractedField.model_validate(
        {
            "key": key,
            "value": value,
            "confidence": confidence,
            "evidence": {"snippet": snippet or f"{key}: {value}"},
        }
    )


def fee(
    category: FeeCategory,
    status: str,
    amount_usd: int | None = None,
    *,
    confidence: int = 90,
    label: str | None = None,
    **kw: object,
) -> ExtractedFee:
    return ExtractedFee.model_validate(
        {
            "category": category,
            "label": label or category.value.replace("_", " "),
            "status": status,
            "amount": Money(amount_minor=amount_usd * 100, currency="USD")
            if amount_usd is not None
            else None,
            "confidence": confidence,
            "evidence": Evidence(snippet=label or category.value),
            **kw,
        }
    )


@dataclass
class FakeExtractor:
    """Returns a canned result (or the result of `factory`), or raises `error`.

    Records every call so tests can assert on the documents and context seen.
    """

    result: ExtractionResult = field(default_factory=empty_result)
    factory: ResultFactory | None = None
    error: ExtractorError | None = None
    name: str = "rules"
    calls: list[tuple[DocumentInput, ExtractionContext]] = field(default_factory=list)

    def extract(self, doc: DocumentInput, ctx: ExtractionContext) -> ExtractionResult:
        self.calls.append((doc, ctx))
        if self.error is not None:
            raise self.error
        if self.factory is not None:
            return self.factory(doc, ctx)
        return self.result
