"""Sleep prevention during an active session (HANDOFF section 8.5).

``SetThreadExecutionState`` with ``ES_CONTINUOUS`` is sticky - it stays in
effect until explicitly cleared, so ``release()`` must always be called to
restore normal power behavior, even if the session ends abnormally.
"""

from __future__ import annotations

import ctypes
import logging
import subprocess
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
        self._mac_proc: subprocess.Popen | None = None

    def acquire(self) -> bool:
        if sys.platform == "darwin":
            return self._acquire_mac()
        if sys.platform != "win32":
            log.info("sleep prevention requested on unsupported platform (%s); ignoring", sys.platform)
            return False
        flags = ES_CONTINUOUS | ES_SYSTEM_REQUIRED
        if self.keep_display_on:
            flags |= ES_DISPLAY_REQUIRED
        result = ctypes.windll.kernel32.SetThreadExecutionState(flags)
        self._active = result != 0
        if not self._active:
            log.warning("SetThreadExecutionState failed to prevent sleep")
        return self._active

    def _acquire_mac(self) -> bool:
        """`caffeinate` ships with macOS; holding it open prevents sleep for as
        long as the process lives, which ``release()`` ends by terminating it -
        the same "sticky until cleared" shape as the Windows API above.
        """
        if self._mac_proc is not None and self._mac_proc.poll() is None:
            return True
        args = ["caffeinate", "-i"]  # -i: prevent idle/app sleep
        if self.keep_display_on:
            args.append("-d")  # -d: also prevent display sleep
        try:
            self._mac_proc = subprocess.Popen(args)
            self._active = True
        except Exception:
            log.warning("caffeinate unavailable; sleep may not be prevented", exc_info=True)
            self._active = False
        return self._active

    def release(self) -> None:
        if sys.platform == "darwin":
            if self._mac_proc is not None:
                self._mac_proc.terminate()
                self._mac_proc = None
            self._active = False
            return
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
