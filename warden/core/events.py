"""In-process event bus.

Everything that happens (state transitions, detections, retries, incidents)
is published here as an ``Event``. The GUI, log file, Discord and LAN
dashboard are all just subscribers. Publishing is thread-safe and a failing
subscriber never breaks the publisher or other subscribers.
"""

from __future__ import annotations

import itertools
import logging
import threading
import time
from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any

log = logging.getLogger(__name__)


class Level(IntEnum):
    # Ordered so filtering by "at least" works; SUCCESS sits between INFO and WARN.
    DEBUG = 10
    INFO = 20
    SUCCESS = 25
    WARN = 30
    ERROR = 40

    @classmethod
    def parse(cls, value: str | int | Level) -> Level:
        if isinstance(value, Level):
            return value
        if isinstance(value, int):
            return cls(value)
        name = value.strip().upper()
        return cls[{"WARNING": "WARN"}.get(name, name)]


@dataclass(frozen=True)
class Event:
    topic: str  # dotted, e.g. "state.transition", "detect.health_bar", "incident.open"
    message: str
    level: Level = Level.INFO
    data: dict[str, Any] = field(default_factory=dict)
    confidence: float | None = None
    ts: float = field(default_factory=time.time)
    seq: int = 0


Handler = Callable[[Event], None]


@dataclass
class _Subscription:
    handler: Handler
    min_level: Level
    topics: tuple[str, ...]  # prefixes; empty = everything

    def wants(self, event: Event) -> bool:
        if event.level < self.min_level:
            return False
        if not self.topics:
            return True
        return any(event.topic == t or event.topic.startswith(t + ".") for t in self.topics)


class EventBus:
    def __init__(self, history: int = 2000):
        self._subs: dict[int, _Subscription] = {}
        self._ids = itertools.count(1)
        self._seq = itertools.count(1)
        self._lock = threading.RLock()
        self._history: deque[Event] = deque(maxlen=history)

    def subscribe(
        self,
        handler: Handler,
        min_level: Level | str = Level.DEBUG,
        topics: Iterable[str] = (),
    ) -> int:
        """Register ``handler``; returns a token for ``unsubscribe``."""
        sub = _Subscription(handler, Level.parse(min_level), tuple(topics))
        with self._lock:
            token = next(self._ids)
            self._subs[token] = sub
        return token

    def unsubscribe(self, token: int) -> None:
        with self._lock:
            self._subs.pop(token, None)

    def emit(
        self,
        topic: str,
        message: str,
        level: Level | str = Level.INFO,
        confidence: float | None = None,
        **data: Any,
    ) -> Event:
        event = Event(
            topic=topic,
            message=message,
            level=Level.parse(level),
            data=data,
            confidence=confidence,
            seq=next(self._seq),
        )
        self.publish(event)
        return event

    def publish(self, event: Event) -> None:
        with self._lock:
            self._history.append(event)
            subs = list(self._subs.values())
        for sub in subs:
            if not sub.wants(event):
                continue
            try:
                sub.handler(event)
            except Exception:  # a broken subscriber must never stop the bot
                log.exception("event subscriber %r failed on %s", sub.handler, event.topic)

    def history(self, min_level: Level | str = Level.DEBUG) -> list[Event]:
        floor = Level.parse(min_level)
        with self._lock:
            return [e for e in self._history if e.level >= floor]


_default_bus: EventBus | None = None


def bus() -> EventBus:
    """Process-wide bus used by the app (tests create their own)."""
    global _default_bus
    if _default_bus is None:
        _default_bus = EventBus()
    return _default_bus
