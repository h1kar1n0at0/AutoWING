"""通知分级、去重和限流策略。"""

from __future__ import annotations

import time
from collections.abc import Callable

from app.notify.events import NotificationEvent, NotificationLevel


_LEVEL_ORDER = {
    NotificationLevel.INFO: 0,
    NotificationLevel.WARNING: 1,
    NotificationLevel.ERROR: 2,
}


class NotificationPolicy:
    def __init__(
        self,
        min_level: str = "warning",
        dedup_seconds: float = 60.0,
        rate_limit_seconds: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        try:
            self._min_level = NotificationLevel(min_level)
        except ValueError:
            self._min_level = NotificationLevel.WARNING
        self._dedup_seconds = max(0.0, dedup_seconds)
        self._rate_limit_seconds = max(0.0, rate_limit_seconds)
        self._clock = clock
        self._last_by_key: dict[tuple[str, str], float] = {}
        self._last_by_type: dict[str, float] = {}

    def accepts_level(self, level: NotificationLevel) -> bool:
        return _LEVEL_ORDER[level] >= _LEVEL_ORDER[self._min_level]

    def should_enqueue(self, event: NotificationEvent, now: float | None = None) -> bool:
        if not event.bypass_level_filter and not self.accepts_level(event.level):
            return False

        timestamp = self._clock() if now is None else now
        dedup_key = (event.event_type, event.dedup_key)
        last_key = self._last_by_key.get(dedup_key)
        if last_key is not None and timestamp - last_key < self._dedup_seconds:
            return False

        last_type = self._last_by_type.get(event.event_type)
        if last_type is not None and timestamp - last_type < self._rate_limit_seconds:
            return False

        self._last_by_key[dedup_key] = timestamp
        self._last_by_type[event.event_type] = timestamp
        self._expire(timestamp)
        return True

    def _expire(self, now: float) -> None:
        if self._dedup_seconds:
            self._last_by_key = {
                key: timestamp
                for key, timestamp in self._last_by_key.items()
                if now - timestamp < self._dedup_seconds
            }
        if self._rate_limit_seconds:
            self._last_by_type = {
                key: timestamp
                for key, timestamp in self._last_by_type.items()
                if now - timestamp < self._rate_limit_seconds
            }