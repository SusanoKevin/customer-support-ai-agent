"""In-memory sliding-window limiter (log P1).

One process holds the counts, which matches the single backend instance the in-memory
sessions already require (L12). A shared store such as Redis would replace this behind the
same `hit` / `check` / `add` methods once sessions move out of memory.
"""

import time
from collections.abc import Callable


class SlidingWindowLimiter:
    """At most `limit` hits per key in any `window_s` seconds."""

    def __init__(self, limit: int, window_s: float, clock: Callable[[], float] = time.monotonic) -> None:
        self._limit = limit
        self._window_s = window_s
        self._clock = clock
        self._hits: dict[str, tuple[float, ...]] = {}

    @property
    def tracked_keys(self) -> int:
        return len(self._hits)

    def check(self, key: str) -> float | None:
        """Seconds until the next hit is allowed, or None if one is allowed now. Records nothing."""
        now = self._clock()
        self._prune(now)
        hits = self._hits.get(key, ())
        if len(hits) < self._limit:
            return None
        return hits[0] + self._window_s - now

    def add(self, key: str) -> None:
        now = self._clock()
        self._prune(now)
        self._hits = {**self._hits, key: (*self._hits.get(key, ()), now)}

    def hit(self, key: str) -> float | None:
        """Records the hit only when it is allowed."""
        wait = self.check(key)
        if wait is None:
            self.add(key)
        return wait

    def _prune(self, now: float) -> None:
        """Drops expired hits, and keys with none left, so memory follows active clients only."""
        cutoff = now - self._window_s
        kept = {k: tuple(t for t in ts if t > cutoff) for k, ts in self._hits.items()}
        self._hits = {k: ts for k, ts in kept.items() if ts}
