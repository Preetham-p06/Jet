"""Extraction accuracy on `fixtures/eval/cases` (design spec §10).

    uv run python scripts/eval_extraction.py --extractor rules --min-accuracy 0.85
    uv run python scripts/eval_extraction.py --extractor both --out report.json

Each case directory holds `meta.json`, `expected.json` and `input.*`; a case may
point `input` / `expected` elsewhere (the demo cases reuse `fixtures/demo`).

Scoring. Every expected scalar, every expected fee (matched on status and amount,
plus `percent`, `hedged` and `explicitly_extra` when the case lists them) and the
intent is one item; an `unreadable` case is one item that passes when the
extractor raises `DocumentUnreadable`. Money matches to the cent, text after
case and whitespace folding (aircraft models canonicalized), numbers exactly.
When an extractor returns several values for a key (chat messages, quoted
email), the one with the highest `sequence` is compared, as the merge would.

`confidence` and `pages` in an expected file are strict checks for the rules
extractor; they are reported but do not count towards accuracy.

Exit status: 1 when overall accuracy is below `--min-accuracy`, or (rules only)
demo accuracy is below `--min-demo-accuracy`.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import Settings, get_settings  # noqa: E402
from app.extraction.base import (  # noqa: E402
    DocumentInput,
    DocumentUnreadable,
    ExtractionContext,
    Extractor,
    LegContext,
)
from app.extraction.documents import load_document  # noqa: E402
from app.extraction.provenance import verify  # noqa: E402
from app.extraction.rules.aircraft import canonical_model  # noqa: E402
from app.extraction.rules.extractor import RulesExtractor  # noqa: E402
from app.extraction.types import ExtractedFee, ExtractedField, ExtractionResult, Money  # noqa: E402
from app.models.enums import DocumentChannel, FeeCategory  # noqa: E402

CASES_DIR = ROOT / "fixtures" / "eval" / "cases"
KNOWN_OPERATORS = (
    "Atlas Air Charter",
    "SkyBridge Aviation",
    "Northstar Jets",
    "Summit Executive Aviation",
    "Harbor Jet Group",
    "Coastal Wings",
    "Meridian Air",
    "Blue Ridge Charter",
)
DEFAULT_TRIP = {
    "origin": "KTEB",
    "destination": "KOPF",
    "depart_local": "2026-10-18T09:00",
    "pax": 7,
}
BUCKETS = (("90+", 90, 101), ("75-89", 75, 90), ("<75", 0, 75))


# --------------------------------------------------------------------------- cases


@dataclass(frozen=True)
class Case:
    case_id: str
    directory: Path
    meta: dict[str, Any]
    expected: dict[str, Any]
    input_path: Path

    @property
    def demo(self) -> bool:
        return bool(self.meta.get("demo"))


def load_cases(pattern: str = "*", cases_dir: Path = CASES_DIR) -> list[Case]:
    cases: list[Case] = []
    for directory in sorted(p for p in cases_dir.iterdir() if p.is_dir()):
        if not fnmatch.fnmatch(directory.name, pattern):
            continue
        meta = json.loads((directory / "meta.json").read_text(encoding="utf-8"))
        expected_path = (directory / meta.get("expected", "expected.json")).resolve()
        expected = json.loads(expected_path.read_text(encoding="utf-8"))
        input_path = (directory / meta.get("input", "input.pdf")).resolve()
        cases.append(Case(directory.name, directory, meta, expected, input_path))
    return cases


def context_for(case: Case) -> ExtractionContext:
    trip = {**DEFAULT_TRIP, **case.meta.get("trip", {})}
    depart = datetime.fromisoformat(trip["depart_local"])
    return ExtractionContext(
        legs=(LegContext(trip["origin"], trip["destination"], depart),),
        pax=int(trip["pax"]),
        known_operator_names=tuple(case.meta.get("known_operator_names", KNOWN_OPERATORS)),
        default_year=depart.year,
    )


def load_case_document(case: Case, settings: Settings) -> DocumentInput:
    channel = case.meta.get("channel")
    received = case.meta.get("received_at")
    loaded = load_document(
        data=case.input_path.read_bytes(),
        text=None,
        filename=case.input_path.name,
        channel=DocumentChannel(channel) if channel else None,
        sender=case.meta.get("sender"),
        subject=case.meta.get("subject"),
        received_at=datetime.fromisoformat(received) if received else None,
        settings=settings,
    )
    return loaded.input


# --------------------------------------------------------------------------- comparison


def _fold(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def expected_money(value: Any, currency: str) -> Money:
    if isinstance(value, dict):
        amount, currency = value["amount"], value.get("currency", currency)
    else:
        amount = value
    minor = int((Decimal(str(amount)) * 100).to_integral_value())
    return Money(amount_minor=minor, currency=currency)


def values_match(key: str, expected: Any, actual: Any, currency: str) -> bool:
    if actual is None:
        return expected is None
    if isinstance(actual, Money):
        return expected is not None and actual == expected_money(expected, currency)
    if isinstance(expected, bool) or isinstance(actual, bool):
        return expected is actual
    if isinstance(expected, int | float) and isinstance(actual, int | float):
        return abs(float(expected) - float(actual)) < 1e-6
    if isinstance(expected, str) and isinstance(actual, str):
        if key == "aircraft_model":
            return _fold(canonical_model(expected) or expected) == _fold(
                canonical_model(actual) or actual
            )
        return _fold(expected) == _fold(actual)
    return bool(expected == actual)


def fee_key(fee: ExtractedFee) -> str:
    if fee.category is FeeCategory.OTHER:
        return f"other.{_fold(fee.label)}"
    return fee.category.value


def latest_fields(result: ExtractionResult) -> dict[str, ExtractedField]:
    chosen: dict[str, ExtractedField] = {}
    for item in result.fields:
        current = chosen.get(item.key)
        if current is None or item.sequence >= current.sequence:
            chosen[item.key] = item
    return chosen


def latest_fees(result: ExtractionResult) -> dict[str, ExtractedFee]:
    chosen: dict[str, ExtractedFee] = {}
    for fee in result.fees:
        key = fee_key(fee)
        current = chosen.get(key)
        if current is None or fee.sequence >= current.sequence:
            chosen[key] = fee
    return chosen


def fee_matches(expected: dict[str, Any], fee: ExtractedFee, currency: str) -> bool:
    if fee.status != expected["status"]:
        return False
    exp_amount = expected.get("amount")
    if exp_amount is None:
        if fee.amount is not None and fee.status not in ("included", "waived"):
            return False
    elif fee.amount is None or fee.amount != expected_money(exp_amount, currency):
        return False
    if "percent" in expected and (
        fee.percent is None or Decimal(str(expected["percent"])) != fee.percent
    ):
        return False
    for flag in ("hedged", "explicitly_extra"):
        if flag in expected and bool(expected[flag]) != getattr(fee, flag):
            return False
    return True


@dataclass
class CaseReport:
    case_id: str
    demo: bool
    items: list[dict[str, Any]] = field(default_factory=list)
    strict_failures: list[str] = field(default_factory=list)
    fee_tp: int = 0
    fee_extracted: int = 0
    fee_expected: int = 0
    known_total: dict[str, Any] | None = None
    snippets_verified: int = 0
    snippets_total: int = 0
    error: str | None = None

    @property
    def correct(self) -> int:
        return sum(1 for item in self.items if item["correct"])

    @property
    def accuracy(self) -> float:
        return self.correct / len(self.items) if self.items else 0.0


def compare(
    case: Case, result: ExtractionResult | None, error: Exception | None, *, strict: bool
) -> CaseReport:
    report = CaseReport(case.case_id, case.demo)
    expected = case.expected
    if expected.get("unreadable"):
        ok = isinstance(error, DocumentUnreadable)
        report.items.append({"key": "unreadable", "correct": ok, "confidence": None})
        if error is not None and not ok:
            report.error = f"{type(error).__name__}: {error}"
        return report
    if result is None:
        report.error = f"{type(error).__name__}: {error}" if error else "no result"
        total = len(expected.get("fields", {})) + len(expected.get("fees", {})) + 1
        report.items = [{"key": "error", "correct": False, "confidence": None}] * total
        report.fee_expected = len(expected.get("fees", {}))
        return report

    currency = expected.get("currency", "USD")
    fields = latest_fields(result)
    fees = latest_fees(result)
    if "intent" in expected:
        report.items.append(
            {
                "key": "intent",
                "correct": result.intent == expected["intent"],
                "expected": expected["intent"],
                "actual": result.intent,
                "confidence": None,
            }
        )
    for key, value in expected.get("fields", {}).items():
        got = fields.get(key)
        actual = got.value if got else None
        report.items.append(
            {
                "key": key,
                "correct": got is not None and values_match(key, value, actual, currency),
                "expected": value,
                "actual": actual.model_dump() if isinstance(actual, Money) else actual,
                "confidence": got.confidence if got else None,
            }
        )
    expected_fees: dict[str, dict[str, Any]] = expected.get("fees", {})
    for key, spec in expected_fees.items():
        fee = fees.get(key)
        ok = fee is not None and fee_matches(spec, fee, currency)
        report.items.append(
            {
                "key": f"fee.{key}",
                "correct": ok,
                "expected": spec,
                "actual": None
                if fee is None
                else {
                    "status": fee.status,
                    "amount": fee.amount.model_dump() if fee.amount else None,
                    "percent": str(fee.percent) if fee.percent is not None else None,
                },
                "confidence": fee.confidence if fee else None,
            }
        )
        report.fee_tp += int(ok)
    report.fee_extracted = len(fees)
    report.fee_expected = len(expected_fees)

    all_items = [*result.fields, *result.fees]
    report.snippets_total = len(all_items)
    report.snippets_verified = sum(1 for item in all_items if item.evidence.verified)

    if strict:
        for key, want in expected.get("confidence", {}).items():
            got_conf = _confidence_of(key, fields, fees)
            if got_conf != want:
                report.strict_failures.append(f"confidence {key}: expected {want}, got {got_conf}")
        for key, want in expected.get("pages", {}).items():
            page = _page_of(key, fields, fees)
            if page != want:
                report.strict_failures.append(f"page {key}: expected {want}, got {page}")

    if "known_total" in expected:
        got_total, method = known_total_cents(result, case)
        want = expected_money(expected["known_total"], currency).amount_minor
        report.known_total = {"expected": want, "actual": got_total, "method": method}
    return report


def _confidence_of(
    key: str, fields: dict[str, ExtractedField], fees: dict[str, ExtractedFee]
) -> int | None:
    if key.startswith("fee."):
        fee = fees.get(key[4:])
        return fee.confidence if fee else None
    item = fields.get(key)
    return item.confidence if item else None


def _page_of(
    key: str, fields: dict[str, ExtractedField], fees: dict[str, ExtractedFee]
) -> int | None:
    if key.startswith("fee."):
        fee = fees.get(key[4:])
        return fee.evidence.page if fee else None
    item = fields.get(key)
    return item.evidence.page if item else None


# --------------------------------------------------------------------------- known total


def known_total_cents(result: ExtractionResult, case: Case) -> tuple[int | None, str]:
    """Known total in cents through the real normalizer; a local re-statement of its
    rules (spec §4) while `services.normalization` is not available."""
    try:
        return _normalizer_total(result, case), "normalizer"
    except NotImplementedError:
        return _fallback_total(result), "fallback"


def _normalizer_total(result: ExtractionResult, case: Case) -> int | None:
    from app.models.enums import AmountStatus, PricingBasis, QuoteStatus, TripType
    from app.services.contracts import (
        FeeLineState,
        FxTable,
        LegState,
        QuoteState,
        TripContext,
        TripPreferencesState,
    )
    from app.services.normalization import normalize_quote

    fields = latest_fields(result)

    def money(key: str) -> int | None:
        item = fields.get(key)
        return item.value.amount_minor if item and isinstance(item.value, Money) else None

    def number(key: str) -> Decimal | None:
        item = fields.get(key)
        return Decimal(str(item.value)) if item and item.value is not None else None

    headline = fields.get("headline_price")
    currency = headline.value.currency if headline and isinstance(headline.value, Money) else "USD"
    ctx = context_for(case)
    leg = ctx.legs[0]
    now = datetime(2026, 10, 1, tzinfo=UTC)
    trip = TripContext(
        trip_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        reference="EVAL",
        trip_type=TripType.ONE_WAY,
        pax=ctx.pax,
        legs=(
            LegState(
                seq=1,
                origin_icao=leg.origin_icao,
                destination_icao=leg.destination_icao,
                depart_local=leg.depart_local,
                depart_tz="America/New_York",
                depart_utc=leg.depart_local.replace(tzinfo=UTC),
            ),
        ),
        preferences=TripPreferencesState(),
        review_threshold=75,
    )
    fees = tuple(
        FeeLineState(
            category=fee.category,
            label=fee.label,
            status=AmountStatus(fee.status),
            amount_minor=fee.amount.amount_minor if fee.amount else None,
            currency=fee.amount.currency if fee.amount else None,
            unit=fee.unit,
            quantity=fee.quantity,
            percent=fee.percent,
            explicitly_extra=fee.explicitly_extra,
            hedged=fee.hedged,
            confidence=fee.confidence,
        )
        for fee in latest_fees(result).values()
    )
    all_in = fields.get("all_in")
    state = QuoteState(
        quote_id=uuid.uuid4(),
        operator_id=uuid.uuid4(),
        operator_name="eval",
        status=QuoteStatus.ACTIVE,
        currency=currency,
        pricing_basis=PricingBasis.HOURLY
        if money("hourly_rate") and not money("headline_price")
        else PricingBasis.FLAT,
        created_at=now,
        headline_minor=money("headline_price"),
        hourly_rate_minor=money("hourly_rate"),
        billable_hours=number("billable_hours"),
        daily_minimum_hours=number("daily_minimum_hours"),
        stated_total_minor=money("stated_total"),
        all_in=bool(all_in and all_in.value is True),
        fees=fees,
    )
    fx = FxTable(as_of=date(2026, 10, 1), rates={})
    return normalize_quote(state, trip, fx, ()).known_total_cents


def _fallback_total(result: ExtractionResult) -> int | None:
    fields = latest_fields(result)

    def money(key: str) -> int | None:
        item = fields.get(key)
        return item.value.amount_minor if item and isinstance(item.value, Money) else None

    headline = money("headline_price")
    if headline is None and money("hourly_rate") is not None:
        rate = Decimal(money("hourly_rate") or 0)
        hours = max(
            Decimal(str(fields["billable_hours"].value)) if "billable_hours" in fields else 0,
            Decimal(str(fields["daily_minimum_hours"].value))
            if "daily_minimum_hours" in fields
            else 0,
        )
        headline = int(rate * hours)
    if headline is None:
        return None
    total = headline
    base = headline
    percent_lines: list[Decimal] = []
    for fee in latest_fees(result).values():
        if fee.status != "stated":
            continue
        if fee.amount is not None:
            amount = fee.amount.amount_minor
            if fee.quantity is not None and fee.unit.value == "per_hour":
                amount = int(Decimal(amount) * fee.quantity)
            total += amount
            if fee.category.value not in ("fet", "segment_fees", "taxes", "international"):
                base += amount
        elif fee.percent is not None:
            percent_lines.append(fee.percent)
    for pct in percent_lines:
        total += int((Decimal(base) * pct / 100).to_integral_value())
    stated = money("stated_total")
    if stated is not None and stated > total:
        total = stated
    return total


# --------------------------------------------------------------------------- running


def run_extractor(
    extractor: Extractor, cases: list[Case], settings: Settings, *, strict: bool
) -> list[CaseReport]:
    reports: list[CaseReport] = []
    for case in cases:
        result: ExtractionResult | None = None
        error: Exception | None = None
        try:
            doc = load_case_document(case, settings)
            raw = extractor.extract(doc, context_for(case))
            result, _ = verify(raw, doc)
        except Exception as exc:  # report every failure as a miss, keep going
            error = exc
        reports.append(compare(case, result, error, strict=strict))
    return reports


def summarize(reports: list[CaseReport]) -> dict[str, Any]:
    def accuracy(selected: list[CaseReport]) -> float | None:
        items = [item for r in selected for item in r.items]
        return sum(1 for i in items if i["correct"]) / len(items) if items else None

    per_key: dict[str, list[bool]] = defaultdict(list)
    buckets: dict[str, list[bool]] = defaultdict(list)
    for report in reports:
        for item in report.items:
            key = item["key"].split(".")[0] if item["key"].startswith("fee.") else item["key"]
            per_key[item["key"] if key != "fee" else "fee"].append(item["correct"])
            conf = item.get("confidence")
            if conf is not None:
                for name, lo, hi in BUCKETS:
                    if lo <= conf < hi:
                        buckets[name].append(item["correct"])
    tp = sum(r.fee_tp for r in reports)
    extracted = sum(r.fee_extracted for r in reports)
    expected = sum(r.fee_expected for r in reports)
    totals = [r.known_total for r in reports if r.known_total]
    verified = sum(r.snippets_verified for r in reports)
    snippets = sum(r.snippets_total for r in reports)
    return {
        "cases": len(reports),
        "accuracy": accuracy(reports),
        "demo_accuracy": accuracy([r for r in reports if r.demo]),
        "per_key": {k: sum(v) / len(v) for k, v in sorted(per_key.items())},
        "fee_precision": tp / extracted if extracted else None,
        "fee_recall": tp / expected if expected else None,
        "known_total_accuracy": (
            sum(1 for t in totals if t["actual"] == t["expected"]) / len(totals) if totals else None
        ),
        "known_total_method": sorted({t["method"] for t in totals}),
        "calibration": {
            name: {"n": len(buckets[name]), "accuracy": sum(buckets[name]) / len(buckets[name])}
            for name, _, _ in BUCKETS
            if buckets[name]
        },
        "snippet_verified_rate": verified / snippets if snippets else None,
        "strict_failures": sum(len(r.strict_failures) for r in reports),
    }


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def print_report(name: str, reports: list[CaseReport], summary: dict[str, Any]) -> None:
    print(f"\n== {name} extractor ==")
    for report in reports:
        tag = " (demo)" if report.demo else ""
        print(f"  {report.case_id:<26}{report.correct:>3}/{len(report.items):<3}{tag}")
        for item in report.items:
            if not item["correct"]:
                print(
                    f"      MISS {item['key']}: expected {item.get('expected')!r}, "
                    f"got {item.get('actual')!r}"
                )
        for failure in report.strict_failures:
            print(f"      STRICT {failure}")
        if report.error:
            print(f"      ERROR {report.error}")
    print(f"  accuracy            {_fmt(summary['accuracy'])}")
    print(f"  demo accuracy       {_fmt(summary['demo_accuracy'])}")
    print(f"  fee precision       {_fmt(summary['fee_precision'])}")
    print(f"  fee recall          {_fmt(summary['fee_recall'])}")
    methods = ",".join(summary["known_total_method"])
    print(f"  known_total acc.    {_fmt(summary['known_total_accuracy'])} ({methods})")
    print(f"  snippets verified   {_fmt(summary['snippet_verified_rate'])}")
    for bucket, stats in summary["calibration"].items():
        print(f"  confidence {bucket:<8} n={stats['n']:<4} accuracy {stats['accuracy']:.3f}")
    print(f"  strict failures     {summary['strict_failures']}")


def build_claude(settings: Settings) -> Extractor | None:
    if settings.anthropic_api_key is None or not settings.anthropic_api_key.get_secret_value():
        print("\n== claude extractor ==\n  skipped: ANTHROPIC_API_KEY is not set")
        return None
    from app.extraction.registry import select_extractor

    claude_settings = settings.model_copy(update={"extractor": "claude"})
    return select_extractor(claude_settings)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--extractor", choices=("rules", "claude", "both"), default="rules")
    parser.add_argument("--cases", default="*", help="glob over case directory names")
    parser.add_argument("--out", type=Path, help="write a JSON report here")
    parser.add_argument("--min-accuracy", type=float, default=0.0)
    parser.add_argument("--min-demo-accuracy", type=float, default=0.95)
    args = parser.parse_args(argv)

    cases = load_cases(args.cases)
    if not cases:
        print(f"no cases match {args.cases!r}")
        return 1
    settings = get_settings()
    output: dict[str, Any] = {}
    status = 0
    names = ("rules", "claude") if args.extractor == "both" else (args.extractor,)
    for name in names:
        extractor: Extractor | None
        extractor = RulesExtractor() if name == "rules" else build_claude(settings)
        if extractor is None:
            continue
        reports = run_extractor(extractor, cases, settings, strict=name == "rules")
        summary = summarize(reports)
        print_report(name, reports, summary)
        output[name] = {
            "summary": summary,
            "cases": [
                {
                    "case_id": r.case_id,
                    "demo": r.demo,
                    "accuracy": r.accuracy,
                    "items": r.items,
                    "strict_failures": r.strict_failures,
                    "known_total": r.known_total,
                    "error": r.error,
                }
                for r in reports
            ],
        }
        accuracy = summary["accuracy"] or 0.0
        if accuracy < args.min_accuracy:
            print(f"  FAIL: accuracy {accuracy:.3f} < {args.min_accuracy}")
            status = 1
        demo = summary["demo_accuracy"]
        if name == "rules" and demo is not None and demo < args.min_demo_accuracy:
            print(f"  FAIL: demo accuracy {demo:.3f} < {args.min_demo_accuracy}")
            status = 1
    if args.out:
        args.out.write_text(json.dumps(output, indent=2, default=str) + "\n", encoding="utf-8")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
