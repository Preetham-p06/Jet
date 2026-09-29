"""Rate limiting behind a protocol, so the in-process limiter can move to Redis."""

from __future__ import annotations

import math
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final, Protocol

#: Failures older than this are forgotten.
FAILURE_TTL_S: Final = 15 * 60
MAX_FAILURE_KEYS: Final = 10_000


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
        """Forget one key (hits and failures), or everything."""
        ...

    def record_failure(self, key: str) -> None:
        """Count one failure for `key` (a failed login for an account)."""
        ...

    def backoff_s(self, key: str, *, free_failures: int, max_backoff_s: int) -> int:
        """Seconds `key` must still wait: 0 for the first `free_failures` failures,
        then 1, 2, 4 ... seconds after the latest one, capped at `max_backoff_s`.
        Failures are never a lockout: the wait is short and ends on its own."""
        ...


class InMemoryRateLimiter:
    """Sliding-window log limiter. Correct for a single process only."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}
        self._failures: dict[str, tuple[int, float]] = {}  # key -> (count, latest)
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
                self._failures.clear()
            else:
                self._hits.pop(key, None)
                self._failures.pop(key, None)

    def record_failure(self, key: str) -> None:
        now = self._clock()
        with self._lock:
            count, latest = self._failures.get(key, (0, 0.0))
            if now - latest > FAILURE_TTL_S:
                count = 0
            self._failures[key] = (count + 1, now)
            if len(self._failures) > MAX_FAILURE_KEYS:
                stale = [k for k, (_, t) in self._failures.items() if now - t > FAILURE_TTL_S]
                for k in stale:
                    del self._failures[k]

    def backoff_s(self, key: str, *, free_failures: int, max_backoff_s: int) -> int:
        with self._lock:
            count, latest = self._failures.get(key, (0, 0.0))
        if count < free_failures:
            return 0
        delay = min(1 << min(count - free_failures, 16), max_backoff_s)
        remaining = latest + delay - self._clock()
        return max(0, math.ceil(remaining))
