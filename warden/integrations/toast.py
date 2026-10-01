"""Windows toast notifications (HANDOFF section 8.13). Optional dependency
(``winotify``) - degrades to a no-op (returns False) rather than crashing
when it isn't installed.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

log = logging.getLogger(__name__)


def _default_backend():
    try:
        from winotify import Notification
    except ImportError:
        return None
    return Notification


class ToastNotifier:
    def __init__(self, enabled: bool = True, app_name: str = "Warden",
                 backend_factory: Callable[[], type | None] = _default_backend):
        self.enabled = enabled
        self.app_name = app_name
        self._backend_factory = backend_factory

    def available(self) -> bool:
        return self._backend_factory() is not None

    def notify(self, title: str, message: str) -> bool:
        if not self.enabled:
            return False
        backend = self._backend_factory()
        if backend is None:
            log.info("toast skipped (winotify not installed): %s - %s", title, message)
            return False
        try:
            backend(app_id=self.app_name, title=title, msg=message, duration="short").show()
            return True
        except Exception:
            log.exception("toast notification failed")
            return False
