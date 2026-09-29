"""Static FX table and airport reference data."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.services import airports
from app.services.fx import UnknownCurrency, load_fx_table, rate_for, to_usd_cents


def test_table_loads_and_caches() -> None:
    table = load_fx_table()
    assert table.base == "USD" and table.as_of == date(2026, 9, 1)
    assert table.rates["EUR"] == Decimal("1.08")
    assert table.knows("USD") and table.knows("GBP") and not table.knows("XYZ")
    assert load_fx_table() is table


def test_custom_path(tmp_path: Path) -> None:
    p = tmp_path / "fx.json"
    p.write_text('{"base": "USD", "as_of": "2026-01-02", "rates": {"JPY": "0.0067"}}')
    table = load_fx_table(p)
    assert to_usd_cents(1_000_000, "JPY", table) == 670_000  # JPY has no minor unit


@pytest.mark.parametrize(
    ("minor", "ccy", "cents"),
    [
        (4_180_000, "USD", 4_180_000),
        (3_250_000, "EUR", 3_510_000),
        (100, "GBP", 127),
        (1, "EUR", 1),  # 1.08 cents rounds half-up to 1
        (50, "MXN", 3),  # 2.75 -> 3
        (1_000, "cad", 730),
    ],
)
def test_to_usd_cents(minor: int, ccy: str, cents: int) -> None:
    assert to_usd_cents(minor, ccy, load_fx_table()) == cents


def test_unknown_currency() -> None:
    with pytest.raises(UnknownCurrency) as exc:
        to_usd_cents(100, "XYZ", load_fx_table())
    assert exc.value.currency == "XYZ"
    with pytest.raises(UnknownCurrency):
        rate_for("ABC", load_fx_table())


REQUIRED = [
    "KTEB", "KOPF", "KMIA", "KHPN", "KBED", "KPBI", "KVNY", "KLAS", "KASE",
    "KORD", "KBOS", "KSFO", "KDAL", "MYNN", "CYYZ", "EGGW", "LFPB",
]  # fmt: skip


def test_airports_cover_required_codes() -> None:
    table = airports.load_airports()
    assert set(REQUIRED) <= set(table)
    for code in REQUIRED:
        info = table[code]
        assert info.city and info.country and info.tz and -90 <= info.lat <= 90


def test_airport_attributes() -> None:
    teb = airports.get_airport("KTEB")
    assert teb is not None and teb.is_us and teb.deice_zone and teb.tz == "America/New_York"
    opf = airports.get_airport("kopf")
    assert opf is not None and not opf.deice_zone
    nas = airports.get_airport("MYNN")
    assert nas is not None and nas.country == "BS" and not nas.is_us
    assert airports.get_airport("LFPB").deice_zone  # type: ignore[union-attr]


def test_lookup_by_iata_and_faa() -> None:
    assert airports.get_airport("TEB").icao == "KTEB"  # type: ignore[union-attr]
    assert airports.get_airport("LBG").icao == "LFPB"  # type: ignore[union-attr]
    assert airports.get_airport("ZZZZ") is None
    assert airports.get_airport("") is None
    assert airports.timezone_for("OPF") == "America/New_York"
    assert airports.timezone_for("nope") is None


def test_search_ranks_codes_first() -> None:
    results = airports.search_airports("teb")
    assert results[0].icao == "KTEB"
    miami = [a.icao for a in airports.search_airports("miami", limit=10)]
    assert {"KMIA", "KOPF", "KTMB"} <= set(miami)
    assert airports.search_airports("", limit=5) == []
    assert len(airports.search_airports("K", limit=3)) == 3


def test_airports_for_and_distance() -> None:
    found = airports.airports_for(["KTEB", "OPF", "XXXX"])
    assert set(found) == {"KTEB", "KOPF"}
    nm = airports.distance_nm(found["KTEB"], found["KOPF"])
    assert 940 < nm < 960
