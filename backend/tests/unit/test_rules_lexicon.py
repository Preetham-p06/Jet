"""Lexicon: table-driven anchor synonyms and status qualifiers (spec §3.3 step 2)."""

from __future__ import annotations

import pytest

from app.extraction.rules.lexicon import Qualifier, match_anchors, match_qualifiers
from app.models.enums import FeeCategory


@pytest.mark.parametrize(
    ("text", "kind", "category"),
    [
        ("Charter price", "headline", None),
        ("flight charge", "headline", None),
        ("Aircraft charge", "headline", None),
        ("quote is", "headline", None),
        ("quoted at", "headline", None),
        ("Grand total", "stated_total", None),
        ("Total due", "stated_total", None),
        ("hourly rate", "hourly_rate", None),
        ("Repositioning", "fee", FeeCategory.POSITIONING),
        ("ferry flight", "fee", FeeCategory.POSITIONING),
        ("deadhead", "fee", FeeCategory.POSITIONING),
        ("Ramp / handling", "fee", FeeCategory.RAMP_HANDLING),
        ("Ramp & handling", "fee", FeeCategory.RAMP_HANDLING),
        ("FBO fee", "fee", FeeCategory.RAMP_HANDLING),
        ("ground handling", "fee", FeeCategory.RAMP_HANDLING),
        ("Fuel surcharge", "fee", FeeCategory.FUEL_SURCHARGE),
        ("FSC", "fee", FeeCategory.FUEL_SURCHARGE),
        ("catering", "fee", FeeCategory.CATERING),
        ("crew overnight", "fee", FeeCategory.CREW_OVERNIGHT),
        ("Crew RON", "fee", FeeCategory.CREW_OVERNIGHT),
        ("crew hotel", "fee", FeeCategory.CREW_OVERNIGHT),
        ("flight attendant", "fee", FeeCategory.CREW),
        ("per diem", "fee", FeeCategory.CREW),
        ("hangar", "fee", FeeCategory.OVERNIGHT),
        ("Landing fees", "fee", FeeCategory.LANDING),
        ("de-icing", "fee", FeeCategory.DEICING),
        ("glycol", "fee", FeeCategory.DEICING),
        ("customs", "fee", FeeCategory.INTERNATIONAL),
        ("eAPIS", "fee", FeeCategory.INTERNATIONAL),
        ("Federal excise tax", "fee", FeeCategory.FET),
        ("FET", "fee", FeeCategory.FET),
        ("segment fees", "fee", FeeCategory.SEGMENT_FEES),
        ("VAT", "fee", FeeCategory.TAXES),
        ("Wi-Fi fee", "fee", FeeCategory.WIFI_FEE),
        ("internet usage", "fee", FeeCategory.WIFI_FEE),
    ],
)
def test_anchor_synonyms(text: str, kind: str, category: FeeCategory | None) -> None:
    anchors = match_anchors(f"{text} $100")
    assert len(anchors) == 1
    assert anchors[0].kind == kind
    assert anchors[0].category == category
    assert anchors[0].text.lower() == text.lower()


def test_longest_match_wins() -> None:
    [anchor] = match_anchors("crew overnight 700")
    assert anchor.category is FeeCategory.CREW_OVERNIGHT
    [anchor] = match_anchors("Fuel surcharge $1,400")
    assert anchor.text == "Fuel surcharge"


def test_whole_words_only() -> None:
    assert match_anchors("frontier ramping") == []
    assert [a.category for a in match_anchors("Ronald's fuelish")] == []


def test_adjacent_same_category_anchors_merge() -> None:
    [anchor] = match_anchors("Positioning (ferry KHPN-KTEB) $1,200")
    assert anchor.category is FeeCategory.POSITIONING
    assert anchor.text == "Positioning (ferry"


@pytest.mark.parametrize(
    ("text", "qualifier"),
    [
        ("included", Qualifier.INCLUDED),
        ("incl.", Qualifier.INCLUDED),
        ("complimentary", Qualifier.INCLUDED),
        ("no charge", Qualifier.INCLUDED),
        ("waived", Qualifier.WAIVED),
        ("extra", Qualifier.EXTRA),
        ("not included", Qualifier.EXTRA),
        ("excl.", Qualifier.EXTRA),
        ("on top", Qualifier.EXTRA),
        ("may", Qualifier.HEDGE),
        ("depending on", Qualifier.HEDGE),
        ("subject to", Qualifier.HEDGE),
        ("if required", Qualifier.HEDGE),
        ("TBD", Qualifier.HEDGE),
        ("at cost", Qualifier.HEDGE),
        ("est.", Qualifier.ESTIMATE),
        ("approximately", Qualifier.ESTIMATE),
        ("~", Qualifier.ESTIMATE),
        ("up to", Qualifier.ESTIMATE),
        ("all in", Qualifier.ALL_IN),
        ("all-inclusive", Qualifier.ALL_IN),
        ("incl. standard charges", Qualifier.ALL_IN),
    ],
)
def test_qualifiers(text: str, qualifier: Qualifier) -> None:
    [match] = match_qualifiers(f"fuel {text} 850")
    assert match.qualifier is qualifier


def test_not_included_beats_included() -> None:
    [match] = match_qualifiers("Catering not included")
    assert match.qualifier is Qualifier.EXTRA
    [match] = match_qualifiers("Catering excl. from price")
    assert match.qualifier is Qualifier.EXTRA


def test_month_may_is_not_a_hedge() -> None:
    assert match_qualifiers("Departs May 5") == []
    assert [q.qualifier for q in match_qualifiers("fuel may be extra")] == [
        Qualifier.HEDGE,
        Qualifier.EXTRA,
    ]
