"""Scalar field patterns: tail numbers, seats, pax, Wi-Fi, routes, dates, times,
durations, availability, decline intent and operator names (spec §3.3 step 6)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, time
from typing import Final, Generic, TypeVar

from app.models.enums import AircraftCategory, Availability

TAIL_NUMBER_RE: Final = re.compile(
    r"\bN(?:[1-9]\d{0,4}|[1-9]\d{0,3}[A-HJ-NP-Z]|[1-9]\d{0,2}[A-HJ-NP-Z]{2})\b"
)


T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class Found(Generic[T]):
    value: T
    start: int
    end: int
    confidence: int


# --------------------------------------------------------------------------- tail numbers

TAIL_CONTEXT_RE: Final = re.compile(r"\b(?:tail|reg(?:istration)?|aircraft|a/c|serial)\b", re.I)
TAIL_CONTEXT_CHARS: Final = 40
TAIL_WITH_CONTEXT: Final = 85
TAIL_WITHOUT_CONTEXT: Final = 65


def find_tail_numbers(
    text: str, *, context_spans: tuple[tuple[int, int], ...] = ()
) -> list[Found[str]]:
    """US N-numbers: 85 when "tail", "reg" or "aircraft" (or an aircraft model given
    in `context_spans`) is within 40 characters, 65 otherwise."""
    found: list[Found[str]] = []
    for m in TAIL_NUMBER_RE.finditer(text):
        lo = max(0, m.start() - TAIL_CONTEXT_CHARS)
        window = text[lo : m.end() + TAIL_CONTEXT_CHARS]
        near_model = any(
            m.start() - end <= TAIL_CONTEXT_CHARS and start - m.end() <= TAIL_CONTEXT_CHARS
            for start, end in context_spans
        )
        near = bool(TAIL_CONTEXT_RE.search(window)) or near_model
        confidence = TAIL_WITH_CONTEXT if near else TAIL_WITHOUT_CONTEXT
        found.append(Found(m.group(0), m.start(), m.end(), confidence))
    return found


# --------------------------------------------------------------------------- seats and pax

_SEATS_RES: Final = (
    re.compile(
        r"\b(\d{1,2})\s*(?:-\s*)?(?:passenger\s+|pax\s+|executive\s+|leather\s+)?seats?\b", re.I
    ),
    re.compile(r"\bconfigured\s+(?:for|with)\s+(\d{1,2})\b", re.I),
    re.compile(
        r"\b(\d{1,2})\s*-?\s*(?:passenger|pax|seat)\s+(?:config(?:uration)?|layout|cabin)\b", re.I
    ),
    re.compile(r"\bseats?\s*:\s*(\d{1,2})\b", re.I),
    re.compile(r"\bseating\s*(?:for|:)\s*(\d{1,2})\b", re.I),
)
_PAX_RES: Final = (
    re.compile(r"\b(\d{1,2})\s*(?:pax|passengers|guests)\b(?!\s*seats)", re.I),
    re.compile(r"\b(?:passengers|pax)\s*:\s*(\d{1,2})\b", re.I),
)


def _find_ints(
    patterns: tuple[re.Pattern[str], ...], text: str, confidence: int, *, limit: int
) -> list[Found[int]]:
    found: list[Found[int]] = []
    for pattern in patterns:
        for m in pattern.finditer(text):
            value = int(m.group(1))
            if not 1 <= value <= limit:
                continue
            if any(f.start < m.end() and m.start() < f.end for f in found):
                continue
            found.append(Found(value, m.start(), m.end(), confidence))
    found.sort(key=lambda f: f.start)
    return found


def find_seats(text: str) -> list[Found[int]]:
    return _find_ints(_SEATS_RES, text, 92, limit=30)


def find_pax(text: str) -> list[Found[int]]:
    return _find_ints(_PAX_RES, text, 92, limit=99)


# --------------------------------------------------------------------------- wifi

_WIFI_WORD: Final = r"(?:wi-?fi|internet|connectivity)"
_WIFI_NEGATIVE: Final = (
    re.compile(rf"\bno\s+{_WIFI_WORD}\b", re.I),
    re.compile(rf"\bwithout\s+{_WIFI_WORD}\b", re.I),
    re.compile(
        rf"\b{_WIFI_WORD}\s*:?\s*(?:-\s*)?(?:no\b|none\b|n/a\b|not\s+(?:installed|available|"
        r"fitted|equipped|offered|working)\b|unavailable\b|inop(?:erative)?\b|not\s+on\s*board\b)",
        re.I,
    ),
)
_WIFI_POSITIVE: Final = (
    re.compile(
        rf"\b{_WIFI_WORD}\s*:?\s*(?:yes|on\s*board|available|installed|equipped|included|"
        r"ka-band|ku-band|starlink|gogo|avance|high-speed)\b",
        re.I,
    ),
    re.compile(r"\b(?:gogo(?:\s+avance)?|starlink|ka-band|ku-band)\b", re.I),
    re.compile(rf"\b(?:with|has|have|onboard|on-board)\s+(?:high-speed\s+)?{_WIFI_WORD}\b", re.I),
)
_WIFI_MENTION: Final = re.compile(r"\bwi-?fi\b", re.I)


def find_wifi(text: str) -> list[Found[bool]]:
    """Negations first ("no wifi", "Wi-Fi: not installed"), then positive statements,
    then a bare Wi-Fi mention (weaker)."""
    for pattern in _WIFI_NEGATIVE:
        m = pattern.search(text)
        if m:
            return [Found(False, m.start(), m.end(), 92)]
    for pattern in _WIFI_POSITIVE:
        m = pattern.search(text)
        if m:
            return [Found(True, m.start(), m.end(), 92)]
    m = _WIFI_MENTION.search(text)
    if m:
        return [Found(True, m.start(), m.end(), 80)]
    return []


# --------------------------------------------------------------------------- routes

_NOT_AIRPORTS: Final = frozenset(
    {"FROM", "WITH", "THIS", "THAT", "TBD", "TBC", "FET", "USD", "EUR", "GBP", "CAD", "CHF"}
    | {"AUD", "FBO", "RON", "VAT", "PDF", "ETE", "ETA", "ETD", "REF", "NOTE", "APIS", "CBP"}
    | {"FSC", "PAX", "EST", "UTC", "EDT", "PST", "CST", "SMS", "RFQ", "FAQ", "LLC", "INC"}
)
_ROUTE_RE: Final = re.compile(
    r"(?<![A-Za-z0-9])([A-Z]{4}|[A-Z]{3})\s*(?:-{1,2}>?|→|>|\bto\b)\s*([A-Z]{4}|[A-Z]{3})"
    r"(?![A-Za-z0-9])"
)


def find_route(text: str) -> list[Found[tuple[str, str]]]:
    """`KTEB -> KOPF`, `KTEB-KOPF`, `TEB-OPF`, `KTEB to KOPF` (codes as written)."""
    found: list[Found[tuple[str, str]]] = []
    for m in _ROUTE_RE.finditer(text):
        a, b = m.group(1), m.group(2)
        if a == b or len(a) != len(b) or a in _NOT_AIRPORTS or b in _NOT_AIRPORTS:
            continue
        found.append(Found((a, b), m.start(), m.end(), 92 if len(a) == 4 else 85))
    return found


# --------------------------------------------------------------------------- dates and times

_MONTHS: Final = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}  # fmt: skip
_MONTH: Final = (
    r"(?P<mon>jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|"
    r"sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?"
)
_DATE_RES: Final = (
    re.compile(r"(?<!\d)(?P<y>\d{4})-(?P<m>\d{2})-(?P<d>\d{2})(?!\d)"),
    re.compile(r"(?<![\d/])(?P<m>\d{1,2})/(?P<d>\d{1,2})/(?P<y>\d{4}|\d{2})(?![\d/])"),
    re.compile(
        rf"(?<![\w])(?P<d>\d{{1,2}})(?:st|nd|rd|th)?[\s-]+{_MONTH}(?![a-z])"
        rf"(?:,?[\s-]+(?P<y>\d{{4}}))?",
        re.I,
    ),
    re.compile(
        rf"(?<![\w]){_MONTH}(?![a-z])\s+(?P<d>\d{{1,2}})(?:st|nd|rd|th)?(?![\d:])"
        rf"(?:,?\s+(?P<y>\d{{4}}))?",
        re.I,
    ),
)


def find_dates(text: str, *, default_year: int | None) -> list[Found[date]]:
    found: list[Found[date]] = []
    for pattern in _DATE_RES:
        for m in pattern.finditer(text):
            if any(f.start < m.end() and m.start() < f.end for f in found):
                continue
            groups = m.groupdict()
            mon = groups.get("mon")
            month = _MONTHS[mon[:3].lower()] if mon else int(groups["m"])
            day = int(groups["d"])
            if groups.get("m") and month > 12 and day <= 12:
                month, day = day, month  # day-first numeric date
            year_text = groups.get("y")
            confidence = 92
            if year_text:
                year = int(year_text)
                if year < 100:
                    year += 2000
            elif default_year is not None:
                year = default_year
                confidence = 85
            else:
                continue
            try:
                value = date(year, month, day)
            except ValueError:
                continue
            found.append(Found(value, m.start(), m.end(), confidence))
    found.sort(key=lambda f: f.start)
    return found


_TIME_RES: Final = (
    re.compile(
        r"(?<![\d:.])(?P<h>[01]?\d|2[0-3]):(?P<m>[0-5]\d)(?![\d:])\s*"
        r"(?P<ap>a\.?m\.?|p\.?m\.?)?(?:\s*(?:L\b|LT\b|local\b))?",
        re.I,
    ),
    re.compile(r"(?<![\d:.])(?P<h>1[0-2]|0?[1-9])\s*(?P<ap>a\.?m\.?|p\.?m\.?)(?![a-z])", re.I),
    re.compile(r"(?<![\d:.])(?P<h>[01]\d|2[0-3])(?P<m>[0-5]\d)\s*(?:L|LT|local|hrs)\b"),
)


def find_times(text: str) -> list[Found[time]]:
    found: list[Found[time]] = []
    for pattern in _TIME_RES:
        for m in pattern.finditer(text):
            if any(f.start < m.end() and m.start() < f.end for f in found):
                continue
            groups = m.groupdict()
            hour = int(groups["h"])
            minute = int(groups.get("m") or 0)
            ampm = (groups.get("ap") or "").lower().replace(".", "")
            if ampm == "pm" and hour < 12:
                hour += 12
            elif ampm == "am" and hour == 12:
                hour = 0
            end = m.end()
            while end > m.start() and text[end - 1].isspace():
                end -= 1
            found.append(Found(time(hour, minute), m.start(), end, 90))
    found.sort(key=lambda f: f.start)
    return found


_DURATION_RES: Final = (
    re.compile(
        r"(?<![\d.])(?P<h>\d{1,2})\s*h(?:rs?|ours?)?\.?\s*(?P<m>\d{1,2})\s*m(?:in(?:ute)?s?)?\b\.?",
        re.I,
    ),
    re.compile(r"(?<![\d:.])(?P<h>\d{1,2}):(?P<m>[0-5]\d)(?![\d:])"),
    re.compile(r"(?<![\d.])(?P<dec>\d{1,2}(?:\.\d{1,2})?)\s*(?:hrs?|hours?)\b\.?", re.I),
    re.compile(r"(?<![\d.])(?P<mins>\d{2,3})\s*(?:mins?|minutes)\b\.?", re.I),
)

DURATION_CONTEXT_RE: Final = re.compile(
    r"\b(?:flight\s+time|flying\s+time|flt\s+time|block(?:\s+time)?|ete|en\s*route|duration|"
    r"air\s+time)\b",
    re.I,
)


def find_durations(text: str) -> list[Found[int]]:
    """Durations in minutes: `2h 58m`, `2:58`, `ETE 2:48`, `2.97 hrs`."""
    found: list[Found[int]] = []
    for pattern in _DURATION_RES:
        for m in pattern.finditer(text):
            if any(f.start < m.end() and m.start() < f.end for f in found):
                continue
            groups = m.groupdict()
            if groups.get("dec"):
                minutes = round(float(groups["dec"]) * 60)
            elif groups.get("mins"):
                minutes = int(groups["mins"])
            else:
                minutes = int(groups["h"]) * 60 + int(groups["m"])
            if not 5 <= minutes <= 24 * 60:
                continue
            found.append(Found(minutes, m.start(), m.end(), 92))
    found.sort(key=lambda f: f.start)
    return found


# --------------------------------------------------------------------------- availability

_AVAILABILITY_RES: Final = (
    (
        re.compile(r"\b(?:not\s+available|unavailable|no\s+availability)\b", re.I),
        Availability.UNAVAILABLE,
    ),
    (
        re.compile(
            r"\bsubject\s+to\s+(?:final\s+|aircraft\s+)?(?:availability|confirmation)\b", re.I
        ),
        Availability.SUBJECT_TO,
    ),
    (re.compile(r"\b(?:tentative(?:ly)?|on\s+hold|soft\s+hold)\b", re.I), Availability.TENTATIVE),
    (re.compile(r"\bon\s+request\b", re.I), Availability.ON_REQUEST),
    (re.compile(r"\bconfirmed\b", re.I), Availability.CONFIRMED),
    (re.compile(r"\bavailable\b", re.I), Availability.AVAILABLE),
)


def find_availability(text: str) -> list[Found[Availability]]:
    found: list[Found[Availability]] = []
    for pattern, value in _AVAILABILITY_RES:
        for m in pattern.finditer(text):
            if any(f.start < m.end() and m.start() < f.end for f in found):
                continue
            found.append(Found(value, m.start(), m.end(), 90))
    found.sort(key=lambda f: f.start)
    return found


_DECLINE_RE: Final = re.compile(
    r"\b(?:unable|no\s+availability|declin(?:e|es|ed|ing)|cannot\s+support|can't\s+support|"
    r"can\s+not\s+support|not\s+able\s+to\s+(?:support|quote|operate)|have\s+to\s+pass|"
    r"must\s+pass)\b",
    re.I,
)


def detect_decline(text: str) -> bool:
    return bool(_DECLINE_RE.search(text))


# --------------------------------------------------------------------------- category / hours

_CATEGORY_WORDS: Final = (
    (r"super[\s-]*mid[\s-]*size", AircraftCategory.SUPER_MIDSIZE),
    (r"ultra[\s-]*long[\s-]*range", AircraftCategory.ULTRA_LONG_RANGE),
    (r"very[\s-]*light(?:\s+jet)?", AircraftCategory.VERY_LIGHT),
    (r"mid[\s-]*size(?:\s+jet)?", AircraftCategory.MIDSIZE),
    (r"light(?:\s+jet)?", AircraftCategory.LIGHT),
    (r"heavy(?:\s+jet)?|large[\s-]*cabin(?:\s+jet)?", AircraftCategory.HEAVY),
    (r"turbo[\s-]*prop", AircraftCategory.TURBOPROP),
)
_CATEGORY_LABEL_RE: Final = re.compile(r"\b(?:category|class|size)\s*:\s*$", re.I)


def find_category(text: str) -> Found[AircraftCategory] | None:
    """An explicitly written category: "Category: Midsize" (95), or a list item that is
    only the category ("Super-midsize", "(Heavy)") (92)."""
    for pattern, category in _CATEGORY_WORDS:
        for m in re.finditer(rf"(?<![\w-]){pattern}(?![\w-])", text, re.I):
            if _CATEGORY_LABEL_RE.search(text[: m.start()]):
                return Found(category, m.start(), m.end(), 95)
            rest = (text[: m.start()] + text[m.end() :]).strip(" ()[].,:;-")
            if not rest or rest.lower() in {"jet", "aircraft", "category", "cabin"}:
                return Found(category, m.start(), m.end(), 92)
    return None


_HOURS: Final = r"(\d{1,2}(?:\.\d{1,2})?)\s*(?:hrs?|hours?|h)\b\.?"
_DAILY_MIN_RES: Final = (
    re.compile(rf"{_HOURS}\s*(?:daily|per\s+day|/\s*day|a\s+day)\s+min(?:imum)?\b", re.I),
    re.compile(rf"\b(?:daily|per\s+day)\s+min(?:imum)?\s*(?:of|:)?\s*{_HOURS}", re.I),
    re.compile(rf"\bmin(?:imum)?\s*(?:of\s+)?{_HOURS}\s*(?:daily|per\s+day|/\s*day|a\s+day)", re.I),
)
_BILLABLE_RES: Final = (
    re.compile(r"\bbillable(?:\s+hours)?\s*:?\s*(\d{1,2}(?:\.\d{1,2})?)\b", re.I),
    re.compile(rf"{_HOURS}\s*billable\b", re.I),
)


def find_daily_minimum(text: str) -> Found[float] | None:
    for pattern in _DAILY_MIN_RES:
        m = pattern.search(text)
        if m:
            return Found(float(m.group(1)), m.start(), m.end(), 90)
    return None


def find_billable_hours(text: str) -> Found[float] | None:
    for pattern in _BILLABLE_RES:
        m = pattern.search(text)
        if m:
            return Found(float(m.group(1)), m.start(), m.end(), 90)
    return None


_VALID_UNTIL_RE: Final = re.compile(
    r"\b(?:valid\s+(?:until|through|thru|to|till)|expires?(?:\s+on)?|expiry(?:\s+date)?|"
    r"good\s+(?:until|through))\b",
    re.I,
)


def is_validity_context(text: str) -> bool:
    return bool(_VALID_UNTIL_RE.search(text))


# --------------------------------------------------------------------------- operator name

GENERIC_OPERATOR_TOKENS: Final = frozenset(
    {"air", "aviation", "jets", "jet", "charter", "charters", "executive", "group"}
    | {"the", "inc", "llc", "ltd", "co", "corp", "and"}
)
_COMPANY_TOKENS: Final = frozenset(
    {"air", "aviation", "jets", "jet", "charter", "charters", "executive", "group", "airways"}
    | {"wings", "aero", "aerospace", "flight", "flights", "airlines", "llc", "inc", "ltd"}
    | {"gmbh", "management"}
)
_WORD_RE: Final = re.compile(r"[a-z0-9]+")
_DISPLAY_NAME_RE: Final = re.compile(r'^\s*"?([^"<]+?)"?\s*<[^>]*>\s*$')


def distinctive_tokens(name: str) -> frozenset[str]:
    tokens = frozenset(_WORD_RE.findall(name.lower()))
    return (tokens - GENERIC_OPERATOR_TOKENS) or tokens


def _known_match(text: str, known_names: tuple[str, ...]) -> tuple[str, int, int] | None:
    """The single known operator whose distinctive tokens all appear in `text`."""
    lowered = text.lower()
    hits: list[tuple[str, int, int]] = []
    for name in known_names:
        tokens = distinctive_tokens(name)
        if not tokens:
            continue
        spans = [re.search(rf"(?<![a-z0-9]){re.escape(t)}(?![a-z0-9])", lowered) for t in tokens]
        matched = [sp for sp in spans if sp is not None]
        if len(matched) == len(spans):
            hits.append((name, min(sp.start() for sp in matched), max(sp.end() for sp in matched)))
    return hits[0] if len(hits) == 1 else None


def _company_like(line: str) -> bool:
    words = _WORD_RE.findall(line.lower())
    if not 1 < len(words) <= 6 or any(ch.isdigit() for ch in line) or ":" in line:
        return False
    return any(w in _COMPANY_TOKENS for w in words)


def display_name(sender: str | None) -> str | None:
    """ "Atlas Air Charter <quotes@…>" -> "Atlas Air Charter"; None for bare addresses."""
    if not sender:
        return None
    m = _DISPLAY_NAME_RE.match(sender)
    name = m.group(1).strip() if m else sender.strip()
    if "@" in name or not re.search(r"[A-Za-z]{2}", name):
        return None
    return name


def _line_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    pos = 0
    for raw in text.split("\n"):
        if raw.strip():
            lead = len(raw) - len(raw.lstrip())
            spans.append((pos + lead, pos + len(raw.rstrip())))
        pos += len(raw) + 1
    return spans


def _scan_lines(
    text: str,
    spans: list[tuple[int, int]],
    known_names: tuple[str, ...],
    known_conf: int,
    line_conf: int,
) -> Found[str] | None:
    for start, end in spans:
        known = _known_match(text[start:end], known_names)
        if known:
            return Found(known[0], start + known[1], start + known[2], known_conf)
    for start, end in spans:
        for piece in re.finditer(r"[^|,·•]+", text[start:end]):
            raw = piece.group(0)
            part = raw.strip()
            if _company_like(part):
                offset = start + piece.start() + (len(raw) - len(raw.lstrip()))
                return Found(part, offset, offset + len(part), line_conf)
    return None


def find_operator_name(
    text: str, *, sender: str | None, known_names: tuple[str, ...]
) -> Found[str] | None:
    """Sender display name, then the first five lines, then signature lines, then a
    unique distinctive-token match anywhere. A sender-derived result has
    `start == end == -1` because the name is not in `text`."""
    name = display_name(sender)
    if name:
        known = _known_match(name, known_names)
        if known:
            return Found(known[0], -1, -1, 95)
        if _company_like(name):
            return Found(name, -1, -1, 88)
    spans = _line_spans(text)
    found = _scan_lines(text, spans[:5], known_names, 92, 80)
    if found is None:
        found = _scan_lines(text, spans[-8:], known_names, 90, 75)
    if found is None:
        known = _known_match(text, known_names)
        if known:
            found = Found(known[0], known[1], known[2], 80)
    return found
