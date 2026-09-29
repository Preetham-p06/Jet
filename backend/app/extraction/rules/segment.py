"""NFKC normalization and sentence/clause segmentation with provenance spans.

Abbreviations (`est.`, `approx.`, `incl.`, `excl.`, `e.g.`, `no.`, `hrs.`,
`min.`) are protected before sentence splitting; clauses split at ", "
followed by a letter, so "38,900" stays intact.

Units are PDF pages, or chat / email messages when `doc.messages` is set.
PDF lines are always separate blocks; in text sources consecutive plain lines
of one paragraph are joined so wrapped sentences stay whole. Within a block,
sentences also split at " · ", " | " and " / " after a number (a common way of
listing charges on one line).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from app.extraction.base import DocumentInput
from app.models.enums import DocumentChannel, DocumentKind


class LineKind(StrEnum):
    LABELLED = "labelled"  # "Label: value" or dot leaders -> base 92
    PROSE = "prose"  # PDF or email prose -> 88
    INFORMAL = "informal"  # SMS / WhatsApp -> 82
    QUOTED = "quoted"  # older quoted email text -> 70


@dataclass(frozen=True, slots=True)
class Clause:
    text: str
    page: int | None
    char_start: int  # offsets into the page (or message) text
    char_end: int
    sentence_index: int
    clause_index: int
    line_kind: LineKind
    sequence: int = 0  # message order for chats / quoted email


_SPACES: Final = re.compile(r"[    -  -  　\t]")
_DASHES: Final = re.compile(r"[‐-―−﹘﹣－]")
_ZERO_WIDTH: Final = re.compile(r"[​‌‍﻿]")

PROTECTED_ABBREVIATIONS: Final = frozenset(
    {"est", "approx", "incl", "excl", "e.g", "i.e", "eg", "ie", "no", "hrs", "hr", "min", "vs"}
    | {"ca", "mr", "mrs", "ms", "dr", "st", "approx", "nos", "tel", "ref"}
)

_SENTENCE_END: Final = re.compile(r"(?<![.])[.!?](?![.])[\"')\]]*\s+")
_LIST_SEPARATOR: Final = re.compile(r"\s+[·•|]\s+|(?<=\d)\s+/\s+(?=[A-Za-z])")
_CLAUSE_SEPARATOR: Final = re.compile(r",\s+(?=[A-Za-z~$€£])|;\s+")
_LABELLED: Final = re.compile(r"^\s*[A-Za-z][^:\n]{0,40}:\s+\S")
_DOT_LEADER: Final = re.compile(r"\.{4,}|…|_{4,}")
_BULLET_LINE: Final = re.compile(r"^\s*(?:[-*•·]\s+|\d+[.)]\s+)")
_WORD_BEFORE: Final = re.compile(r"([A-Za-z][A-Za-z.]*)$")
_CONTINUATION: Final = re.compile(r"^\s*[a-z0-9$€£~(]")
_JOIN_ENDINGS: Final = (",", "-", " and", " or", " the", " a", " of", " for", " to", " is")

_INFORMAL_KINDS: Final = frozenset({DocumentKind.SMS, DocumentKind.WHATSAPP})
_INFORMAL_CHANNELS: Final = frozenset({DocumentChannel.SMS, DocumentChannel.WHATSAPP})


def normalize_text(text: str) -> str:
    """NFKC, non-breaking spaces and dashes normalized, line breaks kept."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _ZERO_WIDTH.sub("", text)
    text = unicodedata.normalize("NFKC", text)
    text = _SPACES.sub(" ", text)
    return _DASHES.sub("-", text)


def is_labelled(text: str) -> bool:
    return bool(_LABELLED.match(text) or _DOT_LEADER.search(text))


def _blocks(text: str, *, pdf: bool) -> Iterator[tuple[int, int]]:
    """Spans of lines (PDF) or joined paragraph lines (text sources)."""
    pos = 0
    lines: list[tuple[int, int]] = []
    for raw in text.split("\n"):
        lines.append((pos, pos + len(raw)))
        pos += len(raw) + 1

    current: tuple[int, int] | None = None
    for start, end in lines:
        line = text[start:end]
        if not line.strip():
            if current is not None:
                yield current
                current = None
            continue
        standalone = pdf or is_labelled(line) or bool(_BULLET_LINE.match(line))
        if current is not None and not standalone:
            # A wrapped line continues the previous one; a capitalized line after a
            # complete one ("Catering: TBD" / "Landing fees incl.") starts anew.
            previous = text[current[0] : current[1]].rstrip()
            continues = bool(_CONTINUATION.match(line)) or previous.endswith(_JOIN_ENDINGS)
            if not continues:
                yield current
                current = None
        if standalone:
            if current is not None:
                yield current
                current = None
            yield (start, end)
        elif current is None:
            current = (start, end)
        else:
            current = (current[0], end)
    if current is not None:
        yield current


def _split(
    text: str, start: int, end: int, pattern: re.Pattern[str], *, protect: bool = False
) -> list[tuple[int, int]]:
    """Split `text[start:end]` at `pattern`; the separator is dropped (except the
    sentence-final punctuation, which stays with its sentence)."""
    parts: list[tuple[int, int]] = []
    cursor = start
    for m in pattern.finditer(text, start, end):
        if protect:
            word = _WORD_BEFORE.search(text, cursor, m.start())
            if word is not None and word.group(1).lower().rstrip(".") in PROTECTED_ABBREVIATIONS:
                continue
            # A single capital letter before the dot is an initial ("J. Smith").
            if word is not None and len(word.group(1)) == 1 and word.group(1).isupper():
                continue
            cut = m.start() + len(m.group(0).rstrip())
            parts.append((cursor, cut))
        else:
            parts.append((cursor, m.start()))
        cursor = m.end()
    parts.append((cursor, end))
    return [_trim(text, s, e) for s, e in parts if text[s:e].strip()]


def _trim(text: str, start: int, end: int) -> tuple[int, int]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


def _units(doc: DocumentInput) -> Iterator[tuple[str, int | None, int, bool]]:
    """(text, page, sequence, is_quoted) for every unit of the document."""
    if doc.messages:
        for msg in sorted(doc.messages, key=lambda m: m.sequence):
            yield msg.text, None, msg.sequence, msg.is_quoted
        return
    is_pdf = doc.kind is DocumentKind.PDF
    for page in doc.pages:
        yield page.text, page.page if is_pdf else None, 0, False


def segment(doc: DocumentInput) -> list[Clause]:
    informal = doc.kind in _INFORMAL_KINDS or doc.channel in _INFORMAL_CHANNELS
    is_pdf = doc.kind is DocumentKind.PDF
    clauses: list[Clause] = []
    sentence_index = 0
    for raw_text, page, sequence, quoted in _units(doc):
        text = normalize_text(raw_text)
        for b_start, b_end in _blocks(text, pdf=is_pdf):
            for s_start, s_end in _split(text, b_start, b_end, _SENTENCE_END, protect=True):
                for l_start, l_end in _split(text, s_start, s_end, _LIST_SEPARATOR):
                    sentence = text[l_start:l_end]
                    if quoted:
                        kind = LineKind.QUOTED
                    elif informal:
                        kind = LineKind.INFORMAL
                    elif is_labelled(sentence):
                        kind = LineKind.LABELLED
                    else:
                        kind = LineKind.PROSE
                    pieces = _split(text, l_start, l_end, _CLAUSE_SEPARATOR)
                    for clause_index, (c_start, c_end) in enumerate(pieces):
                        clauses.append(
                            Clause(
                                text=text[c_start:c_end],
                                page=page,
                                char_start=c_start,
                                char_end=c_end,
                                sentence_index=sentence_index,
                                clause_index=clause_index,
                                line_kind=kind,
                                sequence=sequence,
                            )
                        )
                    sentence_index += 1
    return clauses
