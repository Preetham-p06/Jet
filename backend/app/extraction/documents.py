"""Loading uploads into `DocumentInput` (design spec §1 "Document loading").

* PDF: pypdf text per page; encrypted files get an empty-password decrypt
  attempt; more than `MAX_PDF_PAGES` pages is rejected; fewer than
  `SCANNED_CHARS_PER_PAGE` text characters per page on average marks it scanned.
* `.eml`: stdlib `email`; `text/plain` preferred, HTML stripped otherwise;
  quoted reply text becomes an `is_quoted` message; PDF attachments are
  returned as `Attachment`s and become child source documents.
* WhatsApp exports: split into timestamped messages.
* SMS / pasted text: optional `From:` and `Received:` header lines are honoured.
* Images (PNG, JPEG): accepted only when Claude is configured.

Types are decided by magic bytes, never by the filename or declared type.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Final

from app.config import Settings
from app.extraction.base import DocumentInput
from app.models.enums import DocumentChannel, DocumentKind

PDF_MAGIC: Final = b"%PDF-"
PNG_MAGIC: Final = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC: Final = b"\xff\xd8\xff"
SCANNED_CHARS_PER_PAGE: Final = 40


@dataclass(frozen=True, slots=True)
class Attachment:
    filename: str | None
    media_type: str
    data: bytes


@dataclass(frozen=True, slots=True)
class LoadedDocument:
    input: DocumentInput
    page_count: int | None
    attachments: tuple[Attachment, ...] = ()


def sniff(data: bytes, filename: str | None) -> tuple[DocumentKind, str]:
    """Decide (kind, media_type) from magic bytes; `.eml` and chat text by content.

    Raises `app.errors.Unprocessable` (code `unsupported_type`) otherwise.
    """
    raise NotImplementedError


def load_document(
    *,
    data: bytes | None,
    text: str | None,
    filename: str | None,
    channel: DocumentChannel | None,
    sender: str | None,
    subject: str | None,
    received_at: datetime | None,
    settings: Settings,
) -> LoadedDocument:
    """Validate and load an upload (exactly one of `data` or `text`).

    Raises `PayloadTooLarge` over `MAX_UPLOAD_MB`, `Unprocessable` for bad or
    unsupported content, too many pages, or an image without Claude.
    """
    raise NotImplementedError


def load_pdf(data: bytes, *, max_pages: int) -> LoadedDocument:
    raise NotImplementedError


def load_email(data: bytes) -> LoadedDocument:
    raise NotImplementedError


def load_whatsapp(text: str) -> LoadedDocument:
    raise NotImplementedError


def load_text(
    text: str,
    *,
    channel: DocumentChannel,
    sender: str | None = None,
    received_at: datetime | None = None,
) -> LoadedDocument:
    raise NotImplementedError


def load_image(data: bytes, media_type: str) -> LoadedDocument:
    raise NotImplementedError


def is_scanned(pages_text: list[str]) -> bool:
    """True when the average text per page is below `SCANNED_CHARS_PER_PAGE`."""
    raise NotImplementedError
