"""Operator identity: name normalization, matching and stats."""

from __future__ import annotations

import re
import statistics
import unicodedata
import uuid
from dataclasses import dataclass
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
    raise NotImplementedError


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
