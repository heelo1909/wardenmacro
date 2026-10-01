"""Client-area geometry. Every position in config is a fraction of the client area.

Rects are in *physical* screen pixels (the process is per-monitor DPI aware),
so fraction -> pixel is a plain multiply regardless of Windows scaling.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Rect:
    left: int
    top: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height

    @property
    def area(self) -> int:
        return self.width * self.height

    def is_empty(self) -> bool:
        return self.width <= 0 or self.height <= 0

    def contains(self, x: float, y: float) -> bool:
        return self.left <= x < self.right and self.top <= y < self.bottom

    def intersects(self, other: Rect) -> bool:
        return not (
            other.left >= self.right
            or other.right <= self.left
            or other.top >= self.bottom
            or other.bottom <= self.top
        )

    # -- fractions ---------------------------------------------------------

    def frac_to_px(self, fx: float, fy: float) -> tuple[int, int]:
        """Client fraction -> absolute screen pixel (rounded, clamped inside the rect)."""
        x = self.left + min(max(fx, 0.0), 1.0) * self.width
        y = self.top + min(max(fy, 0.0), 1.0) * self.height
        return (min(int(round(x)), self.right - 1), min(int(round(y)), self.bottom - 1))

    def px_to_frac(self, x: float, y: float) -> tuple[float, float]:
        return ((x - self.left) / self.width, (y - self.top) / self.height)

    def roi_px(self, roi: tuple[float, float, float, float] | list[float]) -> tuple[int, int, int, int]:
        """ROI fractions -> (x1, y1, x2, y2) pixels *relative to the client origin* (for array slicing)."""
        x1, y1, x2, y2 = roi
        return (
            int(round(x1 * self.width)),
            int(round(y1 * self.height)),
            max(int(round(x2 * self.width)), int(round(x1 * self.width)) + 1),
            max(int(round(y2 * self.height)), int(round(y1 * self.height)) + 1),
        )


def frame_rect(frame) -> Rect:
    """A Rect at the origin matching an image array (h, w[, c])."""
    h, w = frame.shape[:2]
    return Rect(0, 0, w, h)
