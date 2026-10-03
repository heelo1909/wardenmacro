"""Find the real Roblox client window and confirm/obtain focus.

The selection logic (``pick_client``) is pure so it can be tested with
mocked window lists; ``Win32Windows`` is the real enumeration backend.
"""

from __future__ import annotations

import ctypes
import logging
import sys
import time
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

from warden.geometry import Rect

log = logging.getLogger(__name__)

CLIENT_PROCESS = "robloxplayerbeta.exe"  # Windows
CLIENT_PROCESS_MAC = "robloxplayer"      # macOS: RobloxPlayer.app/Contents/MacOS/RobloxPlayer
# Anything that is a browser (or another app) must never be targeted, even if titled "Roblox".
BROWSER_CLASSES = frozenset({
    "Chrome_WidgetWin_0",
    "Chrome_WidgetWin_1",   # Chrome, Edge, Brave, Opera, Electron apps
    "MozillaWindowClass",   # Firefox
    "ApplicationFrameWindow",
    "IEFrame",
})
BROWSER_PROCESSES = frozenset({
    # Windows
    "chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe", "vivaldi.exe", "iexplore.exe",
    # macOS (psutil process names, lowercased)
    "google chrome", "safari", "firefox", "microsoft edge", "brave browser", "opera", "vivaldi",
})
UPDATER_PROCESSES = frozenset({"robloxplayerlauncher.exe", "robloxplayerinstaller.exe"})
UPDATER_TITLE_HINTS = ("roblox", "bootstrapper", "updat", "install")


def client_process_names() -> frozenset[str]:
    """The lowercase process name(s) that count as 'the real Roblox client' on
    this OS. macOS gets its own name; every other platform (including this
    project's Linux dev/test sandbox) falls back to the Windows one, which is
    what the existing tests' fixtures already assume.
    """
    if sys.platform == "darwin":
        return frozenset({CLIENT_PROCESS_MAC})
    return frozenset({CLIENT_PROCESS})


@dataclass(frozen=True)
class WindowInfo:
    hwnd: int
    title: str
    class_name: str
    process_name: str  # lowercase exe name, "" if unknown
    pid: int
    visible: bool = True
    minimized: bool = False
    client: Rect = Rect(0, 0, 0, 0)  # physical screen px


class WindowBackend(Protocol):
    def list_windows(self) -> list[WindowInfo]: ...
    def foreground(self) -> int: ...
    def focus(self, hwnd: int) -> bool: ...
    def refresh(self, hwnd: int) -> WindowInfo | None: ...


def is_browser(win: WindowInfo) -> bool:
    return win.class_name in BROWSER_CLASSES or win.process_name in BROWSER_PROCESSES


def pick_client(windows: Iterable[WindowInfo], client_processes: Iterable[str] | None = None) -> WindowInfo | None:
    """The Roblox game client: right process, not a browser, visible, biggest client area."""
    names = frozenset(client_processes) if client_processes is not None else client_process_names()
    candidates = [
        w for w in windows
        if w.process_name in names and not is_browser(w) and w.visible
    ]
    if not candidates:
        return None
    # A restored window beats a minimized one; then the largest client area.
    return max(candidates, key=lambda w: (not w.minimized, w.client.area))


def pick_updater(windows: Iterable[WindowInfo]) -> WindowInfo | None:
    for w in windows:
        if not w.visible or is_browser(w):
            continue
        if w.process_name in UPDATER_PROCESSES:
            return w
    return None


def pick_browser_with_title(windows: Iterable[WindowInfo], needle: str) -> WindowInfo | None:
    """For the browser fallback: a browser window whose title mentions ``needle``."""
    needle = needle.lower()
    for w in windows:
        if w.visible and is_browser(w) and needle in w.title.lower():
            return w
    return None


# --------------------------------------------------------------------------- focus gate


class FocusGate:
    """Input is only allowed while the Roblox client is confirmed foreground."""

    def __init__(self, backend: WindowBackend):
        self.backend = backend
        self.hwnd: int = 0

    def set_target(self, hwnd: int) -> None:
        self.hwnd = hwnd

    def is_focused(self) -> bool:
        return bool(self.hwnd) and self.backend.foreground() == self.hwnd

    def refocus(self) -> bool:
        if not self.hwnd:
            return False
        try:
            return bool(self.backend.focus(self.hwnd))
        except Exception:
            log.exception("refocus failed")
            return False


# --------------------------------------------------------------------------- Win32 backend


class Win32Windows:
    """Real window enumeration via user32 + psutil."""

    def __init__(self):
        if sys.platform != "win32":
            raise OSError("Win32Windows requires Windows")
        from ctypes import wintypes

        self._wt = wintypes
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._proc_names: dict[int, str] = {}
        u, H = self._user32, wintypes.HWND
        # Explicit signatures: 64-bit handles must not be truncated to C int.
        for name, args, res in (
            ("IsWindow", [H], wintypes.BOOL),
            ("IsWindowVisible", [H], wintypes.BOOL),
            ("IsIconic", [H], wintypes.BOOL),
            ("GetWindowTextLengthW", [H], ctypes.c_int),
            ("GetWindowTextW", [H, wintypes.LPWSTR, ctypes.c_int], ctypes.c_int),
            ("GetClassNameW", [H, wintypes.LPWSTR, ctypes.c_int], ctypes.c_int),
            ("GetWindowThreadProcessId", [H, ctypes.POINTER(wintypes.DWORD)], wintypes.DWORD),
            ("GetClientRect", [H, ctypes.POINTER(wintypes.RECT)], wintypes.BOOL),
            ("ClientToScreen", [H, ctypes.POINTER(wintypes.POINT)], wintypes.BOOL),
            ("GetForegroundWindow", [], H),
            ("SetForegroundWindow", [H], wintypes.BOOL),
            ("BringWindowToTop", [H], wintypes.BOOL),
            ("ShowWindow", [H, ctypes.c_int], wintypes.BOOL),
            ("PostMessageW", [H, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM], wintypes.BOOL),
            ("SetWindowPos", [H, H, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT], wintypes.BOOL),
            ("GetCursorPos", [ctypes.POINTER(wintypes.POINT)], wintypes.BOOL),
        ):
            fn = getattr(u, name)
            fn.argtypes, fn.restype = args, res

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

    def _info(self, hwnd: int) -> WindowInfo | None:
        u, wt = self._user32, self._wt
        if not u.IsWindow(hwnd):
            return None
        length = u.GetWindowTextLengthW(hwnd)
        title_buf = ctypes.create_unicode_buffer(length + 1)
        u.GetWindowTextW(hwnd, title_buf, length + 1)
        cls_buf = ctypes.create_unicode_buffer(256)
        u.GetClassNameW(hwnd, cls_buf, 256)
        pid = wt.DWORD()
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        rect = wt.RECT()
        u.GetClientRect(hwnd, ctypes.byref(rect))
        origin = wt.POINT(0, 0)
        u.ClientToScreen(hwnd, ctypes.byref(origin))
        return WindowInfo(
            hwnd=int(hwnd),
            title=title_buf.value,
            class_name=cls_buf.value,
            process_name=self._process_name(pid.value),
            pid=pid.value,
            visible=bool(u.IsWindowVisible(hwnd)),
            minimized=bool(u.IsIconic(hwnd)),
            client=Rect(origin.x, origin.y, rect.right - rect.left, rect.bottom - rect.top),
        )

    def list_windows(self) -> list[WindowInfo]:
        handles: list[int] = []
        proc_type = ctypes.WINFUNCTYPE(ctypes.c_bool, self._wt.HWND, self._wt.LPARAM)

        def _cb(hwnd, _lparam):
            if hwnd:
                handles.append(hwnd)
            return True

        self._user32.EnumWindows(proc_type(_cb), 0)
        out = []
        for hwnd in handles:
            info = self._info(hwnd)
            if info is not None:
                out.append(info)
        return out

    def refresh(self, hwnd: int) -> WindowInfo | None:
        return self._info(hwnd)

    def foreground(self) -> int:
        return int(self._user32.GetForegroundWindow() or 0)

    def focus(self, hwnd: int, timeout: float = 0.6) -> bool:
        u = self._user32
        if u.IsIconic(hwnd):
            u.ShowWindow(hwnd, 9)  # SW_RESTORE
        # Windows refuses SetForegroundWindow from background processes unless the
        # last input came from us; a harmless ALT tap satisfies that rule.
        u.keybd_event(0x12, 0, 0, 0)
        u.keybd_event(0x12, 0, 2, 0)
        u.SetForegroundWindow(hwnd)
        u.BringWindowToTop(hwnd)
        if self.foreground() != hwnd:
            # Stronger fallback: briefly share input state with whichever
            # thread owns the foreground window, which Windows accepts as
            # "the user's last input came from us".
            try:
                kernel32 = ctypes.WinDLL("kernel32")
                fg = u.GetForegroundWindow()
                fg_thread = u.GetWindowThreadProcessId(fg, None) if fg else 0
                me = kernel32.GetCurrentThreadId()
                if fg_thread and fg_thread != me:
                    u.AttachThreadInput(me, fg_thread, True)
                    try:
                        u.SetForegroundWindow(hwnd)
                        u.BringWindowToTop(hwnd)
                    finally:
                        u.AttachThreadInput(me, fg_thread, False)
            except Exception:
                log.debug("AttachThreadInput focus fallback failed", exc_info=True)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.foreground() == hwnd:
                return True
            time.sleep(0.05)
        return self.foreground() == hwnd

    def send_close(self, hwnd: int) -> None:
        self._user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE

    def move_window(self, hwnd: int, x: int, y: int) -> None:
        self._user32.SetWindowPos(hwnd, None, x, y, 0, 0, 0x0001 | 0x0004 | 0x0010)  # NOSIZE|NOZORDER|NOACTIVATE

    def cursor_pos(self) -> tuple[int, int]:
        pt = self._wt.POINT()
        self._user32.GetCursorPos(ctypes.byref(pt))
        return pt.x, pt.y


# --------------------------------------------------------------------------- backend factory


def make_window_backend() -> WindowBackend:
    """The real ``WindowBackend`` for whatever OS this is actually running on.

    Every caller that used to hardcode ``Win32Windows()`` goes through this
    instead, so Warden picks the right backend (and fails with a clear,
    actionable message instead of an OS error) on macOS too.
    """
    if sys.platform == "win32":
        return Win32Windows()
    if sys.platform == "darwin":
        try:
            from warden.platform.window_mac import MacWindows

            return MacWindows()
        except ImportError as exc:
            raise OSError(
                "macOS window support needs the pyobjc packages - install with:\n"
                "  pip install pyobjc-framework-Quartz pyobjc-framework-Cocoa"
            ) from exc
    raise OSError(f"Warden doesn't support this OS yet ({sys.platform}) - only Windows and macOS are supported")
