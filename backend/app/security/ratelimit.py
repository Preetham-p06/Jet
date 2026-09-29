"""Rate limiting behind a protocol, so the in-process limiter can move to Redis."""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    allowed: bool
    remaining: int
    retry_after_s: int


class RateLimiter(Protocol):
    def hit(self, key: str, *, limit: int, window_s: int) -> RateLimitDecision:
        """Record one attempt for `key` and say whether it is within the limit."""
        ...

    def reset(self, key: str | None = None) -> None:
        """Forget one key, or everything."""
        ...


class InMemoryRateLimiter:
    """Sliding-window log limiter. Correct for a single process only."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str, *, limit: int, window_s: int) -> RateLimitDecision:
        now = self._clock()
        cutoff = now - window_s
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if len(hits) >= limit:
                retry = max(1, int(hits[0] + window_s - now) + 1)
                return RateLimitDecision(allowed=False, remaining=0, retry_after_s=retry)
            hits.append(now)
            return RateLimitDecision(allowed=True, remaining=limit - len(hits), retry_after_s=0)

    def reset(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._hits.clear()
            else:
                self._hits.pop(key, None)
