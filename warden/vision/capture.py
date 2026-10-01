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
