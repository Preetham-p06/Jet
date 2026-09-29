"""Operator identity: name normalization, matching and stats."""

from __future__ import annotations

import difflib
import re
import statistics
import unicodedata
import uuid
from dataclasses import dataclass
from email.utils import parseaddr
from typing import Final

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.enums import TripOperatorStatus
from app.models.operator import Operator
from app.models.quote import Quote
from app.models.trip import TripOperator
from app.schemas.operator import OperatorStats

#: Words ignored when looking for an operator's distinctive token.
GENERIC_NAME_TOKENS: Final = frozenset(
    {"air", "aviation", "jets", "jet", "charter", "charters", "executive", "group", "inc", "llc"}
)
WEBMAIL_DOMAINS: Final = frozenset(
    {"gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "icloud.com", "aol.com"}
)
_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_ANGLE = re.compile(r"^(.*?)<([^<>]*)>\s*$")
_PHONE = re.compile(r"^\+?[\d\s().-]{7,}$")


def normalize_operator_name(name: str) -> str:
    """Casefolded, accent- and punctuation-free, single-spaced ("Atlas Jets, Inc." ->
    "atlas jets inc"). Used for uniqueness per workspace."""
    folded = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return _NON_ALNUM.sub(" ", folded.casefold()).strip()


def email_domain(email: str | None) -> str | None:
    """Domain of an email address, or None for webmail (useless for matching)."""
    if not email or "@" not in email:
        return None
    domain = email.rsplit("@", 1)[1].strip().lower()
    return None if domain in WEBMAIL_DOMAINS else domain or None


def distinctive_tokens(name: str) -> set[str]:
    return {t for t in normalize_operator_name(name).split() if t not in GENERIC_NAME_TOKENS}


@dataclass(frozen=True, slots=True)
class OperatorMatch:
    operator: Operator
    method: str  # "email", "phone", "domain", "name", "alias", "token", "fuzzy"
    score: float


def match_operator(
    db: Session,
    workspace_id: uuid.UUID,
    *,
    sender: str | None,
    name: str | None,
) -> OperatorMatch | None:
    """Match by exact email or phone, then non-webmail domain, then name
    (normalized, alias, distinctive token, difflib ratio >= 0.88)."""
    operators = list(
        db.scalars(
            select(Operator)
            .where(Operator.workspace_id == workspace_id)
            .order_by(Operator.is_archived, Operator.created_at, Operator.id)
        )
    )
    if not operators:
        return None
    return _match_sender(operators, sender) or _match_name(operators, name)


def parse_sender(sender: str | None) -> tuple[str | None, str | None, str | None]:
    """(display name, email, phone digits) of a sender such as "Atlas <q@atlas.example>"
    or "Dan <+1 (617) 555-0142>"."""
    if not sender or not sender.strip():
        return None, None, None
    text = sender.strip()
    bracket = _ANGLE.match(text)
    label, address = (bracket.group(1), bracket.group(2)) if bracket else ("", text)
    label = label.strip().strip('"').strip() or None
    address = address.strip()
    email: str | None = None
    phone: str | None = None
    if "@" in address:
        parsed = parseaddr(address)[1] or address
        email = parsed.strip().lower() if "@" in parsed else None
    elif _PHONE.match(address):
        digits = _phone_digits(address)
        phone = digits if digits and len(digits) >= _MIN_PHONE_DIGITS else None
    if label is None and email is None and phone is None:
        label = text
    return label, email, phone


def sender_label(sender: str | None) -> str | None:
    """A human name for an unmatched sender: display name, email, phone, or the raw text."""
    label, email, phone = parse_sender(sender)
    if label:
        return label
    if email:
        return email
    if phone:
        return f"+{phone}"
    return None


_MIN_PHONE_DIGITS: Final = 7
_FUZZY_RATIO: Final = 0.88


def _phone_digits(value: str | None) -> str | None:
    if not value:
        return None
    digits = re.sub(r"\D", "", value)
    return digits or None


def _same_phone(a: str, b: str) -> bool:
    # Compare the national part so "+1 617 555 0142" matches "(617) 555-0142".
    return a[-10:] == b[-10:] if min(len(a), len(b)) >= 10 else a == b


def _match_sender(operators: list[Operator], sender: str | None) -> OperatorMatch | None:
    _, email, phone = parse_sender(sender)
    if email:
        for op in operators:
            if op.email and op.email.strip().lower() == email:
                return OperatorMatch(op, "email", 1.0)
    if phone:
        for op in operators:
            op_phone = _phone_digits(op.phone)
            if op_phone and _same_phone(op_phone, phone):
                return OperatorMatch(op, "phone", 1.0)
    domain = email_domain(email)
    if domain:
        hits = [
            op
            for op in operators
            if (op.email_domain or email_domain(op.email) or "").lower() == domain
        ]
        if len(hits) == 1:
            return OperatorMatch(hits[0], "domain", 0.95)
    return None


def _match_name(operators: list[Operator], name: str | None) -> OperatorMatch | None:
    if not name:
        return None
    wanted = normalize_operator_name(name)
    if not wanted:
        return None
    for op in operators:
        if op.normalized_name == wanted:
            return OperatorMatch(op, "name", 1.0)
    for op in operators:
        if any(normalize_operator_name(a) == wanted for a in op.aliases or []):
            return OperatorMatch(op, "alias", 0.98)
    tokens = distinctive_tokens(name)
    if tokens:
        hits = []
        for op in operators:
            op_tokens = distinctive_tokens(op.name)
            if op_tokens and (op_tokens <= tokens or tokens <= op_tokens):
                hits.append(op)
        if len(hits) == 1:
            return OperatorMatch(hits[0], "token", 0.9)
    best: tuple[float, Operator] | None = None
    for op in operators:
        for candidate in (op.normalized_name, *(normalize_operator_name(a) for a in op.aliases)):
            ratio = difflib.SequenceMatcher(None, wanted, candidate).ratio()
            if ratio >= _FUZZY_RATIO and (best is None or ratio > best[0]):
                best = (ratio, op)
    if best is not None:
        return OperatorMatch(best[1], "fuzzy", round(best[0], 3))
    return None


def operator_stats(db: Session, operator: Operator) -> OperatorStats:
    """Quote count, RFQ outcomes and median response time for one operator."""
    quote_count = db.scalar(
        select(func.count()).select_from(Quote).where(Quote.operator_id == operator.id)
    )
    rows = db.scalars(select(TripOperator).where(TripOperator.operator_id == operator.id)).all()
    hours = [
        (r.responded_at - r.requested_at).total_seconds() / 3600
        for r in rows
        if r.responded_at is not None and r.status is TripOperatorStatus.QUOTED
    ]
    return OperatorStats(
        quote_count=quote_count or 0,
        trips_requested=len(rows),
        trips_quoted=sum(r.status is TripOperatorStatus.QUOTED for r in rows),
        trips_declined=sum(r.status is TripOperatorStatus.DECLINED for r in rows),
        median_response_hours=round(statistics.median(hours), 2) if hours else None,
    )
