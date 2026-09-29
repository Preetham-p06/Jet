"""Airport reference data from `data/airports.json` (ICAO, IATA, city, country, tz,
lat/lon, de-ice zone). Lookups accept ICAO or IATA/FAA codes, case-insensitively."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType

from app.services.contracts import AirportInfo

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "airports.json"
EARTH_RADIUS_NM = 3440.065


@lru_cache(maxsize=4)
def _load(path: Path) -> Mapping[str, AirportInfo]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, AirportInfo] = {}
    for r in rows:
        info = AirportInfo(
            icao=str(r["icao"]).upper(),
            iata=(str(r["iata"]).upper() if r.get("iata") else None),
            name=str(r["name"]),
            city=str(r["city"]),
            country=str(r["country"]).upper(),
            tz=str(r["tz"]),
            lat=float(r["lat"]),
            lon=float(r["lon"]),
            deice_zone=bool(r.get("deice_zone", False)),
        )
        out[info.icao] = info
    return MappingProxyType(out)


@lru_cache(maxsize=4)
def _alias_index(path: Path) -> Mapping[str, str]:
    index: dict[str, str] = {}
    for icao, info in _load(path).items():
        if info.iata:
            index.setdefault(info.iata, icao)
        # FAA location identifiers of contiguous-US airports drop the leading "K".
        if info.is_us and len(icao) == 4 and icao.startswith("K"):
            index.setdefault(icao[1:], icao)
    return MappingProxyType(index)


def load_airports(path: Path | None = None) -> Mapping[str, AirportInfo]:
    """All airports by ICAO (cached)."""
    return _load((path or DEFAULT_PATH).resolve())


def get_airport(code: str) -> AirportInfo | None:
    """By ICAO, or by IATA/FAA code (e.g. "TEB" -> KTEB)."""
    key = code.strip().upper()
    if not key:
        return None
    table = load_airports()
    if key in table:
        return table[key]
    icao = _alias_index(DEFAULT_PATH.resolve()).get(key)
    return table.get(icao) if icao else None


def timezone_for(code: str) -> str | None:
    """IANA zone of the airport, used to default `trip_legs.depart_tz`."""
    info = get_airport(code)
    return info.tz if info else None


def search_airports(query: str, *, limit: int = 10) -> list[AirportInfo]:
    """Prefix match on codes, substring match on name and city; codes rank first."""
    q = query.strip()
    if not q or limit <= 0:
        return []
    upper, folded = q.upper(), q.casefold()
    exact: list[AirportInfo] = []
    prefix: list[AirportInfo] = []
    text: list[AirportInfo] = []
    for info in load_airports().values():
        codes = [c for c in (info.icao, info.iata) if c]
        if upper in codes:
            exact.append(info)
        elif any(c.startswith(upper) for c in codes):
            prefix.append(info)
        elif folded in info.name.casefold() or folded in info.city.casefold():
            text.append(info)
    ordered = exact + prefix + text
    return ordered[:limit]


def airports_for(codes: list[str]) -> dict[str, AirportInfo]:
    """The known subset of `codes`, keyed by ICAO (for `TripContext.airports`)."""
    out: dict[str, AirportInfo] = {}
    for code in codes:
        info = get_airport(code)
        if info is not None:
            out[info.icao] = info
    return out


def distance_nm(a: AirportInfo, b: AirportInfo) -> float:
    """Great-circle distance in nautical miles."""
    lat1, lon1, lat2, lon2 = map(math.radians, (a.lat, a.lon, b.lat, b.lon))
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_NM * math.asin(math.sqrt(h))
