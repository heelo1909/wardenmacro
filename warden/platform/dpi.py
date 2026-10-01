"""Per-monitor DPI awareness and scaling report.

Qt 6 already makes the GUI process per-monitor-v2 aware; CLI tools call
``ensure_dpi_awareness()`` themselves. Either way Win32 rects are physical px.
"""

from __future__ import annotations

import ctypes
import sys
from dataclasses import dataclass

from warden.geometry import Rect

IS_WINDOWS = sys.platform == "win32"
_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)


def ensure_dpi_awareness() -> str:
    """Make this process per-monitor DPI aware. Returns which API succeeded."""
    if not IS_WINDOWS:
        return "n/a"
    user32 = ctypes.windll.user32
    try:
        if user32.SetProcessDpiAwarenessContext(_PER_MONITOR_AWARE_V2):
            return "per-monitor-v2"
    except (AttributeError, OSError):
        pass
    try:
        if ctypes.windll.shcore.SetProcessDpiAwareness(2) == 0:
            return "per-monitor"
    except (AttributeError, OSError):
        pass
    try:
        if user32.SetProcessDPIAware():
            return "system"
    except (AttributeError, OSError):
        pass
    return current_awareness()


def current_awareness() -> str:
    if not IS_WINDOWS:
        return "n/a"
    try:
        ctx = ctypes.windll.user32.GetThreadDpiAwarenessContext()
        awareness = ctypes.windll.user32.GetAwarenessFromDpiAwarenessContext(ctypes.c_void_p(ctx))
        return {0: "unaware", 1: "system", 2: "per-monitor"}.get(awareness, f"unknown({awareness})")
    except (AttributeError, OSError):
        return "unknown"


def window_scale(hwnd: int) -> float:
    """Windows scaling for the monitor a window is on (1.0 = 100%)."""
    if not IS_WINDOWS or not hwnd:
        return 1.0
    try:
        dpi = ctypes.windll.user32.GetDpiForWindow(hwnd)
        return dpi / 96.0 if dpi else 1.0
    except (AttributeError, OSError):
        return 1.0


def to_logical(px: float, scale: float) -> float:
    return px / scale


def to_physical(logical: float, scale: float) -> float:
    return logical * scale


def logical_rect_to_physical(rect: Rect, scale: float) -> Rect:
    return Rect(
        int(round(rect.left * scale)),
        int(round(rect.top * scale)),
        int(round(rect.width * scale)),
        int(round(rect.height * scale)),
    )


@dataclass
class MonitorInfo:
    rect: Rect
    scale: float
    primary: bool


def monitors() -> list[MonitorInfo]:
    if not IS_WINDOWS:
        return []
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    result: list[MonitorInfo] = []

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                    ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]

    proc_type = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HMONITOR, wintypes.HDC,
                                   ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)

    def _cb(hmon, _hdc, _rect, _lparam):
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        user32.GetMonitorInfoW(hmon, ctypes.byref(info))
        r = info.rcMonitor
        dpi_x, dpi_y = wintypes.UINT(), wintypes.UINT()
        scale = 1.0
        try:
            if ctypes.windll.shcore.GetDpiForMonitor(hmon, 0, ctypes.byref(dpi_x), ctypes.byref(dpi_y)) == 0:
                scale = dpi_x.value / 96.0
        except (AttributeError, OSError):
            pass
        result.append(MonitorInfo(Rect(r.left, r.top, r.right - r.left, r.bottom - r.top), scale, bool(info.dwFlags & 1)))
        return 1

    user32.EnumDisplayMonitors(None, None, proc_type(_cb), 0)
    return result
