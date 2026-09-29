"""Claude extractor using the anthropic 1.x SDK.

Error mapping, caught in this order (spec §3.2): refusal -> `ExtractorRefused`
(with `stop_details.category`); max_tokens -> one streaming retry at 64k then
`ExtractorTruncated`; output that does not fit the wire schema ->
`ExtractorInvalidOutput`; `RateLimitError`, 5xx, `APIConnectionError` ->
`ExtractorUnavailable`; other 4xx -> `ExtractorConfigError`. Never sends
`thinking`, `temperature` or a forced `tool_choice`.

Why `create` + `output_config.format` instead of `parse(output_format=...)`:
in anthropic 1.9 the `parse` post-parser runs `validate_json` on the text
before the caller can see `stop_reason`, so a `max_tokens` cut or a refusal
with text raises a bare `pydantic.ValidationError` and the stop reason is
lost. We send the identical schema the SDK would generate (`wire_json_schema`,
merged with `effort` in `output_config`), check `stop_reason` first, and only
then validate the text against `ClaudeQuoteExtraction`.
"""

from __future__ import annotations

import inspect
import logging
from typing import Any, Final

import anthropic

from app.config import Settings
from app.extraction.base import (
    DocumentInput,
    ExtractionContext,
    ExtractorConfigError,
    ExtractorInvalidOutput,
    ExtractorRefused,
    ExtractorTruncated,
    ExtractorUnavailable,
)
from app.extraction.claude.prompt import extractor_version, system_blocks, user_content_blocks
from app.extraction.claude.wire import output_format_param, parse_wire, to_extraction_result
from app.extraction.types import ExtractionResult

logger = logging.getLogger("app.extraction.claude")

SERVER_FALLBACK_BETA: Final = "server-side-fallback-2026-07-01"
STREAMING_RETRY_MAX_TOKENS: Final = 64000
_USAGE_KEYS: Final = (
    "input_tokens",
    "output_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
)


def supports_server_fallback(client: Any) -> bool:
    """True when `client.beta.messages.create` and `.stream` accept `betas` and `fallbacks`."""
    messages = getattr(getattr(client, "beta", None), "messages", None)
    for method in ("create", "stream"):
        func = getattr(messages, method, None)
        if func is None:
            return False
        try:
            params = inspect.signature(func).parameters
        except (TypeError, ValueError):
            return False
        has_var_kw = any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values())
        if not has_var_kw and not {"betas", "fallbacks"} <= params.keys():
            return False
    return True


def _retry_after(err: anthropic.APIStatusError) -> float | None:
    raw = err.response.headers.get("retry-after")
    try:
        return float(raw) if raw is not None else None
    except ValueError:
        return None


def _usage_dict(resp: Any) -> dict[str, int]:
    usage = getattr(resp, "usage", None)
    return {key: int(getattr(usage, key, None) or 0) for key in _USAGE_KEYS}


def _add_usage(total: dict[str, int], more: dict[str, int]) -> dict[str, int]:
    return {key: total.get(key, 0) + more.get(key, 0) for key in _USAGE_KEYS}


def _response_text(resp: Any) -> str:
    return "".join(
        getattr(block, "text", "") or ""
        for block in getattr(resp, "content", None) or []
        if getattr(block, "type", None) == "text"
    )


def _fallback_served(resp: Any, requested_model: str) -> str | None:
    """The model that actually answered, when a server-side fallback ran."""
    served = getattr(resp, "model", None)
    iterations = getattr(getattr(resp, "usage", None), "iterations", None) or []
    ran = any(getattr(it, "type", None) == "fallback_message" for it in iterations)
    if ran or (isinstance(served, str) and served and served != requested_model):
        return served if isinstance(served, str) else None
    return None


class ClaudeExtractor:
    name = "claude"

    def __init__(self, settings: Settings, *, client: Any | None = None) -> None:
        """`client` is an `anthropic.Anthropic` (or a duck-typed fake in tests)."""
        self.settings = settings
        if client is None and settings.anthropic_api_key is not None:
            key = settings.anthropic_api_key.get_secret_value()
            if key:
                client = anthropic.Anthropic(
                    api_key=key,
                    timeout=settings.claude_timeout_s,
                    max_retries=settings.claude_max_retries,
                )
        self.client = client
        self.version = extractor_version()

    @property
    def uses_server_fallback(self) -> bool:
        return self.settings.claude_server_fallback and supports_server_fallback(self.client)

    def build_request(self, doc: DocumentInput, ctx: ExtractionContext) -> dict[str, Any]:
        """Keyword arguments for `messages.create` (without fallback extras)."""
        return {
            "model": self.settings.claude_model,
            "max_tokens": self.settings.claude_max_tokens,
            "system": system_blocks(),
            "messages": [{"role": "user", "content": user_content_blocks(doc, ctx)}],
            "output_config": {
                "effort": self.settings.claude_effort,
                "format": output_format_param(),
            },
        }

    def extract(self, doc: DocumentInput, ctx: ExtractionContext) -> ExtractionResult:
        if self.client is None:
            raise ExtractorConfigError("ANTHROPIC_API_KEY is not configured")
        request = self.build_request(doc, ctx)

        client = self.client
        resp = self._send(client, request, stream=False)
        usage = _usage_dict(resp)
        self._check_refusal(resp)
        if getattr(resp, "stop_reason", None) == "max_tokens":
            logger.info(
                "claude output hit max_tokens=%s; retrying with streaming", request["max_tokens"]
            )
            retry = {**request, "max_tokens": STREAMING_RETRY_MAX_TOKENS}
            resp = self._send(client, retry, stream=True)
            usage = _add_usage(usage, _usage_dict(resp))
            self._check_refusal(resp)
            if getattr(resp, "stop_reason", None) == "max_tokens":
                raise ExtractorTruncated(
                    f"output exceeded {STREAMING_RETRY_MAX_TOKENS} tokens after the streaming retry"
                )

        wire = parse_wire(_response_text(resp))
        if wire is None:
            raise ExtractorInvalidOutput("output did not match the ClaudeQuoteExtraction schema")

        logger.info(
            "claude extraction usage input=%d output=%d cache_read=%d cache_write=%d",
            usage["input_tokens"],
            usage["output_tokens"],
            usage["cache_read_input_tokens"],
            usage["cache_creation_input_tokens"],
        )
        requested = self.settings.claude_model
        served = _fallback_served(resp, requested)
        result = to_extraction_result(
            wire,
            extractor_version=self.version,
            model=served or requested,
            default_currency=ctx.base_currency,
            usage=usage,
        )
        if served:
            result.warnings.append(
                f"claude: served by fallback model {served} (requested {requested})"
            )
        return result

    # --- transport -------------------------------------------------------------------

    def _send(self, client: Any, request: dict[str, Any], *, stream: bool) -> Any:
        if self.uses_server_fallback:
            messages: Any = client.beta.messages
            extra: dict[str, Any] = {"betas": [SERVER_FALLBACK_BETA], "fallbacks": "default"}
        else:
            messages = client.messages
            extra = {}
        try:
            if stream:
                with messages.stream(**request, **extra) as live:
                    return live.get_final_message()
            return messages.create(**request, **extra)
        except anthropic.RateLimitError as err:
            raise ExtractorUnavailable(
                f"rate limited: {err.message}", retry_after_s=_retry_after(err)
            ) from err
        except anthropic.APIStatusError as err:
            if err.status_code >= 500:
                raise ExtractorUnavailable(f"API error {err.status_code}: {err.message}") from err
            logger.error("claude request rejected with %s: %s", err.status_code, err.message)
            raise ExtractorConfigError(f"API error {err.status_code}: {err.message}") from err
        except anthropic.APIConnectionError as err:
            raise ExtractorUnavailable(f"connection error: {err}") from err

    @staticmethod
    def _check_refusal(resp: Any) -> None:
        if getattr(resp, "stop_reason", None) != "refusal":
            return
        details = getattr(resp, "stop_details", None)
        category = getattr(details, "category", None) if details is not None else None
        logger.warning("claude refused the document (category=%s)", category)
        raise ExtractorRefused(f"model refused (category={category})", category=category)
