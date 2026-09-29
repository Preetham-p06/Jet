"""Extractor selection and the Claude -> rules fallback, tested with fakes."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import anthropic
import httpx2
import pytest

from app.config import Environment, ExtractorChoice, Settings
from app.extraction import registry
from app.extraction.base import (
    DocumentInput,
    DocumentUnreadable,
    ExtractionContext,
    ExtractorConfigError,
    ExtractorError,
    ExtractorInvalidOutput,
    ExtractorRefused,
    ExtractorTruncated,
    ExtractorUnavailable,
    LegContext,
    PageText,
)
from app.extraction.claude.extractor import ClaudeExtractor
from app.extraction.registry import (
    ExtractionAttempt,
    FallbackExtractor,
    error_code,
    run_extractor,
    select_extractor,
)
from app.models.enums import DocumentChannel, DocumentKind
from tests.fakes import FakeExtractor, empty_result


def make_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {"env": Environment.TEST, "anthropic_api_key": None}
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


@pytest.fixture
def rules() -> FakeExtractor:
    return FakeExtractor(name="rules", result=empty_result())


@pytest.fixture(autouse=True)
def fake_rules(monkeypatch: pytest.MonkeyPatch, rules: FakeExtractor) -> None:
    # The real rules extractor is built by another package; the registry imports it lazily.
    monkeypatch.setattr(registry, "_build_rules", lambda: rules)


def doc() -> DocumentInput:
    return DocumentInput(
        kind=DocumentKind.TEXT,
        channel=DocumentChannel.PASTE,
        media_type="text/plain",
        pages=(PageText(1, "Atlas Jets: $41,800 all in"),),
    )


def ctx() -> ExtractionContext:
    return ExtractionContext(legs=(LegContext("KTEB", "KOPF", datetime(2026, 10, 18, 9)),), pax=7)


def claude_fake(**kw: Any) -> FakeExtractor:
    result = empty_result().model_copy(update={"extractor": "claude", "model": "claude-opus-5-5"})
    return FakeExtractor(name="claude", result=result, **kw)


# --- selection -----------------------------------------------------------------------


def test_auto_without_key_uses_rules(rules: FakeExtractor) -> None:
    assert select_extractor(make_settings()) is rules


def test_auto_with_key_uses_claude_with_rules_fallback(rules: FakeExtractor) -> None:
    extractor = select_extractor(make_settings(anthropic_api_key="sk-test"))
    assert isinstance(extractor, FallbackExtractor)
    assert isinstance(extractor.primary, ClaudeExtractor)
    assert isinstance(extractor.primary.client, anthropic.Anthropic)
    assert extractor.secondary is rules


def test_empty_key_counts_as_unset(rules: FakeExtractor) -> None:
    assert select_extractor(make_settings(anthropic_api_key="")) is rules


def test_rules_choice_ignores_key(rules: FakeExtractor) -> None:
    settings = make_settings(extractor=ExtractorChoice.RULES, anthropic_api_key="sk-test")
    assert select_extractor(settings) is rules


def test_claude_choice_without_key_falls_back_to_rules(rules: FakeExtractor) -> None:
    assert select_extractor(make_settings(extractor=ExtractorChoice.CLAUDE)) is rules


def test_claude_choice_with_key(rules: FakeExtractor) -> None:
    settings = make_settings(extractor=ExtractorChoice.CLAUDE, anthropic_api_key="sk-test")
    extractor = select_extractor(settings)
    assert isinstance(extractor, FallbackExtractor)
    assert extractor.secondary is rules


def test_injected_client_is_used() -> None:
    client = object()
    extractor = select_extractor(make_settings(), anthropic_client=client)
    assert isinstance(extractor, FallbackExtractor)
    assert isinstance(extractor.primary, ClaudeExtractor)
    assert extractor.primary.client is client


def test_rules_extractor_is_imported_lazily(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.undo()  # restore the real _build_rules
    from app.extraction.rules.extractor import RulesExtractor

    assert isinstance(select_extractor(make_settings()), RulesExtractor)


# --- fallback ------------------------------------------------------------------------

ALL_ERRORS: list[tuple[ExtractorError, str]] = [
    (ExtractorRefused("no", category="cyber"), "refused:cyber"),
    (ExtractorRefused("no"), "refused"),
    (ExtractorTruncated("cut"), "truncated"),
    (ExtractorInvalidOutput("bad"), "invalid_output"),
    (ExtractorUnavailable("429", retry_after_s=3), "unavailable"),
    (ExtractorConfigError("401"), "config_error"),
    (ExtractorError("generic"), "error"),
]


@pytest.mark.parametrize(("error", "code"), ALL_ERRORS)
def test_every_extractor_error_falls_back_to_rules(
    rules: FakeExtractor, error: ExtractorError, code: str
) -> None:
    primary = claude_fake(error=error)
    attempt = FallbackExtractor(primary, rules).extract_with_report(doc(), ctx())

    assert attempt.used == "rules"
    assert attempt.fallback_error is error
    assert attempt.result.extractor == "rules"
    assert attempt.result.warnings[-1] == f"claude failed ({code}); used rules"
    assert len(primary.calls) == 1
    assert len(rules.calls) == 1
    assert rules.result.warnings == []  # the secondary's own result is not mutated


def test_primary_success_skips_secondary(rules: FakeExtractor) -> None:
    primary = claude_fake()
    attempt = FallbackExtractor(primary, rules).extract_with_report(doc(), ctx())
    assert attempt == ExtractionAttempt(result=primary.result, used="claude")
    assert rules.calls == []


def test_extract_returns_just_the_result(rules: FakeExtractor) -> None:
    fallback = FallbackExtractor(claude_fake(error=ExtractorTruncated()), rules)
    assert fallback.extract(doc(), ctx()).extractor == "rules"


def test_document_unreadable_from_primary_is_not_swallowed(rules: FakeExtractor) -> None:
    primary = claude_fake(error=DocumentUnreadable("scanned"))
    with pytest.raises(DocumentUnreadable):
        FallbackExtractor(primary, rules).extract_with_report(doc(), ctx())
    assert rules.calls == []


def test_document_unreadable_from_rules_is_reraised() -> None:
    rules = FakeExtractor(name="rules", error=DocumentUnreadable("no text layer"))
    primary = claude_fake(error=ExtractorUnavailable("down"))
    with pytest.raises(DocumentUnreadable) as info:
        FallbackExtractor(primary, rules).extract_with_report(doc(), ctx())
    assert info.value.reason == "no_text_layer"


def test_non_extractor_errors_propagate(rules: FakeExtractor) -> None:
    class Boom(FakeExtractor):
        def extract(self, doc: DocumentInput, ctx: ExtractionContext) -> Any:
            raise RuntimeError("bug")

    with pytest.raises(RuntimeError):
        FallbackExtractor(Boom(name="claude"), rules).extract_with_report(doc(), ctx())
    assert rules.calls == []


def test_run_extractor_plain_and_fallback(rules: FakeExtractor) -> None:
    plain = run_extractor(rules, doc(), ctx())
    assert plain.used == "rules"
    assert plain.fallback_error is None

    fallback = FallbackExtractor(claude_fake(error=ExtractorRefused()), rules)
    attempt = run_extractor(fallback, doc(), ctx())
    assert attempt.used == "rules"
    assert isinstance(attempt.fallback_error, ExtractorRefused)


def test_error_code_unreadable() -> None:
    assert error_code(DocumentUnreadable()) == "unreadable"


def test_real_claude_529_falls_back_to_rules(rules: FakeExtractor) -> None:
    """End to end over the real SDK: an overloaded API falls back to rules."""

    def handler(request: httpx2.Request) -> httpx2.Response:
        body = {"type": "error", "error": {"type": "overloaded_error", "message": "busy"}}
        return httpx2.Response(529, json=body)

    client = anthropic.Anthropic(
        api_key="test",
        max_retries=0,
        http_client=anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(handler)),
    )
    extractor = select_extractor(
        make_settings(anthropic_api_key="sk-test", claude_server_fallback=False),
        anthropic_client=client,
    )
    attempt = run_extractor(extractor, doc(), ctx())
    assert attempt.used == "rules"
    assert isinstance(attempt.fallback_error, ExtractorUnavailable)
    assert attempt.result.warnings == ["claude failed (unavailable); used rules"]
