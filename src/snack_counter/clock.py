from __future__ import annotations

from datetime import datetime


class Clock:
    def now(self) -> datetime:
        return datetime.utcnow()


class FrozenClock(Clock):
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now

    def set(self, now: datetime) -> None:
        self._now = now

    def advance(self, **kwargs) -> datetime:
        from datetime import timedelta

        self._now = self._now + timedelta(**kwargs)
        return self._now
