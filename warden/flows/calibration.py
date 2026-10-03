"""Calibration backend (HANDOFF section 7.4 / 8.8): capture a region as a
template, sample an HSV range from it, adjust a detector's ROI, and turn an
unknown-gallery frame into a new template. Kept separate from
``gui/pages/calibration.py`` so all of it is testable without Qt.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
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
                gaps.append(("info", f"{slot} '{weapon}': not learned yet - pick it yourself in the first "
                                     f"match and Warden will remember it"))
            if app.loadout_ui.mode == "tabs" and slot not in app.loadout_ui.slots:
                gaps.append(("warn", f"loadout picker layout for '{slot}' isn't set up"))
    return gaps


# --------------------------------------------------------------------------- guided setup
#
# Plain-language description of every screen Warden needs to recognize: where
# to go in the game to see it, and what to drag a box around once captured.
# Used by the Calibration page's checklist and the auto-capture overlay.


@dataclass(frozen=True)
class ScreenGuide:
    key: str
    title: str
    go_to: str          # what to do in Roblox so this screen is showing
    box_hint: str       # what to drag a box around on the captured frame
    required: bool      # needed just to reach an FFA match
    shares_capture: tuple[str, ...] = ()  # other screens visible in the same capture


SCREEN_GUIDES: tuple[ScreenGuide, ...] = (
    ScreenGuide("lobby_play", "Lobby", "Stand in the lobby where you normally start.",
                "the button you click to start queueing (e.g. Play)", True),
    ScreenGuide("mode_list", "Game-mode menu", "Open the menu where you pick a game mode, with FFA showing.",
                "something that's always on this menu, like its title", False, ("ffa_tile",)),
    ScreenGuide("ffa_tile", "FFA option", "Same menu as above, with the FFA option visible.",
                "just the FFA tile / button", True),
    ScreenGuide("health_bar", "In a match", "Be in a match (alive) with your HUD showing.",
                "the green health bar (bottom-left)", True),
    ScreenGuide("weapon_picker", "Weapon picker", "Open the weapon / loadout picker.",
                "the picker's title or another part that's always there", False),
    ScreenGuide("respawn_prompt", "Respawn screen", "Die in a match and leave the respawn prompt up.",
                "the respawn prompt / button", False),
    ScreenGuide("match_end", "Match results", "Stay on the end-of-match results screen.",
                "the results / victory banner", False),
)
GUIDES_BY_KEY = {g.key: g for g in SCREEN_GUIDES}

# The auto-capture walk-through: one capture per step; a step can fill
# several screens at once (the mode menu shows both mode_list and ffa_tile).
CAPTURE_STEPS: tuple[tuple[str, ...], ...] = (
    ("lobby_play",), ("mode_list", "ffa_tile"), ("health_bar",), ("weapon_picker",),
    ("respawn_prompt",), ("match_end",),
)

# Solid-colored bars are learned by color (they change length, so an image
# template wouldn't match at low health); everything else - buttons, tiles,
# banners, mostly text + icons - is learned as an image template.
COLOR_LEARNED = frozenset({"health_bar"})

MAX_SELECTION_AREA = 0.35  # a "template" covering most of the screen matches nothing useful


def selection_problem(sel: tuple[float, float, float, float] | None) -> str | None:
    """A human-readable reason a drag selection is unusable, or None if it's fine."""
    if sel is None:
        return "Drag a box on the picture first."
    x1, y1, x2, y2 = sel
    area = (x2 - x1) * (y2 - y1)
    if area > MAX_SELECTION_AREA:
        return ("That box covers most of the screen - drag a small box around just the "
                "thing described above, so Warden learns what it looks like.")
    if (x2 - x1) < 0.004 or (y2 - y1) < 0.004:
        return "That box is too small - drag a slightly bigger one."
    return None


def expand_roi(sel: tuple[float, float, float, float], pad: float = 0.12) -> tuple[float, float, float, float]:
    """Where to *look* for something boxed at ``sel``: the box plus a margin, so
    small layout shifts (window size, UI animation) still match."""
    x1, y1, x2, y2 = sel
    w, h = x2 - x1, y2 - y1
    px, py = max(w * 0.5, pad), max(h * 0.5, pad)
    clamp = lambda v: min(max(v, 0.0), 1.0)  # noqa: E731
    return (clamp(x1 - px), clamp(y1 - py), clamp(x2 + px), clamp(y2 + py))


def tighten_to_button(frame: np.ndarray, sel: tuple[float, float, float, float],
                      inset_px: int = 3) -> tuple[float, float, float, float]:
    """Shrink a box to the solid, brightly colored button inside it.

    People box a button with some margin; that margin is the 3D game world,
    which changes every time the camera moves, so the template stops matching
    (2026-10-02: the user's Play-button template scored 0.72 with its margin,
    0.97 tightened). If the box doesn't contain one solid colored block, it's
    returned unchanged.
    """
    import cv2

    rect = frame_rect(frame)
    x1, y1, x2, y2 = rect.roi_px(sel)
    crop = frame[y1:y2, x1:x2]
    if crop.size == 0 or crop.ndim != 3:
        return sel
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    mask = ((hsv[:, :, 1] > 110) & (hsv[:, :, 2] > 110)).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    if count <= 1:
        return sel
    i = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    bx, by, bw, bh, area = stats[i]
    sel_area = crop.shape[0] * crop.shape[1]
    # Must be a solid block (not scattered pixels), clearly smaller than the box.
    if area < 0.15 * sel_area or area < 0.6 * bw * bh or bw * bh > 0.92 * sel_area:
        return sel
    if bw <= 2 * inset_px + 4 or bh <= 2 * inset_px + 4:
        return sel
    nx1, ny1 = x1 + bx + inset_px, y1 + by + inset_px
    nx2, ny2 = x1 + bx + bw - inset_px, y1 + by + bh - inset_px
    return (nx1 / rect.width, ny1 / rect.height, nx2 / rect.width, ny2 / rect.height)


def calibration_capture_path(screen: str) -> Path:
    """Where auto-capture stores the raw screenshot for a screen."""
    from warden import paths

    return paths.data_dir("calibration") / f"{screen}.png"


def is_screen_calibrated(app, name: str, templates: TemplateLibrary) -> bool:
    cfg = app.detectors.get(name)
    if cfg is None or not cfg.enabled:
        return False
    if cfg.method == "template":
        return cfg.template is not None and templates.exists(cfg.template.path)
    return bool(cfg.params.get("calibrated"))


def quick_calibrate(app, name: str, frame: np.ndarray, sel: tuple[float, float, float, float],
                    templates: TemplateLibrary) -> tuple[DetectorConfig, str]:
    """One-click calibration of ``name`` from a box on ``frame``.

    Color detectors (e.g. health_bar) learn the box's colors; everything else
    learns the box as an image template. Either way the detector then only
    looks near where the box was. Returns (new config, short description).
    """
    from warden.config.schema import TemplateSpec

    cfg = app.detectors[name]
    roi = expand_roi(sel)
    params = {**cfg.params, "calibrated": 1.0}
    if name in COLOR_LEARNED:
        lower, upper = sample_hsv_from_selection(frame, sel)
        area = (sel[2] - sel[0]) * (sel[3] - sel[1])
        aspect = ((sel[2] - sel[0]) * frame.shape[1]) / max((sel[3] - sel[1]) * frame.shape[0], 1)
        new = cfg.model_copy(update={
            "hsv": [HSVRange(lower=tuple(lower), upper=tuple(upper))], "fallback_hsv": [],
            "roi": ROI(x1=roi[0], y1=roi[1], x2=roi[2], y2=roi[3]),
            "min_area": min(cfg.min_area, area * 0.15), "max_area": max(min(area * 3.0, 1.0), cfg.min_area),
            "aspect_min": max(min(aspect * 0.3, cfg.aspect_min), 0.05),
            "aspect_max": max(aspect * 2.5, cfg.aspect_max),
            "params": params,
        })
        return new, f"learned its colors (H {lower[0]}-{upper[0]})"
    rel = cfg.template.path if cfg.template is not None else f"templates/{name}.png"
    sel = tighten_to_button(frame, sel)
    roi = expand_roi(sel)
    save_template_from_frame(templates, rel, frame, sel)
    threshold = cfg.template.threshold if cfg.template is not None else 0.78
    new = cfg.model_copy(update={
        "method": "template", "template": TemplateSpec(path=rel, threshold=threshold, ref_height=frame.shape[0]),
        "roi": ROI(x1=roi[0], y1=roi[1], x2=roi[2], y2=roi[3]), "params": params,
    })
    return new, "saved what it looks like"
