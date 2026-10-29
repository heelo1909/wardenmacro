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
  against) is content-only. So a windowed Roblox window has ``title_bar_pt``
  (config ``mac.title_bar_pt``, default 28) trimmed off the top; a window
  that fills its display (fullscreen) is left whole. If the display list
  can't be read, nothing is trimmed (the pre-port behavior).
- All bounds are in *points*. Captures come back in pixels (2x on Retina);
  ``platform/retina.py`` holds the conversions.
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
from warden.platform import retina
from warden.platform.window import WindowInfo

log = logging.getLogger(__name__)

_NORMAL_WINDOW_LAYER = 0  # kCGWindowLayer value for an ordinary app window (menu bar/dock/etc use others)

# Set once at startup from config (``mac.title_bar_pt``) by ``platform.macos.configure``.
TITLE_BAR_PT = 28


class MacWindows:
    """Real window enumeration via Quartz's CGWindowList + AppKit's NSRunningApplication."""

    def __init__(self, title_bar_pt: int | None = None):
        if sys.platform != "darwin":
            raise OSError("MacWindows requires macOS")
        self.title_bar_pt = TITLE_BAR_PT if title_bar_pt is None else title_bar_pt
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

    def displays(self) -> list[retina.Display]:
        """Attached displays in global points, with their backing scale. [] if unreadable."""
        cg = self._cg
        try:
            err, ids, count = cg.CGGetActiveDisplayList(16, None, None)
            if err:
                return []
            out = []
            for did in list(ids)[: int(count)]:
                b = cg.CGDisplayBounds(did)
                bounds = Rect(int(b.origin.x), int(b.origin.y), int(b.size.width), int(b.size.height))
                scale = 1.0
                mode = cg.CGDisplayCopyDisplayMode(did)
                if mode is not None:
                    scale = retina.backing_scale(int(cg.CGDisplayModeGetPixelWidth(mode)), bounds.width)
                out.append(retina.Display(bounds, scale))
            return out
        except Exception:
            log.debug("display list unavailable", exc_info=True)
            return []

    def _raw_list(self, onscreen_only: bool) -> list[dict]:
        cg = self._cg
        opt = cg.kCGWindowListOptionOnScreenOnly if onscreen_only else cg.kCGWindowListOptionAll
        opt |= cg.kCGWindowListExcludeDesktopElements
        return list(cg.CGWindowListCopyWindowInfo(opt, cg.kCGNullWindowID) or [])

    def _info(self, raw: dict, displays: list[retina.Display] | None = None) -> WindowInfo | None:
        number = raw.get("kCGWindowNumber")
        if number is None:
            return None
        bounds = raw.get("kCGWindowBounds") or {}
        frame = Rect(int(bounds.get("X", 0)), int(bounds.get("Y", 0)),
                     int(bounds.get("Width", 0)), int(bounds.get("Height", 0)))
        client = frame
        if displays:  # unknown displays -> can't tell fullscreen from windowed; leave as-is
            client = retina.content_rect(frame, retina.display_for(frame, displays), self.title_bar_pt)
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
            client=client,
        )

    def _normal_windows(self, onscreen_only: bool) -> list[dict]:
        return [raw for raw in self._raw_list(onscreen_only)
                if raw.get("kCGWindowLayer", 0) == _NORMAL_WINDOW_LAYER]

    def list_windows(self) -> list[WindowInfo]:
        out = []
        displays = self.displays()
        for raw in self._normal_windows(onscreen_only=False):
            info = self._info(raw, displays)
            if info is not None:
                out.append(info)
        return out

    def refresh(self, hwnd: int) -> WindowInfo | None:
        for raw in self._normal_windows(onscreen_only=False):
            if raw.get("kCGWindowNumber") == hwnd:
                return self._info(raw, self.displays())
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
