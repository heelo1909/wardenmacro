"""Sleep prevention during an active session (HANDOFF section 8.5).

``SetThreadExecutionState`` with ``ES_CONTINUOUS`` is sticky - it stays in
effect until explicitly cleared, so ``release()`` must always be called to
restore normal power behavior, even if the session ends abnormally.
"""

from __future__ import annotations

import ctypes
import logging
import sys

log = logging.getLogger(__name__)

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002


class SleepGuard:
    """``with SleepGuard(): ...`` or manual ``acquire()``/``release()``."""

    def __init__(self, keep_display_on: bool = True):
        self.keep_display_on = keep_display_on
        self._active = False

    def acquire(self) -> bool:
        if sys.platform != "win32":
            log.info("sleep prevention requested on non-Windows platform; ignoring")
            return False
        flags = ES_CONTINUOUS | ES_SYSTEM_REQUIRED
        if self.keep_display_on:
            flags |= ES_DISPLAY_REQUIRED
        result = ctypes.windll.kernel32.SetThreadExecutionState(flags)
        self._active = result != 0
        if not self._active:
            log.warning("SetThreadExecutionState failed to prevent sleep")
        return self._active

    def release(self) -> None:
        if sys.platform == "win32" and self._active:
            ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
        self._active = False

    @property
    def active(self) -> bool:
        return self._active

    def __enter__(self) -> "SleepGuard":
        self.acquire()
        return self

    def __exit__(self, *exc) -> None:
        self.release()
