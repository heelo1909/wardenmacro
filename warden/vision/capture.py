"""Grab the Roblox client area only (BGR uint8 numpy arrays)."""

from __future__ import annotations

import sys
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

    def _quartz_capture(self, hwnd: int, width: int, height: int, rect: Rect | None = None) -> np.ndarray | None:
        """macOS equivalent of ``_print_window``: ``CGWindowListCreateImage``
        rasterizes a window by its id regardless of what's on top of it or
        whether it's covered - same "capture by handle, not by screen region"
        trick as PrintWindow, needed for the exact same reason (Warden's own
        window, or anything else, sitting on top of Roblox). Requires the
        macOS "Screen Recording" permission; with it missing this (quietly,
        like everything else here) returns None and ``grab()`` falls back to
        a plain screen capture instead of raising.
        """
        if sys.platform != "darwin" or not hwnd or width <= 0 or height <= 0:
            return None
        try:
            import Quartz
        except ImportError:
            return None
        # With a window id plus kCGWindowListOptionIncludingWindow, the screen
        # rect only *clips* that one window's image - so passing the content
        # rect (title bar already trimmed by MacWindows) captures just the game
        # area, still unaffected by anything stacked on top. CGRectNull = the
        # whole window frame (used when no rect is known).
        bounds = Quartz.CGRectNull
        if rect is not None and not rect.is_empty():
            bounds = Quartz.CGRectMake(rect.left, rect.top, rect.width, rect.height)
        image = Quartz.CGWindowListCreateImage(
            bounds,
            Quartz.kCGWindowListOptionIncludingWindow,
            hwnd,
            Quartz.kCGWindowImageBoundsIgnoreFraming | Quartz.kCGWindowImageBestResolution,
        )
        if image is None:
            return None
        return _cgimage_to_bgr(Quartz, image, width, height)

    def grab(self, rect: Rect) -> np.ndarray:
        frame = None
        try:
            if sys.platform == "win32":
                frame = self._print_window(self.hwnd, rect.width, rect.height)
            elif sys.platform == "darwin":
                frame = self._quartz_capture(self.hwnd, rect.width, rect.height, rect)
        except Exception:
            frame = None
        if frame is not None:
            self.last_method = "window"
            return frame
        self.last_method = "screen"
        frame = self.fallback.grab(rect)
        if sys.platform == "darwin":
            frame = to_point_size(frame, rect.width, rect.height)
        return frame


def to_point_size(frame: np.ndarray, want_w: int, want_h: int) -> np.ndarray:
    """macOS: a Retina capture (pixels, 2x) scaled down to the window's size in
    points, so every frame Warden sees on a Mac is in the same units as the
    window rect and click coordinates, whichever capture path produced it.
    A frame already at point size (scale 1) is returned untouched.
    """
    if frame is None or want_w <= 0 or want_h <= 0:
        return frame
    h, w = frame.shape[:2]
    if (w, h) == (want_w, want_h):
        return frame
    import cv2

    return cv2.resize(frame, (want_w, want_h), interpolation=cv2.INTER_AREA)


def _cgimage_to_bgr(quartz, image, want_w: int, want_h: int) -> np.ndarray | None:
    """A CGImageRef's raw pixels as a BGR ``np.ndarray`` cropped/resized to
    ``(want_w, want_h)``. Split out from ``_quartz_capture`` so the byte-layout
    logic can be exercised by tests with a fake image object, without pyobjc
    installed (see tests/test_capture.py's FakeCGImage).
    """
    px_w, px_h = int(quartz.CGImageGetWidth(image)), int(quartz.CGImageGetHeight(image))
    if px_w <= 0 or px_h <= 0:
        return None
    provider = quartz.CGImageGetDataProvider(image)
    buf = bytes(quartz.CGDataProviderCopyData(provider))
    bytes_per_row = int(quartz.CGImageGetBytesPerRow(image))
    if bytes_per_row < px_w * 4 or len(buf) < bytes_per_row * px_h:
        return None
    arr = np.frombuffer(buf, dtype=np.uint8, count=bytes_per_row * px_h).reshape(px_h, bytes_per_row)
    arr = arr[:, : px_w * 4].reshape(px_h, px_w, 4)
    # CGWindowListCreateImage is 32-bit-little-endian/alpha-first, i.e. B,G,R,A
    # in increasing memory address order - the same byte layout this file's
    # Windows path already assumes (GetDIBits' BGRA), so the same "drop the
    # last channel" slice applies. If real hardware ever shows swapped red/
    # blue, flip this to [:, :, [2, 1, 0]] instead.
    frame = np.ascontiguousarray(arr[:, :, :3])
    # Retina displays return pixels at up to 2x the window's point size.
    frame = to_point_size(frame, want_w, want_h)
    if not frame.any():
        return None
    return frame


def find_roblox_client():
    """(hwnd, client Rect) of the Roblox client window, or None."""
    from warden.platform import dpi
    from warden.platform.window import make_window_backend, pick_client

    dpi.ensure_dpi_awareness()
    client = pick_client(make_window_backend().list_windows())
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
        from warden.platform.window import make_window_backend

        try:
            make_window_backend().focus(hwnd)
            time.sleep(0.35)
        except Exception:
            pass
    capturer = WindowCapturer()
    capturer.hwnd = hwnd
    frame = capturer.grab(rect)
    grab_roblox_client.last_method = capturer.last_method
    return frame


grab_roblox_client.last_method = "none"
