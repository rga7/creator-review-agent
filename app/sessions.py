"""Session store: idle expiry, a size cap, and server-issued ids only."""

from __future__ import annotations

import threading
import time
import uuid
from typing import Callable

from .state import SessionState


class SessionStore:
    def __init__(self, ttl_s: float, max_sessions: int,
                 clock: Callable[[], float] = time.monotonic):
        self._ttl, self._max, self._clock = ttl_s, max_sessions, clock
        self._items: dict[str, SessionState] = {}
        self._lock = threading.Lock()

    def __len__(self) -> int:
        return len(self._items)

    def _expire(self, now: float) -> None:
        for sid in [s for s, st in self._items.items() if now - st.last_seen > self._ttl]:
            del self._items[sid]

    def get(self, sid: str | None) -> SessionState | None:
        if not sid:
            return None
        with self._lock:
            now = self._clock()
            st = self._items.get(sid)
            if st is None:
                return None
            if now - st.last_seen > self._ttl:
                del self._items[sid]
                return None
            st.last_seen = now
            return st

    def create(self) -> SessionState:
        with self._lock:
            now = self._clock()
            self._expire(now)
            while len(self._items) >= self._max:
                oldest = min(self._items, key=lambda s: self._items[s].last_seen)
                del self._items[oldest]
            st = SessionState(session_id=uuid.uuid4().hex, last_seen=now)
            self._items[st.session_id] = st
            return st

    def drop(self, sid: str | None) -> None:
        with self._lock:
            self._items.pop(sid or "", None)
