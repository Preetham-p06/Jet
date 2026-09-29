"""Extractor protocol, its inputs, and the error hierarchy the pipeline relies on."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, runtime_checkable

from app.extraction.types import ExtractionResult
from app.models.enums import DocumentChannel, DocumentKind


@dataclass(frozen=True, slots=True)
class PageText:
    page: int  # 1-based
    text: str


@dataclass(frozen=True, slots=True)
class ChatMessage:
    """One message of a chat export, or one part of an email body.

    For email, the fresh reply is `is_quoted=False` and older quoted text is
    `is_quoted=True` with a lower `sequence`, so it is processed first and
    superseded by the reply.
    """

    sequence: int
    text: str
    author: str | None = None
    sent_at: datetime | None = None
    is_quoted: bool = False


@dataclass(frozen=True, slots=True)
class DocumentInput:
    """Everything an extractor may read about one source document."""

    kind: DocumentKind
    channel: DocumentChannel
    media_type: str
    pages: tuple[PageText, ...] = ()
    raw_bytes: bytes | None = None  # PDFs and images, for Claude document/image blocks
    is_scanned: bool = False
    sender: str | None = None
    subject: str | None = None
    received_at: datetime | None = None
    messages: tuple[ChatMessage, ...] = ()

    @property
    def has_text_layer(self) -> bool:
        return any(p.text.strip() for p in self.pages)

    @property
    def full_text(self) -> str:
        return "\n\n".join(p.text for p in self.pages)


@dataclass(frozen=True, slots=True)
class LegContext:
    origin_icao: str
    destination_icao: str
    depart_local: datetime  # naive, local to the origin


@dataclass(frozen=True, slots=True)
class ExtractionContext:
    """Trip context that helps an extractor resolve ambiguity (never instructions)."""

    legs: tuple[LegContext, ...]
    pax: int
    known_operator_names: tuple[str, ...] = ()
    base_currency: str = "USD"
    default_year: int | None = None
    trip_reference: str | None = None
    operator_hint: str | None = None  # name of an explicitly chosen operator
    extra: dict[str, str] = field(default_factory=dict)


@runtime_checkable
class Extractor(Protocol):
    """Turns one document into an `ExtractionResult`.

    Implementations raise an `ExtractorError` subclass on failure and must not
    touch the database.
    """

    name: str

    def extract(self, doc: DocumentInput, ctx: ExtractionContext) -> ExtractionResult: ...


class ExtractorError(Exception):
    """Base class. `retryable` says whether the same call may succeed later."""

    retryable: bool = False

    def __init__(self, message: str = "", *, retryable: bool | None = None) -> None:
        super().__init__(message or self.__class__.__name__)
        if retryable is not None:
            self.retryable = retryable


class ExtractorUnavailable(ExtractorError):
    """Rate limited, 5xx, overloaded or unreachable."""

    retryable = True

    def __init__(self, message: str = "", *, retry_after_s: float | None = None) -> None:
        super().__init__(message)
        self.retry_after_s = retry_after_s


class ExtractorConfigError(ExtractorError):
    """A 4xx the caller cannot fix by retrying: bad key, permission, bad request."""


class ExtractorRefused(ExtractorError):
    """The model declined to process the document."""

    def __init__(self, message: str = "", *, category: str | None = None) -> None:
        super().__init__(message)
        self.category = category


class ExtractorTruncated(ExtractorError):
    """The output hit the token limit."""


class ExtractorInvalidOutput(ExtractorError):
    """The output could not be parsed into the wire schema."""


class DocumentUnreadable(ExtractorError):
    """No usable text (for example a scanned PDF without OCR); needs manual entry."""

    def __init__(self, message: str = "", *, reason: str = "no_text_layer") -> None:
        super().__init__(message)
        self.reason = reason
