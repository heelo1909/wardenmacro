"""HSV colour blob finder - the primary detector."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import cv2
import numpy as np

from warden.geometry import frame_rect


@dataclass(frozen=True)
class Blob:
    # all in client fractions
    x1: float
    y1: float
    x2: float
    y2: float
    area: float  # pixel area / client area
    fill: float  # pixel area / bounding-box area (1.0 = solid rectangle)

    @property
    def center(self) -> tuple[float, float]:
        return ((self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2)

    @property
    def box(self) -> tuple[float, float, float, float]:
        return (self.x1, self.y1, self.x2, self.y2)


def hsv_mask(hsv: np.ndarray, ranges: Sequence) -> np.ndarray:
    """OR of all ranges. A range whose lower H > upper H wraps through 0 (reds)."""
    mask = np.zeros(hsv.shape[:2], dtype=np.uint8)
    for r in ranges:
        lo, hi = (r.lower, r.upper) if hasattr(r, "lower") else r
        lo, hi = tuple(int(v) for v in lo), tuple(int(v) for v in hi)
        if lo[0] <= hi[0]:
            mask |= cv2.inRange(hsv, lo, hi)
        else:
            mask |= cv2.inRange(hsv, (0, lo[1], lo[2]), (hi[0], hi[1], hi[2]))
            mask |= cv2.inRange(hsv, (lo[0], lo[1], lo[2]), (179, hi[1], hi[2]))
    return mask


def find_blobs(
    frame: np.ndarray,
    roi: Sequence[float],
    ranges: Sequence,
    min_area: float = 0.0005,
    max_area: float = 0.25,
    aspect_min: float = 0.05,
    aspect_max: float = 50.0,
) -> list[Blob]:
    """Blobs of the given colour inside ``roi``, largest first. Areas are client fractions."""
    if not ranges:
        return []
    rect = frame_rect(frame)
    x1, y1, x2, y2 = rect.roi_px(roi)
    crop = frame[y1:y2, x1:x2]
    if crop.size == 0:
        return []
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    mask = hsv_mask(hsv, ranges)
    # Close small gaps (text on buttons, anti-aliasing) so one button = one blob.
    k = max(3, (min(crop.shape[:2]) // 120) | 1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((k, k), np.uint8))

    n, _labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    total = float(rect.area)
    blobs = []
    for i in range(1, n):
        bx, by, bw, bh, px = stats[i]
        area = px / total
        if not (min_area <= area <= max_area):
            continue
        aspect = bw / max(bh, 1)
        if not (aspect_min <= aspect <= aspect_max):
            continue
        blobs.append(Blob(
            x1=(x1 + bx) / rect.width,
            y1=(y1 + by) / rect.height,
            x2=(x1 + bx + bw) / rect.width,
            y2=(y1 + by + bh) / rect.height,
            area=area,
            fill=px / float(bw * bh),
        ))
    blobs.sort(key=lambda b: b.area, reverse=True)
    return blobs


def sample_hsv(frame: np.ndarray, box: Sequence[float], margin: Sequence[int] = (8, 50, 50)) -> tuple[list[int], list[int]]:
    """Calibration helper: an HSV range covering the central 60% of a box (fractions)."""
    rect = frame_rect(frame)
    x1, y1, x2, y2 = rect.roi_px(box)
    cx, cy = (x2 - x1) * 0.2, (y2 - y1) * 0.2
    crop = frame[int(y1 + cy):max(int(y2 - cy), int(y1 + cy) + 1), int(x1 + cx):max(int(x2 - cx), int(x1 + cx) + 1)]
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV).reshape(-1, 3).astype(int)
    lo = np.percentile(hsv, 5, axis=0)
    hi = np.percentile(hsv, 95, axis=0)
    limits = (179, 255, 255)
    lower = [int(max(0, lo[i] - margin[i])) for i in range(3)]
    upper = [int(min(limits[i], hi[i] + margin[i])) for i in range(3)]
    return lower, upper
