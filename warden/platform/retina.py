"""Screen pixels vs. click points on macOS (Retina backing scale).

macOS reports window bounds, cursor positions and CGEvent click locations in
*points*. Screen captures come back in *pixels*, which is 2x the point size
on a Retina display (1x on a regular one). Every conversion between the two
goes through the small pure helpers here, so they can be unit tested at scale
1 and 2 without a Mac.

Windows never calls this module: Warden's Windows side is DPI-aware and
already works in physical pixels everywhere (see ``platform/dpi.py``).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from warden.geometry import Rect


@dataclass(frozen=True)
class Display:
    """One attached display, in global points (top-left origin, like CGDisplayBounds)."""

    bounds: Rect
    scale: float = 1.0  # backing scale factor: 2.0 on Retina, 1.0 otherwise


def backing_scale(pixel_size: int, point_size: int) -> float:
    """The scale implied by an image of ``pixel_size`` px covering ``point_size`` pt.

    Rounded to the nearest 0.5 (real values are 1.0, 2.0 and, rarely, 1.5 or 3.0),
    and never below 1.0. Returns 1.0 for anything degenerate.
    """
    if pixel_size <= 0 or point_size <= 0:
        return 1.0
    raw = pixel_size / point_size
    return max(1.0, round(raw * 2) / 2)


def pixel_to_point(x: float, y: float, scale: float) -> tuple[int, int]:
    """A position inside a captured frame (pixels) -> the same spot in points."""
    s = scale if scale > 0 else 1.0
    return int(round(x / s)), int(round(y / s))


def point_to_pixel(x: float, y: float, scale: float) -> tuple[int, int]:
    """A position in points -> the matching pixel in a captured frame."""
    s = scale if scale > 0 else 1.0
    return int(round(x * s)), int(round(y * s))


def rect_to_pixels(rect: Rect, scale: float) -> Rect:
    s = scale if scale > 0 else 1.0
    return Rect(int(round(rect.left * s)), int(round(rect.top * s)),
                int(round(rect.width * s)), int(round(rect.height * s)))


def frame_px_to_screen_pt(x: float, y: float, client: Rect, scale: float) -> tuple[int, int]:
    """A pixel inside a capture of ``client`` (a rect in points) -> a global click point."""
    px, py = pixel_to_point(x, y, scale)
    return client.left + px, client.top + py


def display_for(rect: Rect, displays: Iterable[Display]) -> Display | None:
    """The display containing the centre of ``rect`` (the one the window is 'on')."""
    cx = rect.left + rect.width / 2
    cy = rect.top + rect.height / 2
    for d in displays:
        b = d.bounds
        if b.left <= cx < b.left + b.width and b.top <= cy < b.top + b.height:
            return d
    return None


def covers_display(rect: Rect, display: Display | None, slack_pt: int = 2) -> bool:
    """True when a window fills its whole display (macOS fullscreen: no title bar)."""
    if display is None:
        return False
    b = display.bounds
    return (abs(rect.left - b.left) <= slack_pt and abs(rect.top - b.top) <= slack_pt
            and rect.width >= b.width - slack_pt and rect.height >= b.height - slack_pt)


def content_rect(window: Rect, display: Display | None, title_bar_pt: int) -> Rect:
    """The game's content area inside a macOS window frame.

    Quartz reports the whole window frame, title bar included; Windows'
    ``GetClientRect`` (what the rest of Warden is written against) reports
    content only. A fullscreen window has no title bar, so nothing is trimmed.
    """
    if title_bar_pt <= 0 or covers_display(window, display) or window.height <= title_bar_pt:
        return window
    return Rect(window.left, window.top + title_bar_pt, window.width, window.height - title_bar_pt)
