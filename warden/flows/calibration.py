"""Calibration backend (HANDOFF section 7.4 / 8.8): capture a region as a
template, sample an HSV range from it, adjust a detector's ROI, and turn an
unknown-gallery frame into a new template. Kept separate from
``gui/pages/calibration.py`` so all of it is testable without Qt.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import numpy as np

from warden.config.schema import ROI, DetectorConfig, HSVRange
from warden.geometry import frame_rect
from warden.vision import color
from warden.vision.templates import TemplateLibrary

log = logging.getLogger(__name__)

CALIBRATION_SCREENS = (
    "lobby_play", "mode_list", "ffa_tile", "health_bar", "respawn_prompt",
    "weapon_picker", "switch_weapons", "match_end", "disconnect_modal",
)


def sample_hsv_from_selection(
    frame: np.ndarray, roi: tuple[float, float, float, float], margin: tuple[int, int, int] = (8, 50, 50),
) -> tuple[list[int], list[int]]:
    return color.sample_hsv(frame, roi, margin)


def crop_frame(frame: np.ndarray, roi: tuple[float, float, float, float]) -> np.ndarray:
    rect = frame_rect(frame)
    x1, y1, x2, y2 = rect.roi_px(roi)
    return frame[y1:y2, x1:x2]


def save_template_from_frame(templates: TemplateLibrary, path: str, frame: np.ndarray,
                              roi: tuple[float, float, float, float]) -> Path:
    return templates.save(path, crop_frame(frame, roi))


def apply_roi(detector: DetectorConfig, roi: tuple[float, float, float, float]) -> DetectorConfig:
    return detector.model_copy(update={"roi": ROI(x1=roi[0], y1=roi[1], x2=roi[2], y2=roi[3])})


def apply_hsv(detector: DetectorConfig, lower: list[int], upper: list[int]) -> DetectorConfig:
    return detector.model_copy(update={"hsv": [HSVRange(lower=tuple(lower), upper=tuple(upper))]})


def px_rect_to_fractions(x1: float, y1: float, x2: float, y2: float, width: float, height: float
                          ) -> tuple[float, float, float, float]:
    """A drag-selection in pixels (over a possibly-scaled-down thumbnail of size
    ``width`` x ``height``) -> client-area fractions, normalized so x1<x2, y1<y2.
    """
    fx1, fx2 = sorted((x1 / width, x2 / width))
    fy1, fy2 = sorted((y1 / height, y2 / height))
    clamp = lambda v: min(max(v, 0.0), 1.0)  # noqa: E731
    fx1, fx2, fy1, fy2 = clamp(fx1), clamp(fx2), clamp(fy1), clamp(fy2)
    if fx2 <= fx1:
        fx2 = min(fx1 + 0.001, 1.0)
    if fy2 <= fy1:
        fy2 = min(fy1 + 0.001, 1.0)
    return (fx1, fy1, fx2, fy2)


# --------------------------------------------------------------------------- unknown gallery


def list_unknown_frames(unknown_dir: Path) -> list[Path]:
    return sorted(Path(unknown_dir).glob("*.png"), reverse=True)  # newest first


def make_template_from_unknown(templates: TemplateLibrary, unknown_path: Path, template_path: str,
                                roi: tuple[float, float, float, float]):
    import cv2

    frame = cv2.imread(str(unknown_path))
    if frame is None:
        raise ValueError(f"unreadable unknown frame: {unknown_path}")
    return save_template_from_frame(templates, template_path, frame, roi)


# --------------------------------------------------------------------------- contract OCR verification


_HOURS_PATTERN = re.compile(
    r"(?:(?P<days>\d+)\s*d)?\s*(?P<hours>\d+)\s*h\s*(?P<minutes>\d+)\s*m", re.IGNORECASE
)


def parse_contract_hours(text: str | None) -> float | None:
    """Parse a readout like '12h 53m / 1d 0h 0m' into the *first* duration's hours.

    The game's own progress counter is what's being read here (not any
    macro's UI) - format assumed is 'Hh Mm' optionally preceded by 'Dd'.
    """
    if not text:
        return None
    match = _HOURS_PATTERN.search(text)
    if not match:
        return None
    days = int(match.group("days") or 0)
    hours = int(match.group("hours"))
    minutes = int(match.group("minutes"))
    return days * 24 + hours + minutes / 60.0
