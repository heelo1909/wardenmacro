"""Desktop toast/banner notifications (HANDOFF section 8.13). Windows uses the
optional ``winotify`` dependency; macOS needs nothing extra - ``osascript`` (a
native "display notification" via Notification Center) ships with the OS.
Either way this degrades to a no-op (returns False) rather than crashing if
the backend isn't available.
"""

from __future__ import annotations

import logging
import subprocess
import sys
from collections.abc import Callable

log = logging.getLogger(__name__)


class _MacNotification:
    """Shaped like ``winotify.Notification`` (same constructor kwargs, a
    ``.show()`` call) so ``ToastNotifier.notify`` doesn't need to care which
    backend it got.
    """

    def __init__(self, app_id: str = "", title: str = "", msg: str = "", duration: str = "short"):
        self.title = title
        self.msg = msg

    def show(self) -> None:
        script = f"display notification {_osa_quote(self.msg)} with title {_osa_quote(self.title)}"
        subprocess.run(["osascript", "-e", script], check=True,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)


def _osa_quote(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _default_backend():
    if sys.platform == "darwin":
        return _MacNotification
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
