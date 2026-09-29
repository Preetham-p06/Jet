"""The rule-based extractor: segment, match lexicon, parse money, assign, score."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, time
from typing import Final

from app.extraction.base import DocumentInput, DocumentUnreadable, ExtractionContext
from app.extraction.rules import confidence as conf
from app.extraction.rules.aircraft import find_aircraft
from app.extraction.rules.lexicon import (
    ABBREVIATED_INCLUDED,
    AnchorMatch,
    Qualifier,
    QualifierMatch,
    match_anchors,
    match_qualifiers,
)
from app.extraction.rules.money import MoneyMatch, find_money
from app.extraction.rules.patterns import (
    DURATION_CONTEXT_RE,
    Found,
    detect_decline,
    distinctive_tokens,
    find_availability,
    find_billable_hours,
    find_category,
    find_daily_minimum,
    find_dates,
    find_durations,
    find_operator_name,
    find_pax,
    find_route,
    find_seats,
    find_tail_numbers,
    find_times,
    find_wifi,
    is_validity_context,
)
from app.extraction.rules.segment import Clause, LineKind, normalize_text, segment
from app.extraction.types import (
    Evidence,
    ExtractedFee,
    ExtractedField,
    ExtractionIntent,
    ExtractionResult,
    Money,
)
from app.models.enums import DocumentKind, FeeCategory, FeeUnit

RULES_VERSION: Final = "rules-1"

RIGHT_ANCHOR_CHARS: Final = 25
HEADLINE_FALLBACK_MIN_MINOR: Final = 1000_00
LABEL_MAX_CHARS: Final = 80

_LEADERS: Final = re.compile(r"[\s.·…_:]+")
_LABEL_TRIM: Final = " \t.:·…_-=(["
_REVISION_RE: Final = re.compile(
    r"\b(?:revised|revision|updated\s+(?:quote|price|pricing)|correction|amended)\b",
    re.I,
)
_DEPARTURE_RE: Final = re.compile(
    r"\b(?:dep(?:art(?:ure|ing|s)?)?|etd|wheels\s+up|off\s+blocks|pick\s*up)\b", re.I
)
_OTHER_EXCLUDED: Final = re.compile(
    r"\b(?:total|subtotal|sub-total|deposit|balance|payment|due|price|rate|amount|quote|"
    r"valid|ref|invoice)\b",
    re.I,
)
_LABEL_SPLIT: Final = re.compile(r"\s*(?::|\.{3,}|…)\s*")


_MONEY_KEYS: Final = frozenset({"headline_price", "hourly_rate", "stated_total"})


def _fee_key(fee: ExtractedFee) -> tuple[str, int]:
    """Merge key of a fee: `category`, or `other.<label>`, per sequence."""
    suffix = "." + fee.label.lower() if fee.category is FeeCategory.OTHER else ""
    return fee.category.value + suffix, fee.sequence


@dataclass(slots=True)
class _Assigned:
    """Money values attached to one anchor."""

    clause: int
    anchor: AnchorMatch
    values: list[tuple[int, MoneyMatch]] = field(default_factory=list)  # (clause idx, money)


@dataclass(slots=True)
class _State:
    fields: list[ExtractedField] = field(default_factory=list)
    fees: list[ExtractedFee] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    seen_keys: set[tuple[str, int]] = field(default_factory=set)
    conflicts: set[tuple[str, int]] = field(default_factory=set)


class RulesExtractor:
    """Deterministic, offline extractor.

    Raises `DocumentUnreadable` for documents without a text layer (scanned
    PDFs, images). Money assignment: nearest anchor to the left in the clause,
    else the previous clause's last anchor in the same sentence, else the
    nearest anchor to the right within 25 characters.
    """

    name = "rules"
    version = RULES_VERSION

    def extract(self, doc: DocumentInput, ctx: ExtractionContext) -> ExtractionResult:
        if doc.kind is DocumentKind.IMAGE or doc.is_scanned or not doc.has_text_layer:
            raise DocumentUnreadable(
                "The document has no text layer; OCR needs the Claude extractor",
                reason="no_text_layer",
            )
        return _Run(doc, ctx).run()


class _Run:
    def __init__(self, doc: DocumentInput, ctx: ExtractionContext) -> None:
        self.doc = doc
        self.ctx = ctx
        self.clauses = segment(doc)
        self.anchors = [match_anchors(c.text) for c in self.clauses]
        self.qualifiers = [match_qualifiers(c.text) for c in self.clauses]
        self.state = _State()
        self._unit_cache: dict[tuple[int | None, int], str] = {}
        year = ctx.default_year
        if year is None and ctx.legs:
            year = ctx.legs[0].depart_local.year
        self.default_year = year
        self.currency = self._document_currency()

    # ------------------------------------------------------------------ helpers

    def unit_text(self, clause: Clause) -> str:
        key = (clause.page, clause.sequence)
        cached = self._unit_cache.get(key)
        if cached is not None:
            return cached
        text = ""
        if self.doc.messages:
            for msg in self.doc.messages:
                if msg.sequence == clause.sequence:
                    text = msg.text
                    break
        else:
            for page in self.doc.pages:
                if clause.page is None or page.page == clause.page:
                    text = page.text
                    break
        text = normalize_text(text)
        self._unit_cache[key] = text
        return text

    def evidence(self, first: Clause, last: Clause | None = None) -> Evidence:
        last = last or first
        if (last.page, last.sequence) != (first.page, first.sequence):
            last = first
        start, end = first.char_start, max(first.char_end, last.char_end)
        snippet = self.unit_text(first)[start:end] or first.text
        return Evidence(snippet=snippet, page=first.page, char_start=start, char_end=end)

    def prev_clause(self, idx: int) -> int | None:
        if idx == 0:
            return None
        prev = self.clauses[idx - 1]
        if prev.sentence_index != self.clauses[idx].sentence_index:
            return None
        return idx - 1

    def _document_currency(self) -> str:
        counts: Counter[str] = Counter()
        for clause in self.clauses:
            for m in find_money(clause.text, default_currency=self.ctx.base_currency):
                if m.explicit_currency:
                    counts[m.currency] += 1
        if counts:
            return counts.most_common(1)[0][0]
        return self.ctx.base_currency

    def add_field(
        self, key: str, value: object, confidence: int, evidence: Evidence, sequence: int
    ) -> None:
        if (key, sequence) in self.state.seen_keys:
            if key in _MONEY_KEYS and any(
                f.key == key and f.sequence == sequence and f.value != value
                for f in self.state.fields
            ):
                self.state.conflicts.add((key, sequence))
            return
        self.state.seen_keys.add((key, sequence))
        self.state.fields.append(
            ExtractedField.model_validate(
                {
                    "key": key,
                    "value": value,
                    "confidence": conf.clamp(confidence),
                    "evidence": evidence,
                    "sequence": sequence,
                }
            )
        )

    # ------------------------------------------------------------------ main

    def run(self) -> ExtractionResult:
        assigned, unassigned = self._assign()
        used_anchor_keys: set[tuple[int, int]] = set()
        for item in assigned:
            used_anchor_keys.add((item.clause, item.anchor.start))
            self._emit_assigned(item)
        self._emit_moneyless(used_anchor_keys)
        self._emit_unassigned(unassigned)
        self._emit_scalars()
        self._apply_conflicts()
        intent = self._intent()
        if intent in ("quote", "revision") and not any(
            f.key in ("headline_price", "hourly_rate", "stated_total") for f in self.state.fields
        ):
            self.state.warnings.append("no_price_found")
        return ExtractionResult(
            extractor="rules",
            extractor_version=RULES_VERSION,
            intent=intent,
            fields=self.state.fields,
            fees=self.state.fees,
            warnings=self.state.warnings,
        )

    # ------------------------------------------------------------------ money

    def _assign(self) -> tuple[list[_Assigned], list[tuple[int, MoneyMatch]]]:
        by_anchor: dict[tuple[int, int], _Assigned] = {}
        order: list[tuple[int, int]] = []
        unassigned: list[tuple[int, MoneyMatch]] = []
        for idx, clause in enumerate(self.clauses):
            anchors = self.anchors[idx]
            prev = self.prev_clause(idx)
            has_anchor = bool(anchors) or (prev is not None and bool(self.anchors[prev]))
            for money in find_money(
                clause.text, default_currency=self.currency, has_anchor=has_anchor
            ):
                target: tuple[int, AnchorMatch] | None = None
                left = [a for a in anchors if a.end <= money.start]
                if left:
                    target = (idx, left[-1])
                elif not anchors and prev is not None and self.anchors[prev]:
                    target = (prev, self.anchors[prev][-1])
                else:
                    right = [
                        a
                        for a in anchors
                        if a.start >= money.end and a.start - money.end <= RIGHT_ANCHOR_CHARS
                    ]
                    if right:
                        target = (idx, right[0])
                if target is None:
                    unassigned.append((idx, money))
                    continue
                key = (target[0], target[1].start)
                if key not in by_anchor:
                    by_anchor[key] = _Assigned(target[0], target[1])
                    order.append(key)
                by_anchor[key].values.append((idx, money))
        return [by_anchor[k] for k in order], unassigned

    def _scope_qualifiers(self, item: _Assigned, money_idx: int, money: MoneyMatch) -> set[str]:
        """Qualifier texts that apply to an anchor with a value (see module docs)."""
        a_idx, anchor = item.clause, item.anchor
        anchors = self.anchors[a_idx]
        quals = self.qualifiers[a_idx]
        if money_idx != a_idx:
            # Cross-clause: the anchor's clause from the anchor on, plus the whole money clause.
            chosen = [q for q in quals if q.start >= anchor.start]
            chosen += self.qualifiers[money_idx]
        elif money.amount_minor is None:
            chosen = list(quals)  # percentages ("FET 7.5% ... included") take the clause
        else:
            first = anchors[0].start if anchors else 0
            lo = 0 if anchor.start == first else anchor.start
            after = [a.start for a in anchors if a.start >= max(money.end, anchor.end)]
            hi = after[0] if after else len(self.clauses[a_idx].text)
            chosen = [q for q in quals if q.start >= lo and q.end <= hi]
        return {q.qualifier.value + "|" + q.text.lower() for q in chosen}

    @staticmethod
    def _has(quals: set[str], qualifier: Qualifier) -> bool:
        return any(q.split("|", 1)[0] == qualifier.value for q in quals)

    def _far(self, item: _Assigned, money_idx: int, money: MoneyMatch) -> bool:
        a_clause = self.clauses[item.clause]
        anchor = item.anchor
        if money_idx == item.clause:
            if money.start >= anchor.end:
                gap = a_clause.text[anchor.end : money.start]
            else:
                gap = a_clause.text[money.end : anchor.start]
        else:
            gap = a_clause.text[anchor.end :] + " " + self.clauses[money_idx].text[: money.start]
        return len(_LEADERS.sub(" ", gap)) > conf.FAR_ANCHOR_CHARS

    def _label(self, item: _Assigned, money_idx: int, money: MoneyMatch) -> str:
        text = self.clauses[item.clause].text
        anchor = item.anchor
        label = anchor.text
        if money_idx == item.clause and money.start >= anchor.end:
            label = text[anchor.start : money.start]
            label = re.split(r"\s*(?:\.{3,}|…)", label)[0]
            label = label.strip(_LABEL_TRIM)
            if label.count("(") > label.count(")"):
                label += ")"
        return (label or anchor.text).strip()[:LABEL_MAX_CHARS]

    def _emit_assigned(self, item: _Assigned) -> None:
        amounts = [(i, m) for i, m in item.values if m.amount_minor is not None]
        percents = [(i, m) for i, m in item.values if m.percent is not None]
        money_idx, money = amounts[0] if amounts else percents[0]
        clause = self.clauses[item.clause]
        m_clause = self.clauses[money_idx]
        quals = self._scope_qualifiers(item, money_idx, money)
        hedge = self._has(quals, Qualifier.HEDGE)
        estimate = self._has(quals, Qualifier.ESTIMATE)
        extra = self._has(quals, Qualifier.EXTRA)
        far = self._far(item, money_idx, money)
        first, last = (clause, m_clause) if money_idx >= item.clause else (m_clause, clause)
        evidence = self.evidence(first, last)
        seq = clause.sequence
        anchor = item.anchor
        amount = (
            Money(amount_minor=money.amount_minor, currency=money.currency)
            if money.amount_minor is not None
            else None
        )

        if anchor.kind != "fee":
            if amount is None:
                return
            score = conf.score(
                clause.line_kind,
                currency_marker=money.explicit_currency,
                hedge=hedge,
                estimate=estimate,
                far_from_anchor=far,
            )
            if money.per_hour or anchor.kind == "hourly_rate":
                self.add_field("hourly_rate", amount, score, evidence, seq)
                if money.quantity is not None:
                    self.add_field("billable_hours", float(money.quantity), score, evidence, seq)
                return
            key = "headline_price" if anchor.kind == "headline" else "stated_total"
            self.add_field(key, amount, score, evidence, seq)
            if anchor.kind == "headline" and self._has(quals, Qualifier.ALL_IN):
                self.add_field("all_in", True, score, evidence, seq)
            return

        assert anchor.category is not None  # noqa: S101 - fee anchors always carry one
        percent = percents[0][1].percent if percents else None
        unit = FeeUnit.FLAT
        if money.per_hour:
            unit = FeeUnit.PER_HOUR
        elif amount is None:
            unit = FeeUnit.PERCENT
        included = [q for q in quals if q.startswith(Qualifier.INCLUDED.value + "|")]
        explicitly_extra = False
        hedged = False
        if self._has(quals, Qualifier.WAIVED):
            status, score = "waived", conf.INCLUDED_SCORE
        elif included and not extra:
            abbreviated = all(q.split("|", 1)[1] in ABBREVIATED_INCLUDED for q in included)
            status = "included"
            score = conf.INCLUDED_ABBREVIATED_SCORE if abbreviated else conf.INCLUDED_SCORE
        elif hedge or estimate:
            status, hedged = "estimated", True
            score = conf.score(
                clause.line_kind,
                currency_marker=money.explicit_currency,
                hedge=hedge,
                estimate=estimate,
                far_from_anchor=far,
            )
        else:
            status = "stated"
            explicitly_extra = extra
            score = conf.score(
                clause.line_kind,
                currency_marker=money.explicit_currency,
                explicit_extra=extra,
                far_from_anchor=far,
            )
        self._add_fee(
            ExtractedFee(
                category=anchor.category,
                label=self._label(item, money_idx, money),
                status=status,  # type: ignore[arg-type]
                amount=amount,
                unit=unit,
                quantity=money.quantity,
                percent=percent,
                explicitly_extra=explicitly_extra,
                hedged=hedged,
                confidence=conf.clamp(score),
                evidence=evidence,
                sequence=seq,
            )
        )

    def _add_fee(self, fee: ExtractedFee) -> None:
        for existing in self.state.fees:
            same_key = existing.category == fee.category and (
                fee.category is not FeeCategory.OTHER or existing.label == fee.label
            )
            if (
                same_key
                and existing.sequence == fee.sequence
                and existing.amount == fee.amount
                and existing.status == fee.status
            ):
                return  # the same charge matched twice (e.g. two synonyms in one line)
        self.state.fees.append(fee)

    def _emit_moneyless(self, used: set[tuple[int, int]]) -> None:
        for idx, clause in enumerate(self.clauses):
            quals = self.qualifiers[idx]
            kinds = {q.qualifier for q in quals}
            for anchor in self.anchors[idx]:
                if (idx, anchor.start) in used:
                    continue
                if anchor.kind == "headline" and Qualifier.ALL_IN in kinds:
                    self.add_field(
                        "all_in",
                        True,
                        conf.BASE[clause.line_kind],
                        self.evidence(clause),
                        clause.sequence,
                    )
                if anchor.kind != "fee" or anchor.category is None:
                    continue
                self._moneyless_fee(idx, clause, anchor, quals, kinds)

    def _moneyless_fee(
        self,
        idx: int,
        clause: Clause,
        anchor: AnchorMatch,
        quals: list[QualifierMatch],
        kinds: set[Qualifier],
    ) -> None:
        assert anchor.category is not None  # noqa: S101
        hedge = Qualifier.HEDGE in kinds
        estimate = Qualifier.ESTIMATE in kinds
        extra = Qualifier.EXTRA in kinds
        if Qualifier.WAIVED in kinds:
            status, score, hedged = "waived", conf.INCLUDED_SCORE, False
        elif Qualifier.INCLUDED in kinds and not extra:
            included = [q for q in quals if q.qualifier is Qualifier.INCLUDED]
            abbreviated = all(q.text.lower() in ABBREVIATED_INCLUDED for q in included)
            status = "included"
            score = conf.INCLUDED_ABBREVIATED_SCORE if abbreviated else conf.INCLUDED_SCORE
            hedged = False
        elif hedge or extra or estimate:
            status, hedged = "not_stated", hedge or estimate
            score = conf.score(
                clause.line_kind,
                explicit_extra=extra and not hedged,
                hedge=hedge,
                estimate=estimate,
            )
        else:
            return
        self._add_fee(
            ExtractedFee(
                category=anchor.category,
                label=anchor.text.strip()[:LABEL_MAX_CHARS],
                status=status,  # type: ignore[arg-type]
                explicitly_extra=status == "not_stated" and extra and not hedged,
                hedged=hedged,
                confidence=conf.clamp(score),
                evidence=self.evidence(clause),
                sequence=clause.sequence,
            )
        )

    def _emit_unassigned(self, unassigned: list[tuple[int, MoneyMatch]]) -> None:
        for idx, money in unassigned:
            clause = self.clauses[idx]
            if money.amount_minor is None:
                continue
            amount = Money(amount_minor=money.amount_minor, currency=money.currency)
            quals = {q.qualifier for q in self.qualifiers[idx]}
            if money.per_hour:
                score = conf.score(clause.line_kind, currency_marker=money.explicit_currency)
                self.add_field("hourly_rate", amount, score, self.evidence(clause), clause.sequence)
                if money.quantity is not None:
                    self.add_field(
                        "billable_hours",
                        float(money.quantity),
                        score,
                        self.evidence(clause),
                        clause.sequence,
                    )
                continue
            label = self._other_label(clause, money)
            if label is not None:
                self._add_fee(
                    ExtractedFee(
                        category=FeeCategory.OTHER,
                        label=label,
                        status="stated",
                        amount=amount,
                        explicitly_extra=Qualifier.EXTRA in quals,
                        confidence=conf.score(
                            clause.line_kind,
                            currency_marker=money.explicit_currency,
                            explicit_extra=Qualifier.EXTRA in quals,
                        ),
                        evidence=self.evidence(clause),
                        sequence=clause.sequence,
                    )
                )
                continue
            has_price = any(
                f.key in ("headline_price", "hourly_rate") and f.sequence == clause.sequence
                for f in self.state.fields
            )
            if (
                not has_price
                and not self.anchors[idx]
                and money.amount_minor >= HEADLINE_FALLBACK_MIN_MINOR
            ):
                score = conf.score(
                    clause.line_kind,
                    currency_marker=money.explicit_currency,
                    hedge=Qualifier.HEDGE in quals,
                    estimate=Qualifier.ESTIMATE in quals,
                    far_from_anchor=True,
                )
                evidence = self.evidence(clause)
                self.add_field("headline_price", amount, score, evidence, clause.sequence)
                if Qualifier.ALL_IN in quals:
                    self.add_field("all_in", True, score, evidence, clause.sequence)

    @staticmethod
    def _other_label(clause: Clause, money: MoneyMatch) -> str | None:
        """ "Pet fee: $150" -> "Pet fee" for labelled lines without a known anchor."""
        if clause.line_kind is not LineKind.LABELLED:
            return None
        before = clause.text[: money.start]
        parts = _LABEL_SPLIT.split(before, maxsplit=1)
        if len(parts) < 2 or parts[1].strip():
            return None
        label = parts[0].strip(_LABEL_TRIM)
        if not label or _OTHER_EXCLUDED.search(label) or not re.search(r"[A-Za-z]{3}", label):
            return None
        return label[:LABEL_MAX_CHARS]

    # ------------------------------------------------------------------ scalars

    def _score(self, found_conf: int, clause: Clause) -> int:
        return min(found_conf, conf.BASE[clause.line_kind] + conf.CURRENCY_BONUS)

    def _clause_at(self, clause_ref: Clause, offset: int) -> Clause:
        for clause in self.clauses:
            if (clause.page, clause.sequence) == (
                clause_ref.page,
                clause_ref.sequence,
            ) and clause.char_start <= offset < max(clause.char_end, clause.char_start + 1):
                return clause
        return clause_ref

    def _emit_scalars(self) -> None:
        explicit_category = False
        route_done: set[int] = set()
        departure_dates: list[tuple[Found[date], Clause]] = []
        departure_times: list[tuple[int, Found[time], Clause]] = []
        seen_units: set[tuple[int | None, int]] = set()

        for idx, clause in enumerate(self.clauses):
            text = clause.text
            seq = clause.sequence
            ev = self.evidence(clause)
            unit_key = (clause.page, clause.sequence)
            if unit_key not in seen_units:
                seen_units.add(unit_key)
                self._unit_scalars(clause)

            category = find_category(text)
            if category is not None:
                explicit_category = True
                score = self._score(category.confidence, clause)
                self.add_field("aircraft_category", category.value.value, score, ev, seq)
            for seats in find_seats(text)[:1]:
                self.add_field("seats", seats.value, self._score(seats.confidence, clause), ev, seq)
            for pax in find_pax(text)[:1]:
                self.add_field("pax", pax.value, self._score(pax.confidence, clause), ev, seq)
            for wifi in find_wifi(text)[:1]:
                self.add_field("wifi", wifi.value, self._score(wifi.confidence, clause), ev, seq)
            for avail in find_availability(text)[:1]:
                score = self._score(avail.confidence, clause)
                self.add_field("availability", avail.value.value, score, ev, seq)
            positioning = any(a.category is FeeCategory.POSITIONING for a in self.anchors[idx])
            if not positioning and seq not in route_done:
                for route in find_route(text)[:1]:
                    route_done.add(seq)
                    score = self._score(route.confidence, clause)
                    self.add_field("departure_airport", route.value[0], score, ev, seq)
                    self.add_field("arrival_airport", route.value[1], score, ev, seq)
            validity = is_validity_context(text)
            for found_date in find_dates(text, default_year=self.default_year):
                if validity:
                    score = self._score(found_date.confidence, clause)
                    self.add_field("valid_until", found_date.value.isoformat(), score, ev, seq)
                else:
                    departure_dates.append((found_date, clause))
                break
            if DURATION_CONTEXT_RE.search(text):
                for duration in find_durations(text)[:1]:
                    score = self._score(duration.confidence, clause)
                    self.add_field("flight_time_minutes", duration.value, score, ev, seq)
            elif not validity:
                for found_time in find_times(text)[:1]:
                    priority = 0 if _DEPARTURE_RE.search(text) else 1
                    departure_times.append((priority, found_time, clause))
            daily = find_daily_minimum(text)
            if daily is not None:
                score = self._score(daily.confidence, clause)
                self.add_field("daily_minimum_hours", daily.value, score, ev, seq)
            billable = find_billable_hours(text)
            if billable is not None:
                score = self._score(billable.confidence, clause)
                self.add_field("billable_hours", billable.value, score, ev, seq)

        self._aircraft_fields(explicit_category)
        self._departure(departure_dates, departure_times)
        self._operator_name()
        self._currency_field()

    def _unit_scalars(self, clause: Clause) -> None:
        """Tail numbers need context across list items, so they scan the whole unit."""
        text = self.unit_text(clause)
        spans = tuple((m.start, m.end) for m in find_aircraft(text))
        for tail in find_tail_numbers(text, context_spans=spans)[:1]:
            owner = self._clause_at(clause, tail.start)
            score = self._score(tail.confidence, owner)
            self.add_field("tail_number", tail.value, score, self.evidence(owner), owner.sequence)

    def _aircraft_fields(self, explicit_category: bool) -> None:
        for clause in self.clauses:
            match = next(iter(find_aircraft(clause.text)), None)
            if match is None:
                continue
            ev = self.evidence(clause)
            seq = clause.sequence
            base = conf.BASE[clause.line_kind] + conf.CURRENCY_BONUS
            self.add_field("aircraft_model", match.entry.model, min(base, 95), ev, seq)
            if not explicit_category:
                self.add_field(
                    "aircraft_category", match.entry.category.value, min(base, 90), ev, seq
                )
            if not any(f.key == "seats" for f in self.state.fields):
                self.add_field(
                    "seats", match.entry.typical_seats, conf.DICTIONARY_INFERRED, ev, seq
                )
            return

    def _departure(
        self,
        dates: list[tuple[Found[date], Clause]],
        times: list[tuple[int, Found[time], Clause]],
    ) -> None:
        if not times:
            return
        date_found: Found[date] | None = None
        date_clause: Clause | None = None
        if dates:
            date_found, date_clause = dates[0]

        # Prefer a time on a departure line, then one in the date's sentence.
        def rank(item: tuple[int, Found[time], Clause]) -> tuple[int, int]:
            priority, _, clause = item
            same = date_clause is not None and clause.sentence_index in (
                date_clause.sentence_index,
                date_clause.sentence_index + 1,
            )
            return (priority, 0 if same else 1)

        best = min(times, key=rank)
        _, found_time, time_clause = best
        if date_found is None or date_clause is None:
            if not self.ctx.legs:
                return
            day = self.ctx.legs[0].depart_local.date()
            score = conf.DICTIONARY_INFERRED
            evidence = self.evidence(time_clause)
        else:
            day = date_found.value
            score = min(
                self._score(date_found.confidence, date_clause),
                self._score(found_time.confidence, time_clause),
            )
            if (date_clause.page, date_clause.sequence) == (time_clause.page, time_clause.sequence):
                first, last = sorted((date_clause, time_clause), key=lambda c: c.char_start)
                if last.char_end - first.char_start <= 300:
                    evidence = self.evidence(first, last)
                else:
                    evidence = self.evidence(time_clause)
            else:
                evidence = self.evidence(time_clause)
        value = f"{day.isoformat()}T{found_time.value.strftime('%H:%M')}"
        self.add_field("departure_local", value, score, evidence, time_clause.sequence)

    def _operator_name(self) -> None:
        if not self.doc.pages and not self.doc.messages:
            return
        first_unit = self.doc.pages[0].text if self.doc.pages else self.doc.messages[0].text
        text = normalize_text(first_unit)
        found = find_operator_name(
            text, sender=self.doc.sender, known_names=self.ctx.known_operator_names
        )
        if found is None:
            return
        page = self.doc.pages[0].page if self.doc.pages else None
        if self.doc.kind is not DocumentKind.PDF:
            page = None
        start, end = found.start, found.end
        if start < 0:
            # From the sender: point at the name (or its distinctive word) if the text has it.
            lowered = text.lower()
            candidates = [found.value.lower(), *sorted(distinctive_tokens(found.value))]
            for token in candidates:
                hit = re.search(rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])", lowered)
                if hit:
                    start, end = hit.start(), hit.end()
                    break
        if start < 0:
            evidence = Evidence(snippet=self.doc.sender or found.value, page=None)
        else:
            line_start = text.rfind("\n", 0, start) + 1
            line_end = text.find("\n", end)
            line_end = len(text) if line_end < 0 else line_end
            evidence = Evidence(
                snippet=text[line_start:line_end].strip() or found.value,
                page=page,
                char_start=line_start,
                char_end=line_end,
            )
        self.add_field("operator_name", found.value, found.confidence, evidence, 0)

    def _currency_field(self) -> None:
        for clause in self.clauses:
            for money in find_money(clause.text, default_currency=self.currency):
                if money.explicit_currency and money.currency == self.currency:
                    score = conf.BASE[clause.line_kind] + conf.CURRENCY_BONUS
                    self.add_field("currency", self.currency, score, self.evidence(clause), 0)
                    return

    # ------------------------------------------------------------------ finishing

    def _apply_conflicts(self) -> None:
        """-20 on each value when one document (same sequence) states a key twice
        with different values."""
        self.state.fields = [
            f.model_copy(update={"confidence": conf.clamp(f.confidence - conf.CONFLICT_PENALTY)})
            if (f.key, f.sequence) in self.state.conflicts
            else f
            for f in self.state.fields
        ]
        fee_values: dict[tuple[str, int], set[str]] = {}
        for fee in self.state.fees:
            amount = fee.amount.model_dump_json() if fee.amount else ""
            values = fee_values.setdefault(_fee_key(fee), set())
            values.add(f"{fee.status}:{amount}:{fee.percent}")
        updated: list[ExtractedFee] = []
        for fee in self.state.fees:
            if len(fee_values[_fee_key(fee)]) > 1:
                fee = fee.model_copy(
                    update={"confidence": conf.clamp(fee.confidence - conf.CONFLICT_PENALTY)}
                )
            updated.append(fee)
        self.state.fees = updated

    def _intent(self) -> ExtractionIntent:
        text = "\n".join(c.text for c in self.clauses)
        has_price = any(
            f.key in ("headline_price", "hourly_rate", "stated_total") for f in self.state.fields
        )
        if not has_price and detect_decline(text):
            return "decline"
        if _REVISION_RE.search(text):
            return "revision"
        if has_price or self.state.fees:
            return "quote"
        return "other"
