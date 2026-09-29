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

All page and message texts are passed through `segment.normalize_text`, so the
character offsets the extractors report index the stored text exactly.
"""

from __future__ import annotations

import dataclasses
import email
import email.policy
import io
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import EmailMessage, Message
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from typing import Final

from app.config import Settings
from app.errors import PayloadTooLarge, Unprocessable
from app.extraction.base import ChatMessage, DocumentInput, PageText
from app.extraction.rules.segment import normalize_text
from app.models.enums import DocumentChannel, DocumentKind

PDF_MAGIC: Final = b"%PDF-"
PNG_MAGIC: Final = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC: Final = b"\xff\xd8\xff"
SCANNED_CHARS_PER_PAGE: Final = 40

EMAIL_MEDIA_TYPE: Final = "message/rfc822"
TEXT_MEDIA_TYPE: Final = "text/plain"
PDF_MEDIA_TYPE: Final = "application/pdf"

_EMAIL_HEADERS: Final = frozenset(
    {"from", "to", "cc", "subject", "date", "message-id", "mime-version", "content-type"}
    | {"received", "return-path", "delivered-to", "reply-to", "in-reply-to", "references"}
)
_EMAIL_REQUIRED: Final = frozenset({"mime-version", "message-id", "content-type", "subject", "to"})
_HEADER_LINE: Final = re.compile(r"^([A-Za-z][A-Za-z0-9-]{0,40}):[ \t]*(.*)$")
_TEXT_HEADERS: Final = frozenset({"from", "received", "to", "date", "sent", "subject"})

# "[10/2/26, 14:05:09] Dan: text", "10/2/26, 2:05 PM - Dan: text", "2026-10-02 14:05 - Dan: text"
_WHATSAPP_LINE: Final = re.compile(
    r"^‎?\[?(?P<date>\d{1,4}[/.-]\d{1,2}[/.-]\d{1,4}),?\s+"
    r"(?P<time>\d{1,2}:\d{2}(?::\d{2})?(?:\s?[AaPp]\.?[Mm]\.?)?)\]?\s*(?:-\s*)?"
    r"(?P<author>[^:\n]{1,60}?):\s(?P<text>.*)$"
)
_QUOTE_HEADER: Final = re.compile(
    r"^(?:On\s.{3,200}?wrote:|-{2,}\s*Original Message\s*-{2,}|From:\s.+|Sent from my .+)\s*$",
    re.IGNORECASE,
)


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


# --------------------------------------------------------------------------- sniffing


def _decode_text(data: bytes) -> str | None:
    if b"\x00" in data[:4096]:
        return None
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return None


def _leading_headers(text: str) -> tuple[dict[str, str], int]:
    """Header lines at the top of `text` (lower-cased names) and where the body starts."""
    headers: dict[str, str] = {}
    lines = text.replace("\r\n", "\n").split("\n")
    index = 0
    last: str | None = None
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            break
        if line[:1] in (" ", "\t") and last is not None:
            headers[last] += " " + line.strip()
            index += 1
            continue
        m = _HEADER_LINE.match(line)
        if m is None:
            break
        last = m.group(1).lower()
        headers[last] = m.group(2).strip()
        index += 1
    offset = sum(len(line) + 1 for line in lines[:index])
    return headers, offset


def _looks_like_email(text: str) -> bool:
    headers, _ = _leading_headers(text)
    names = set(headers)
    return (
        "from" in names
        and bool(names & _EMAIL_REQUIRED)
        and names
        <= _EMAIL_HEADERS
        | {
            n
            for n in names
            if n.startswith("x-") or n.startswith("content-") or n.startswith("dkim")
        }
    )


def _looks_like_whatsapp(text: str) -> bool:
    lines = [line for line in text.splitlines() if line.strip()][:20]
    hits = sum(1 for line in lines if _WHATSAPP_LINE.match(line))
    return hits >= 2 or (hits == 1 and len(lines) <= 2)


def sniff(data: bytes, filename: str | None) -> tuple[DocumentKind, str]:
    """Decide (kind, media_type) from magic bytes; `.eml` and chat text by content.

    Raises `app.errors.Unprocessable` (code `unsupported_type`) otherwise.
    """
    head = data[:1024].lstrip(b"\xef\xbb\xbf \t\r\n")
    if head.startswith(PDF_MAGIC):
        return DocumentKind.PDF, PDF_MEDIA_TYPE
    if data.startswith(PNG_MAGIC):
        return DocumentKind.IMAGE, "image/png"
    if data.startswith(JPEG_MAGIC):
        return DocumentKind.IMAGE, "image/jpeg"
    text = _decode_text(data)
    if text is None or not text.strip():
        raise Unprocessable("Unsupported file type", code="unsupported_type")
    if _looks_like_email(text):
        return DocumentKind.EMAIL, EMAIL_MEDIA_TYPE
    if _looks_like_whatsapp(text):
        return DocumentKind.WHATSAPP, TEXT_MEDIA_TYPE
    return DocumentKind.TEXT, TEXT_MEDIA_TYPE


# --------------------------------------------------------------------------- entry point


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
    if (data is None) == (text is None):
        raise Unprocessable("Send exactly one of a file or pasted text", code="invalid_input")
    size = len(data) if data is not None else len((text or "").encode("utf-8"))
    if size > settings.max_upload_bytes:
        raise PayloadTooLarge(f"Uploads are limited to {settings.max_upload_mb} MB")
    if size == 0 or (text is not None and not text.strip()):
        raise Unprocessable("The upload is empty", code="empty_document")

    if data is not None:
        kind, media_type = sniff(data, filename)
        if kind is DocumentKind.PDF:
            loaded = load_pdf(data, max_pages=settings.max_pdf_pages)
        elif kind is DocumentKind.IMAGE:
            if not settings.claude_enabled:
                raise Unprocessable(
                    "Images need the Claude extractor (no OCR is configured)",
                    code="image_requires_claude",
                )
            loaded = load_image(data, media_type)
        elif kind is DocumentKind.EMAIL:
            loaded = load_email(data)
        else:
            decoded = _decode_text(data) or ""
            loaded = _load_plain(decoded, kind, channel)
    else:
        assert text is not None  # noqa: S101 - checked above
        if _looks_like_email(text):
            loaded = load_email(text.encode("utf-8"))
        elif _looks_like_whatsapp(text):
            loaded = load_whatsapp(text)
        else:
            loaded = _load_plain(text, DocumentKind.TEXT, channel)

    doc = loaded.input
    updates: dict[str, object] = {}
    if channel is not None:
        updates["channel"] = channel
        if doc.kind is DocumentKind.TEXT and channel is DocumentChannel.SMS:
            updates["kind"] = DocumentKind.SMS
    if sender:
        updates["sender"] = sender
    if subject:
        updates["subject"] = subject
    if received_at is not None:
        updates["received_at"] = _aware(received_at)
    if updates:
        doc = dataclasses.replace(doc, **updates)  # type: ignore[arg-type]
    return dataclasses.replace(loaded, input=doc)


def _load_plain(text: str, kind: DocumentKind, channel: DocumentChannel | None) -> LoadedDocument:
    if kind is DocumentKind.WHATSAPP:
        return load_whatsapp(text)
    headers, _ = _leading_headers(text)
    inferred = DocumentChannel.SMS if {"from", "received"} & set(headers) else DocumentChannel.PASTE
    return load_text(text, channel=channel or inferred)


# --------------------------------------------------------------------------- PDF


def load_pdf(data: bytes, *, max_pages: int) -> LoadedDocument:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
        if reader.is_encrypted:
            try:
                ok = reader.decrypt("")
            except Exception as exc:  # missing crypto backend, unsupported algorithm
                raise Unprocessable(
                    "The PDF is encrypted and cannot be opened", code="pdf_encrypted"
                ) from exc
            if not ok:
                raise Unprocessable("The PDF is password protected", code="pdf_encrypted")
        page_count = len(reader.pages)
        if page_count == 0:
            raise Unprocessable("The PDF has no pages", code="pdf_unreadable")
        if page_count > max_pages:
            raise Unprocessable(
                f"The PDF has {page_count} pages; the limit is {max_pages}",
                code="too_many_pages",
            )
        texts: list[str] = []
        for page in reader.pages:
            try:
                raw = page.extract_text() or ""
            except Exception:  # a broken content stream on one page
                raw = ""
            texts.append(normalize_text(raw).strip("\n"))
    except Unprocessable:
        raise
    except (PdfReadError, ValueError, KeyError, TypeError, RecursionError) as exc:
        raise Unprocessable("The PDF could not be read", code="pdf_unreadable") from exc

    pages = tuple(PageText(page=i + 1, text=t) for i, t in enumerate(texts))
    doc = DocumentInput(
        kind=DocumentKind.PDF,
        channel=DocumentChannel.PDF_UPLOAD,
        media_type=PDF_MEDIA_TYPE,
        pages=pages,
        raw_bytes=data,
        is_scanned=is_scanned(texts),
    )
    return LoadedDocument(input=doc, page_count=page_count)


def is_scanned(pages_text: list[str]) -> bool:
    """True when the average text per page is below `SCANNED_CHARS_PER_PAGE`."""
    if not pages_text:
        return True
    chars = sum(len("".join(t.split())) for t in pages_text)
    return chars / len(pages_text) < SCANNED_CHARS_PER_PAGE


# --------------------------------------------------------------------------- email


class _HTMLText(HTMLParser):
    _BLOCK: Final = frozenset({"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "table"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style", "head"):
            self._skip += 1
        elif tag in self._BLOCK:
            self.parts.append("\n")
        elif tag == "blockquote":
            self.parts.append("\n> ")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "head"):
            self._skip = max(0, self._skip - 1)
        elif tag in self._BLOCK:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    parser = _HTMLText()
    parser.feed(html)
    parser.close()
    text = "".join(parser.parts)
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n\s*\n\s*\n+", "\n\n", text).strip()


def split_quoted(body: str) -> tuple[str, str]:
    """(fresh reply, older quoted text with `>` markers removed)."""
    lines = body.split("\n")
    for index, line in enumerate(lines):
        stripped = line.strip()
        if _QUOTE_HEADER.match(stripped) and index > 0 or stripped.startswith(">"):
            fresh = "\n".join(lines[:index]).strip()
            quoted_lines = [re.sub(r"^\s*(?:>\s?)+", "", ln) for ln in lines[index:]]
            if _QUOTE_HEADER.match(stripped) and not stripped.startswith(">"):
                quoted_lines = quoted_lines[1:]
            return fresh, "\n".join(quoted_lines).strip()
    return body.strip(), ""


def _part_text(part: Message) -> str:
    if isinstance(part, EmailMessage):
        try:
            content = part.get_content()
        except (LookupError, UnicodeDecodeError, AssertionError):
            content = None
        if isinstance(content, str):
            return content
        if isinstance(content, bytes):
            return _decode_text(content) or ""
    payload = part.get_payload(decode=True)
    if isinstance(payload, bytes):
        return _decode_text(payload) or ""
    return ""


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    try:
        return _aware(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        pass
    try:
        return _aware(parsedate_to_datetime(value))
    except (TypeError, ValueError, IndexError):
        return None


def load_email(data: bytes) -> LoadedDocument:
    try:
        msg = email.message_from_bytes(data, policy=email.policy.default)
    except Exception as exc:
        raise Unprocessable("The email could not be parsed", code="email_unreadable") from exc

    body = ""
    if isinstance(msg, EmailMessage):
        part = msg.get_body(preferencelist=("plain", "html"))
        if part is not None:
            body = _part_text(part)
            if part.get_content_type() == "text/html":
                body = html_to_text(body)
    elif not msg.is_multipart():
        body = _part_text(msg)
    body = normalize_text(body).strip()

    attachments: list[Attachment] = []
    if isinstance(msg, EmailMessage):
        for att in msg.iter_attachments():
            payload = att.get_payload(decode=True)
            if not isinstance(payload, bytes):
                continue
            if payload[:1024].lstrip().startswith(PDF_MAGIC):
                attachments.append(Attachment(att.get_filename(), PDF_MEDIA_TYPE, payload))

    fresh, quoted = split_quoted(body)
    messages: list[ChatMessage] = []
    if quoted:
        messages.append(ChatMessage(sequence=0, text=quoted, is_quoted=True))
    if fresh or not quoted:
        messages.append(ChatMessage(sequence=len(messages), text=fresh))

    sender = str(msg.get("From") or "").strip() or None
    subject = str(msg.get("Subject") or "").strip() or None
    doc = DocumentInput(
        kind=DocumentKind.EMAIL,
        channel=DocumentChannel.EMAIL,
        media_type=EMAIL_MEDIA_TYPE,
        pages=(PageText(page=1, text=body),) if body else (),
        sender=sender,
        subject=subject,
        received_at=_parse_datetime(str(msg.get("Date") or "")),
        messages=tuple(messages),
    )
    return LoadedDocument(input=doc, page_count=None, attachments=tuple(attachments))


# --------------------------------------------------------------------------- chat and text


def _whatsapp_datetime(day: str, clock: str) -> datetime | None:
    parts = [int(p) for p in re.split(r"[/.-]", day)]
    if len(parts) != 3:
        return None
    if parts[0] > 999:
        year, month, dom = parts
    else:
        first, second, year = parts
        if year < 100:
            year += 2000
        # Day-first when unambiguous; otherwise the US month-first export format.
        month, dom = (second, first) if first > 12 else (first, second)
    clock = clock.strip().lower().replace(".", "")
    pm, am = clock.endswith("pm"), clock.endswith("am")
    pieces = [int(p) for p in re.sub(r"\s?[ap]m$", "", clock).split(":")]
    hour, minute = pieces[0], pieces[1]
    second = pieces[2] if len(pieces) > 2 else 0
    if pm and hour < 12:
        hour += 12
    elif am and hour == 12:
        hour = 0
    try:
        return datetime(year, month, dom, hour, minute, second, tzinfo=UTC)
    except ValueError:
        return None


def load_whatsapp(text: str) -> LoadedDocument:
    """Split a WhatsApp export into messages. Timestamps are the phone's wall clock
    and are stored as UTC (the export carries no zone)."""
    body = normalize_text(text).strip()
    messages: list[ChatMessage] = []
    current: dict[str, object] | None = None
    lines: list[str] = []

    def flush() -> None:
        if current is None:
            return
        message_text = "\n".join(lines).strip()
        if message_text and "<Media omitted>" not in message_text:
            messages.append(
                ChatMessage(
                    sequence=len(messages),
                    text=message_text,
                    author=str(current["author"]),
                    sent_at=current["sent_at"],  # type: ignore[arg-type]
                )
            )

    for line in body.split("\n"):
        m = _WHATSAPP_LINE.match(line)
        if m:
            flush()
            current = {
                "author": m.group("author").strip(),
                "sent_at": _whatsapp_datetime(m.group("date"), m.group("time")),
            }
            lines = [m.group("text")]
        elif current is not None:
            lines.append(line)
    flush()
    if not messages:
        return load_text(text, channel=DocumentChannel.WHATSAPP)
    authors = [m.author for m in messages if m.author]
    doc = DocumentInput(
        kind=DocumentKind.WHATSAPP,
        channel=DocumentChannel.WHATSAPP,
        media_type=TEXT_MEDIA_TYPE,
        pages=(PageText(page=1, text=body),),
        sender=authors[0] if authors else None,
        received_at=messages[0].sent_at,
        messages=tuple(messages),
    )
    return LoadedDocument(input=doc, page_count=None)


def load_text(
    text: str,
    *,
    channel: DocumentChannel,
    sender: str | None = None,
    received_at: datetime | None = None,
) -> LoadedDocument:
    """SMS or pasted text. Leading `From:` / `Received:` (also `Date:`, `Sent:`, `To:`)
    lines are read as headers and removed from the body."""
    normalized = normalize_text(text)
    headers, offset = _leading_headers(normalized)
    body = normalized
    if headers and set(headers) <= _TEXT_HEADERS and {"from", "received"} & set(headers):
        body = normalized[offset:]
    else:
        headers = {}
    body = body.strip()
    parsed_received = _parse_datetime(
        headers.get("received") or headers.get("date") or headers.get("sent")
    )
    kind = DocumentKind.SMS if channel is DocumentChannel.SMS else DocumentKind.TEXT
    if channel is DocumentChannel.WHATSAPP:
        kind = DocumentKind.WHATSAPP
    doc = DocumentInput(
        kind=kind,
        channel=channel,
        media_type=TEXT_MEDIA_TYPE,
        pages=(PageText(page=1, text=body),) if body else (),
        sender=sender or headers.get("from") or None,
        subject=headers.get("subject") or None,
        received_at=_aware(received_at) if received_at else parsed_received,
    )
    return LoadedDocument(input=doc, page_count=None)


def load_image(data: bytes, media_type: str) -> LoadedDocument:
    doc = DocumentInput(
        kind=DocumentKind.IMAGE,
        channel=DocumentChannel.OTHER,
        media_type=media_type,
        raw_bytes=data,
        is_scanned=True,
    )
    return LoadedDocument(input=doc, page_count=1)
