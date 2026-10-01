"""Global hotkeys (work while Roblox has focus) via pynput."""

from __future__ import annotations

import logging
from collections.abc import Callable

log = logging.getLogger(__name__)


def to_pynput(combo: str) -> str:
    """'F6' -> '<f6>', 'ctrl+shift+s' -> '<ctrl>+<shift>+s'."""
    parts = []
    for part in combo.lower().replace(" ", "").split("+"):
        if len(part) == 1:
            parts.append(part)
        else:
            parts.append(f"<{part}>")
    return "+".join(parts)


class Hotkeys:
    def __init__(self, bindings: dict[str, Callable[[], None]]):
        """``bindings`` maps a combo like 'F8' to a callback."""
        self.bindings = bindings
        self._listener = None

    def start(self) -> bool:
        try:
            from pynput import keyboard
        except Exception as exc:
            log.warning("global hotkeys unavailable: %s", exc)
            return False
        mapping = {to_pynput(combo): self._safe(cb) for combo, cb in self.bindings.items() if combo}
        self._listener = keyboard.GlobalHotKeys(mapping)
        self._listener.daemon = True
        self._listener.start()
        return True

    @staticmethod
    def _safe(cb: Callable[[], None]) -> Callable[[], None]:
        def run():
            try:
                cb()
            except Exception:
                log.exception("hotkey handler failed")

        return run

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
