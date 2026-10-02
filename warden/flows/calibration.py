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


# --------------------------------------------------------------------------- preflight

# Detectors the lobby -> FFA -> match path can't work without. If any of these
# is template-based and its template was never captured, the state machine can
# never get past that screen - which used to show up as Warden endlessly
# timing out and relaunching ("keeps rejoining, never opens FFA").
CRITICAL_DETECTORS = ("lobby_play", "mode_list", "ffa_tile", "health_bar")
# Needed for respawn / loadout handling but not for simply reaching a match.
SECONDARY_DETECTORS = ("weapon_picker", "respawn_prompt", "match_end")


def template_library(subdir: str | None = None) -> TemplateLibrary:
    """The template library the live app uses: user data folder first, then
    the install/repo folder as a read-only fallback for older captures.
    """
    from warden import paths

    base, fallback = paths.templates_home(), paths.repo_root()
    if subdir:
        base, fallback = base / subdir, fallback / subdir
    return TemplateLibrary(base, fallbacks=[fallback])


def calibration_gaps(app, preset, detector_templates: TemplateLibrary | None = None,
                     weapon_templates: TemplateLibrary | None = None) -> list[tuple[str, str]]:
    """What still needs calibrating before a run can work, as (severity, message)
    pairs - severity ``"error"`` blocks reaching a match at all, ``"warn"``
    only degrades respawn/loadout handling.
    """
    from warden.flows.loadout import weapon_template_path

    detector_templates = detector_templates or template_library()
    weapon_templates = weapon_templates or template_library(app.weapon_templates_dir)
    gaps: list[tuple[str, str]] = []
    for name in (*CRITICAL_DETECTORS, *SECONDARY_DETECTORS):
        cfg = app.detectors.get(name)
        severity = "error" if name in CRITICAL_DETECTORS else "warn"
        if cfg is None or not cfg.enabled:
            if name in CRITICAL_DETECTORS and name not in ("mode_list",):
                gaps.append((severity, f"detector '{name}' is disabled or missing from config"))
            continue
        if cfg.method == "template":
            if cfg.template is None or not detector_templates.exists(cfg.template.path):
                path = cfg.template.path if cfg.template else f"templates/{name}.png"
                gaps.append((severity, f"'{name}' has no captured template yet ({path})"))

    # mode_list and ffa_tile are interchangeable for leaving the lobby; only
    # flag mode_list when ffa_tile can't stand in for it either.
    ffa_missing = any("'ffa_tile'" in m for _, m in gaps)
    if not ffa_missing:
        gaps = [g for g in gaps if "'mode_list'" not in g[1]]

    if not preset.loadout.random:
        for slot, weapon in preset.loadout.slots().items():
            if not weapon:
                continue
            if not weapon_templates.exists(weapon_template_path(slot, weapon)):
                gaps.append(("warn", f"no weapon template for {slot} '{weapon}' - Warden can't select it "
                                     f"(Calibration > Weapon templates)"))
            if slot not in app.loadout_ui.slots:
                gaps.append(("warn", f"loadout picker layout for '{slot}' isn't set up"))
    return gaps
