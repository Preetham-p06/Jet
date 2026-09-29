"""Enumerate the app's API routes.

FastAPI 0.142 keeps included routers nested (`_IncludedRouter`), so
`app.routes` alone lists only the docs routes. Walk the effective routes so
the meta-tests see every endpoint with its full path.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI
from fastapi.routing import APIRoute

from app.deps import role_gate_of
from app.models.enums import Role

try:  # FastAPI >= 0.140
    from fastapi.routing import _IncludedRouter
except ImportError:  # pragma: no cover - older FastAPI flattens routes
    _IncludedRouter = None  # type: ignore[assignment,misc]


@dataclass(frozen=True)
class RouteInfo:
    method: str
    path: str
    route: APIRoute

    @property
    def key(self) -> tuple[str, str]:
        return self.method, self.path

    def roles(self) -> frozenset[Role] | None:
        gates = [role_gate_of(d.call) for d in self.route.dependant.dependencies]
        found = [g for g in gates if g]
        return found[0] if found else None


def _walk(routes: Iterable[Any]) -> Iterator[tuple[str, Any]]:
    for route in routes:
        if _IncludedRouter is not None and isinstance(route, _IncludedRouter):
            for candidate in route.effective_candidates():
                if isinstance(candidate, _IncludedRouter):
                    yield from _walk([candidate])
                else:
                    yield candidate.path, candidate.original_route
        else:
            yield getattr(route, "path", ""), route


def api_routes(app: FastAPI) -> list[RouteInfo]:
    out = []
    for path, route in _walk(app.routes):
        if isinstance(route, APIRoute):
            out.extend(RouteInfo(m, path, route) for m in sorted(route.methods or ()))
    return out
