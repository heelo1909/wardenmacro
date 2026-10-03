"""macOS window enumeration/focus backend (Quartz + AppKit via pyobjc).

Mirrors ``Win32Windows`` (platform/window.py) behind the same ``WindowBackend``
protocol, so every OS-agnostic piece - ``pick_client``, ``FocusGate``, the
state machine, the whole tick loop - works unchanged on macOS. Reached only
through ``window.make_window_backend()``; never imported at module load time
anywhere else, since pyobjc doesn't exist on Windows/Linux.

Caveats (not verified on real hardware - this project is developed and tested
without a Mac; see README's macOS section for what to check first):

- ``CGWindowListCopyWindowInfo`` reports a window's full frame, title bar
  included. Win32's ``GetClientRect`` (what the rest of Warden was written
  against) is content-only. Playing Roblox in fullscreen avoids the
  difference entirely; in windowed mode, clicks/captures may be off by
  roughly a title bar's height.
- Capturing Roblox needs the "Screen Recording" OS permission; sending clicks
  and keystrokes needs "Accessibility" (System Settings -> Privacy &
  Security). Without them this backend doesn't error - it just finds no
  window / sends nothing, same as the rest of Warden's "degrade, don't
  crash" style elsewhere in this codebase.
- "minimized" has no exact equivalent here: a window CGWindowList can't see
  (minimized, on another Space, hidden) is just reported as not visible.
"""

from __future__ import annotations

import logging
import sys
import time

from warden.geometry import Rect
from warden.platform.window import WindowInfo

log = logging.getLogger(__name__)

_NORMAL_WINDOW_LAYER = 0  # kCGWindowLayer value for an ordinary app window (menu bar/dock/etc use others)


class MacWindows:
    """Real window enumeration via Quartz's CGWindowList + AppKit's NSRunningApplication."""

    def __init__(self):
        if sys.platform != "darwin":
            raise OSError("MacWindows requires macOS")
        import Quartz
        from AppKit import NSApplicationActivateIgnoringOtherApps, NSRunningApplication

        self._cg = Quartz
        self._running_app = NSRunningApplication
        self._activate_flags = NSApplicationActivateIgnoringOtherApps
        self._proc_names: dict[int, str] = {}

    def _process_name(self, pid: int) -> str:
        if pid in self._proc_names:
            return self._proc_names[pid]
        name = ""
        try:
            import psutil

            name = psutil.Process(pid).name().lower()
        except Exception:
            pass
        if len(self._proc_names) > 512:
            self._proc_names.clear()
        self._proc_names[pid] = name
        return name

    def _raw_list(self, onscreen_only: bool) -> list[dict]:
        cg = self._cg
        opt = cg.kCGWindowListOptionOnScreenOnly if onscreen_only else cg.kCGWindowListOptionAll
        opt |= cg.kCGWindowListExcludeDesktopElements
        return list(cg.CGWindowListCopyWindowInfo(opt, cg.kCGNullWindowID) or [])

    def _info(self, raw: dict) -> WindowInfo | None:
        number = raw.get("kCGWindowNumber")
        if number is None:
            return None
        bounds = raw.get("kCGWindowBounds") or {}
        pid = int(raw.get("kCGWindowOwnerPID", 0) or 0)
        onscreen = bool(raw.get("kCGWindowIsOnscreen", False))
        return WindowInfo(
            hwnd=int(number),
            title=str(raw.get("kCGWindowName", "") or ""),
            class_name="",  # macOS has no Win32-style window class
            process_name=self._process_name(pid),
            pid=pid,
            visible=onscreen,
            minimized=not onscreen,  # best-effort - see module docstring
            client=Rect(int(bounds.get("X", 0)), int(bounds.get("Y", 0)),
                        int(bounds.get("Width", 0)), int(bounds.get("Height", 0))),
        )

    def _normal_windows(self, onscreen_only: bool) -> list[dict]:
        return [raw for raw in self._raw_list(onscreen_only)
                if raw.get("kCGWindowLayer", 0) == _NORMAL_WINDOW_LAYER]

    def list_windows(self) -> list[WindowInfo]:
        out = []
        for raw in self._normal_windows(onscreen_only=False):
            info = self._info(raw)
            if info is not None:
                out.append(info)
        return out

    def refresh(self, hwnd: int) -> WindowInfo | None:
        for raw in self._normal_windows(onscreen_only=False):
            if raw.get("kCGWindowNumber") == hwnd:
                return self._info(raw)
        return None

    def _frontmost_pid(self) -> int:
        try:
            from AppKit import NSWorkspace

            app = NSWorkspace.sharedWorkspace().frontmostApplication()
            return int(app.processIdentifier()) if app is not None else 0
        except Exception:
            log.debug("frontmost app lookup failed", exc_info=True)
            return 0

    def foreground(self) -> int:
        pid = self._frontmost_pid()
        if not pid:
            return 0
        # CGWindowListCopyWindowInfo is returned front-to-back ordered, so the
        # first on-screen, normal-layer window owned by the frontmost app is
        # its key/main window - the closest match to Win32's GetForegroundWindow.
        for raw in self._normal_windows(onscreen_only=True):
            if int(raw.get("kCGWindowOwnerPID", 0) or 0) == pid:
                return int(raw.get("kCGWindowNumber", 0) or 0)
        return 0

    def focus(self, hwnd: int, timeout: float = 0.6) -> bool:
        info = self.refresh(hwnd)
        if info is None or not info.pid:
            return False
        try:
            app = self._running_app.runningApplicationWithProcessIdentifier_(info.pid)
            if app is None:
                return False
            app.activateWithOptions_(self._activate_flags)
        except Exception:
            log.exception("focus failed")
            return False
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.foreground() == hwnd:
                return True
            time.sleep(0.05)
        return self.foreground() == hwnd

    def send_close(self, hwnd: int) -> None:
        """Best-effort polite quit (like Cmd+Q) of the window's owning app.

        macOS has no per-window WM_CLOSE a background process can send
        without the Accessibility API; ``RobloxProcess.close()`` already
        falls back to killing the process if this doesn't finish in time.
        """
        info = self.refresh(hwnd)
        if info is None or not info.pid:
            return
        try:
            app = self._running_app.runningApplicationWithProcessIdentifier_(info.pid)
            if app is not None:
                app.terminate()
        except Exception:
            log.debug("send_close failed", exc_info=True)

    def move_window(self, hwnd: int, x: int, y: int) -> None:
        # Moving another app's window from the outside needs the Accessibility
        # (AXUIElement) API; nothing in Warden calls this today.
        log.debug("move_window is not implemented on macOS")

    def cursor_pos(self) -> tuple[int, int]:
        loc = self._cg.CGEventGetLocation(self._cg.CGEventCreate(None))
        return int(loc.x), int(loc.y)
