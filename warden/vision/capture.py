"""Grab the Roblox client area only (BGR uint8 numpy arrays)."""

from __future__ import annotations

import threading
import time
from typing import Protocol

import numpy as np

from warden.geometry import Rect


class Capturer(Protocol):
    def grab(self, rect: Rect) -> np.ndarray: ...


class MssCapturer:
    """mss handles are per-thread, so each thread lazily gets its own."""

    def __init__(self):
        self._local = threading.local()

    def _sct(self):
        sct = getattr(self._local, "sct", None)
        if sct is None:
            import mss

            factory = getattr(mss, "MSS", None) or mss.mss
            sct = factory()
            self._local.sct = sct
        return sct

    def grab(self, rect: Rect) -> np.ndarray:
        if rect.is_empty():
            raise ValueError("cannot capture an empty rect")
        shot = self._sct().grab({"left": rect.left, "top": rect.top, "width": rect.width, "height": rect.height})
        # BGRA -> BGR without an extra copy through cv2
        return np.ascontiguousarray(np.asarray(shot)[:, :, :3])


def measure_fps(capturer: Capturer, rect: Rect, seconds: float = 1.0) -> float:
    frames, start = 0, time.perf_counter()
    while time.perf_counter() - start < seconds:
        capturer.grab(rect)
        frames += 1
    return frames / (time.perf_counter() - start)


class WindowCapturer:
    """Captures the Roblox window's *own* pixels via ``PrintWindow``, so other
    windows on top of it (Warden itself, Discord, a browser, the calibration
    overlay) never end up in the frame. The first real run showed exactly
    that: Warden's own window covering the game got saved as an "unknown
    screen". Falls back to a plain screen grab (``MssCapturer``) for any frame
    PrintWindow can't produce (non-Windows, minimized window, driver quirk).

    Set ``hwnd`` to the client window before grabbing; ``grab(rect)`` keeps the
    same signature as ``MssCapturer`` so everything else is unchanged.
    """

    PW_CLIENTONLY = 0x1
    PW_RENDERFULLCONTENT = 0x2

    def __init__(self, fallback: Capturer | None = None):
        self.fallback = fallback or MssCapturer()
        self.hwnd: int = 0
        self.last_method = "none"  # "window" | "screen" - for diagnostics / calibration UX
        self._api = None

    def _win32(self):
        if self._api is None:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.WinDLL("user32", use_last_error=True)
            gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
            H = ctypes.c_void_p
            for fn, args, res in (
                (user32.GetDC, [wintypes.HWND], H),
                (user32.ReleaseDC, [wintypes.HWND, H], ctypes.c_int),
                (user32.PrintWindow, [wintypes.HWND, H, wintypes.UINT], wintypes.BOOL),
                (user32.IsIconic, [wintypes.HWND], wintypes.BOOL),
                (gdi32.CreateCompatibleDC, [H], H),
                (gdi32.CreateCompatibleBitmap, [H, ctypes.c_int, ctypes.c_int], H),
                (gdi32.SelectObject, [H, H], H),
                (gdi32.DeleteObject, [H], wintypes.BOOL),
                (gdi32.DeleteDC, [H], wintypes.BOOL),
                (gdi32.GetDIBits, [H, H, wintypes.UINT, wintypes.UINT, ctypes.c_void_p, ctypes.c_void_p,
                                   wintypes.UINT], ctypes.c_int),
            ):
                fn.argtypes, fn.restype = args, res

            class BITMAPINFOHEADER(ctypes.Structure):
                _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                            ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD),
                            ("biCompression", wintypes.DWORD), ("biSizeImage", wintypes.DWORD),
                            ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG),
                            ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]

            self._api = (ctypes, user32, gdi32, BITMAPINFOHEADER)
        return self._api

    def _print_window(self, hwnd: int, width: int, height: int) -> np.ndarray | None:
        import sys

        if sys.platform != "win32" or not hwnd or width <= 0 or height <= 0:
            return None
        ctypes, user32, gdi32, BIH = self._win32()
        if user32.IsIconic(hwnd):
            return None
        hdc = user32.GetDC(hwnd)
        if not hdc:
            return None
        mem = bmp = old = None
        try:
            mem = gdi32.CreateCompatibleDC(hdc)
            bmp = gdi32.CreateCompatibleBitmap(hdc, width, height)
            if not mem or not bmp:
                return None
            old = gdi32.SelectObject(mem, bmp)
            if not user32.PrintWindow(hwnd, mem, self.PW_CLIENTONLY | self.PW_RENDERFULLCONTENT):
                return None
            header = BIH()
            header.biSize = ctypes.sizeof(BIH)
            header.biWidth, header.biHeight = width, -height  # negative = top-down rows
            header.biPlanes, header.biBitCount, header.biCompression = 1, 32, 0  # BI_RGB
            buf = (ctypes.c_ubyte * (width * height * 4))()
            # GetDIBits wants the bitmap *not* selected into a DC.
            gdi32.SelectObject(mem, old)
            old = None
            lines = gdi32.GetDIBits(mem, bmp, 0, height, buf, ctypes.byref(header), 0)  # DIB_RGB_COLORS
            if lines != height:
                return None
            frame = np.frombuffer(buf, dtype=np.uint8).reshape(height, width, 4)[:, :, :3]
            frame = np.ascontiguousarray(frame)
            if not frame.any():  # all-zero = PrintWindow produced nothing usable
                return None
            return frame
        finally:
            if old:
                gdi32.SelectObject(mem, old)
            if bmp:
                gdi32.DeleteObject(bmp)
            if mem:
                gdi32.DeleteDC(mem)
            user32.ReleaseDC(hwnd, hdc)

    def grab(self, rect: Rect) -> np.ndarray:
        frame = None
        try:
            frame = self._print_window(self.hwnd, rect.width, rect.height)
        except Exception:
            frame = None
        if frame is not None:
            self.last_method = "window"
            return frame
        self.last_method = "screen"
        return self.fallback.grab(rect)


def find_roblox_client():
    """(hwnd, client Rect) of the Roblox client window, or None."""
    from warden.platform import dpi
    from warden.platform.window import Win32Windows, pick_client

    dpi.ensure_dpi_awareness()
    client = pick_client(Win32Windows().list_windows())
    if client is None or client.client.is_empty():
        return None
    return client.hwnd, client.client


def grab_roblox_client(focus: bool = False) -> np.ndarray | None:
    """One frame of the Roblox client, with no session running.

    Used by Calibration (no Start needed - starting a session that can't
    recognize the screens yet is exactly what kept relaunching the game).
    Uses window capture, so Warden's own window on top doesn't matter; with
    ``focus=True`` the client is brought to the front first, which only
    matters if window capture isn't available and a screen grab is used.
    Returns None if no client window is found.
    """
    found = find_roblox_client()
    if found is None:
        return None
    hwnd, rect = found
    if focus:
        from warden.platform.window import Win32Windows

        try:
            Win32Windows().focus(hwnd)
            time.sleep(0.35)
        except Exception:
            pass
    capturer = WindowCapturer()
    capturer.hwnd = hwnd
    frame = capturer.grab(rect)
    grab_roblox_client.last_method = capturer.last_method
    return frame


grab_roblox_client.last_method = "none"
