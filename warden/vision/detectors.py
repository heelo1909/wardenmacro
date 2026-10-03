"""High-level detectors: config -> a yes/no (plus confidence) per tick.

Each detector tracks its own ``confirm_frames`` run so a single flickery
frame never counts; ``reset()`` clears that run (used e.g. once a disconnect
modal vanishes before it was confirmed).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np

from warden.config.schema import DetectorConfig
from warden.geometry import frame_rect
from warden.vision import color, ocr
from warden.vision.templates import Match, TemplateLibrary, match_template

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Detection:
    name: str
    hit: bool
    confirmed: bool  # hit AND seen for confirm_frames in a row
    confidence: float
    box: tuple[float, float, float, float] | None = None
    text: str | None = None
    streak: int = 0


@dataclass
class Detector:
    name: str
    config: DetectorConfig
    templates: TemplateLibrary | None = None
    _streak: int = field(default=0, init=False)

    def reset(self) -> None:
        self._streak = 0

    def evaluate(self, frame: np.ndarray) -> Detection:
        if not self.config.enabled:
            return Detection(self.name, False, False, 0.0, streak=0)
        hit, confidence, box, text = self._raw(frame)
        self._streak = self._streak + 1 if hit else 0
        confirmed = hit and self._streak >= self.config.confirm_frames
        return Detection(self.name, hit, confirmed, confidence, box, text, self._streak)

    def _raw(self, frame: np.ndarray) -> tuple[bool, float, tuple | None, str | None]:
        method = self.config.method
        if method == "color":
            return self._color(frame)
        if method == "template":
            return self._template(frame)
        if method == "ocr":
            return self._ocr_only(frame)
        if method == "composite":
            return self._composite(frame)
        # "window" and "frozen" are evaluated out-of-band (see WindowDetector / FrozenDetector).
        return (False, 0.0, None, None)

    def _color(self, frame: np.ndarray) -> tuple[bool, float, tuple | None, str | None]:
        cfg = self.config
        blobs = color.find_blobs(frame, cfg.roi.as_list(), cfg.hsv, cfg.min_area, cfg.max_area,
                                  cfg.aspect_min, cfg.aspect_max)
        if not blobs and cfg.fallback_hsv:
            blobs = color.find_blobs(frame, cfg.roi.as_list(), cfg.fallback_hsv, cfg.min_area, cfg.max_area,
                                      cfg.aspect_min, cfg.aspect_max)
        if not blobs:
            return (False, 0.0, None, None)
        best = blobs[0]
        text = None
        if cfg.ocr is not None:
            text = self._ocr_crop(frame, best.box)
            if not ocr.contains_any(text, cfg.ocr.contains) and ocr.available():
                return (False, 0.0, best.box, text)
        return (True, min(best.fill, 1.0), best.box, text)

    def _template(self, frame: np.ndarray) -> tuple[bool, float, tuple | None, str | None]:
        cfg = self.config
        if cfg.template is None or self.templates is None:
            return (False, 0.0, None, None)
        tmpl = self.templates.get(cfg.template.path)
        if tmpl is None:
            return (False, 0.0, None, None)
        base = frame.shape[0] / cfg.template.ref_height if cfg.template.ref_height else 1.0
        match: Match | None = match_template(
            frame, tmpl, cfg.roi.as_list(), cfg.template.scale_min, cfg.template.scale_max, cfg.template.scale_steps,
            base_scale=base,
        )
        if match is None or match.score < cfg.template.threshold:
            score = match.score if match else 0.0
            return (False, score, match.box if match else None, None)
        text = self._ocr_crop(frame, match.box) if cfg.ocr is not None else None
        if cfg.ocr is not None and not ocr.contains_any(text, cfg.ocr.contains) and ocr.available():
            return (False, match.score, match.box, text)
        return (True, match.score, match.box, text)

    def _ocr_only(self, frame: np.ndarray) -> tuple[bool, float, tuple | None, str | None]:
        if self.config.ocr is None:
            return (False, 0.0, None, None)
        box = self.config.roi.as_list()
        text = self._ocr_crop(frame, box)
        hit = ocr.contains_any(text, self.config.ocr.contains)
        return (hit, 1.0 if hit else 0.0, tuple(box), text)

    def _composite(self, frame: np.ndarray) -> tuple[bool, float, tuple | None, str | None]:
        """Modal dialog: dimmed/low-variance surround plus the configured OCR phrase."""
        cfg = self.config
        box = cfg.roi.as_list()
        text = self._ocr_crop(frame, box)
        if cfg.ocr is not None:
            hit = ocr.contains_any(text, cfg.ocr.contains)
            return (hit, 1.0 if hit else 0.0, tuple(box), text)
        return (False, 0.0, None, text)

    def _ocr_crop(self, frame: np.ndarray, box) -> str | None:
        rect = frame_rect(frame)
        x1, y1, x2, y2 = rect.roi_px(box)
        psm = self.config.ocr.psm if self.config.ocr else 7
        return ocr.read_text(frame[y1:y2, x1:x2], psm=psm)


def build_detectors(configs: dict[str, DetectorConfig], templates: TemplateLibrary) -> dict[str, Detector]:
    return {name: Detector(name, cfg, templates) for name, cfg in configs.items()}


# --------------------------------------------------------------------------- non-vision detectors


class FrozenDetector:
    """True once the frame's perceptual hash hasn't changed for ``seconds``."""

    def __init__(self, seconds: float = 30.0, hash_size: int = 8, threshold: int = 3,
                 clock=None):
        import time

        self.seconds = seconds
        self.hash_size = hash_size
        self.threshold = threshold
        self.clock = clock or time.monotonic
        self._last_hash: np.ndarray | None = None
        self._since: float = self.clock()

    @staticmethod
    def _phash(frame: np.ndarray, size: int) -> np.ndarray:
        import cv2

        small = cv2.resize(frame if frame.ndim == 2 else cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (size, size))
        return (small > small.mean()).astype(np.uint8)

    def evaluate(self, frame: np.ndarray) -> Detection:
        h = self._phash(frame, self.hash_size)
        now = self.clock()
        if self._last_hash is None or int(np.count_nonzero(h != self._last_hash)) > self.threshold:
            self._last_hash = h
            self._since = now
            return Detection("frozen", False, False, 0.0)
        elapsed = now - self._since
        hit = elapsed >= self.seconds
        return Detection("frozen", hit, hit, min(elapsed / self.seconds, 1.0))

    def reset(self) -> None:
        self._last_hash = None


class WindowStateDetector:
    """Wraps window-backend facts (updater window / process gone) as a Detection."""

    def __init__(self, name: str, check):
        self.name = name
        self.check = check  # callable -> bool

    def evaluate(self, _frame: np.ndarray | None = None) -> Detection:
        hit = bool(self.check())
        return Detection(self.name, hit, hit, 1.0 if hit else 0.0)

    def reset(self) -> None:
        pass
