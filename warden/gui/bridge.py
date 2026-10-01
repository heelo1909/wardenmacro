"""Thread-safe bridge from the EventBus (fired from the tick thread) to Qt widgets.

``EventBus.emit`` calls subscriber callbacks synchronously on whichever
thread published the event - usually ``TickLoop``'s background thread, never
the GUI thread. Touching a QWidget off the GUI thread is undefined
behavior, so every event is re-emitted as a Qt signal; Qt auto-queues a
signal emitted from one thread to a slot that lives on another (this
object lives on the GUI thread since it's constructed there), which is
exactly the hand-off we need.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from warden.core.events import Event, EventBus, Level


class BusBridge(QObject):
    event = Signal(object)  # carries an Event

    def __init__(self, bus: EventBus, min_level: Level | str = Level.DEBUG, parent=None):
        super().__init__(parent)
        self._bus = bus
        self._token = bus.subscribe(self._on_event, min_level=min_level)

    def _on_event(self, event: Event) -> None:
        self.event.emit(event)

    def close(self) -> None:
        self._bus.unsubscribe(self._token)
