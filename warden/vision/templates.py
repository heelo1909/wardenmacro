"""Multi-scale template matching (fallback / anchor detector)."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from warden.geometry import frame_rect

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Match:
    score: float
    x1: float  # client fractions
    y1: float
    x2: float
    y2: float
    scale: float

    @property
    def center(self) -> tuple[float, float]:
        return ((self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2)

    @property
    def box(self) -> tuple[float, float, float, float]:
        return (self.x1, self.y1, self.x2, self.y2)


def _gray(img: np.ndarray) -> np.ndarray:
    return img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def match_template(
    frame: np.ndarray,
    template: np.ndarray,
    roi: Sequence[float] = (0, 0, 1, 1),
    scale_min: float = 0.75,
    scale_max: float = 1.25,
    scale_steps: int = 11,
    base_scale: float = 1.0,
) -> Match | None:
    """Best match over scales ``base_scale * [scale_min..scale_max]``. Returns None if nothing fits."""
    rect = frame_rect(frame)
    x1, y1, x2, y2 = rect.roi_px(roi)
    region = _gray(frame[y1:y2, x1:x2])
    tmpl = _gray(template)
    if region.size == 0 or tmpl.size == 0:
        return None
    scales = np.linspace(scale_min, scale_max, scale_steps) if scale_steps > 1 else np.array([1.0])
    best: Match | None = None
    for s in scales * base_scale:
        tw, th = int(round(tmpl.shape[1] * s)), int(round(tmpl.shape[0] * s))
        if tw < 6 or th < 6 or tw > region.shape[1] or th > region.shape[0]:
            continue
        interp = cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR
        scaled = cv2.resize(tmpl, (tw, th), interpolation=interp)
        if float(scaled.std()) < 1e-3:  # flat template -> normalized score undefined
            continue
        res = cv2.matchTemplate(region, scaled, cv2.TM_CCOEFF_NORMED)
        _, score, _, loc = cv2.minMaxLoc(res)
        if not np.isfinite(score):
            continue
        if best is None or score > best.score:
            mx, my = x1 + loc[0], y1 + loc[1]
            best = Match(
                score=float(score),
                x1=mx / rect.width, y1=my / rect.height,
                x2=(mx + tw) / rect.width, y2=(my + th) / rect.height,
                scale=float(s),
            )
    return best


class TemplateLibrary:
    """Loads template images relative to a base folder, reloading when the file changes."""

    def __init__(self, base: Path):
        self.base = Path(base)
        self._cache: dict[Path, tuple[float, np.ndarray]] = {}
        self._warned: set[Path] = set()

    def resolve(self, path: str) -> Path:
        p = Path(path)
        return p if p.is_absolute() else self.base / p

    def get(self, path: str) -> np.ndarray | None:
        full = self.resolve(path)
        try:
            mtime = full.stat().st_mtime
        except OSError:
            if full not in self._warned:
                log.info("template not captured yet: %s", full)
                self._warned.add(full)
            return None
        cached = self._cache.get(full)
        if cached and cached[0] == mtime:
            return cached[1]
        img = cv2.imread(str(full), cv2.IMREAD_COLOR)
        if img is None:
            log.warning("template unreadable: %s", full)
            return None
        self._cache[full] = (mtime, img)
        self._warned.discard(full)
        return img

    def save(self, path: str, image: np.ndarray) -> Path:
        full = self.resolve(path)
        full.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(full), image)
        self._cache.pop(full, None)
        return full
