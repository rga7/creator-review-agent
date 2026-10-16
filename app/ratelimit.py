"""Per-process rate limits. With several workers, each keeps its own counts."""

from __future__ import annotations

import threading
import time
from collections import deque

_SWEEP_EVERY_S = 60.0

_lock = threading.Lock()
_hits: dict[str, deque] = {}
_windows: dict[str, float] = {}
_last_sweep = 0.0


class RateLimitExceeded(Exception):
    def __init__(self, retry_after: float):
        self.retry_after = retry_after
        super().__init__(f"rate limit exceeded, retry after {retry_after:.1f}s")


def _prune(key: str, now: float, window: float) -> deque:
    q = _hits.setdefault(key, deque())
    _windows[key] = window
    cutoff = now - window
    while q and q[0] < cutoff:
        q.popleft()
    return q


def _sweep(now: float) -> None:
    global _last_sweep
    if now - _last_sweep < _SWEEP_EVERY_S:
        return
    _last_sweep = now
    for key in [k for k, q in _hits.items()
                if not q or q[-1] < now - _windows.get(k, 0.0)]:
        _hits.pop(key, None)
        _windows.pop(key, None)


def check(key: str, max_hits: int, window_seconds: float) -> None:
    now = time.monotonic()
    with _lock:
        _sweep(now)
        q = _prune(key, now, window_seconds)
        if len(q) >= max_hits:
            raise RateLimitExceeded(max(window_seconds - (now - q[0]), 0.1))
        q.append(now)


def blocked(key: str, max_hits: int, window_seconds: float) -> float:
    """Seconds until the key is free again, 0.0 if it already is."""
    now = time.monotonic()
    with _lock:
        q = _hits.get(key)
        if not q:
            return 0.0
        cutoff = now - window_seconds
        live = [t for t in q if t >= cutoff]
        if len(live) < max_hits:
            return 0.0
        return max(window_seconds - (now - live[0]), 0.1)


def record(key: str, window_seconds: float) -> None:
    now = time.monotonic()
    with _lock:
        _sweep(now)
        _prune(key, now, window_seconds).append(now)


def reset() -> None:
    global _last_sweep
    with _lock:
        _hits.clear()
        _windows.clear()
        _last_sweep = 0.0
