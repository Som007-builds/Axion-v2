"""Provider cooldown state."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable


class CooldownTracker:
    """Temporarily skip providers that failed hard.

    The clock is injectable so tests can advance time without sleeping.
    """

    def __init__(
        self,
        window_s: float,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._window_s = max(0.0, window_s)
        self._clock = clock
        self._until: dict[str, float] = {}
        self._lock = threading.Lock()

    def is_cooling(self, provider: str) -> bool:
        with self._lock:
            until = self._until.get(provider, 0.0)
        return self._clock() < until

    def mark_failed(self, provider: str) -> None:
        with self._lock:
            self._until[provider] = self._clock() + self._window_s

    def reset(self) -> None:
        with self._lock:
            self._until.clear()
