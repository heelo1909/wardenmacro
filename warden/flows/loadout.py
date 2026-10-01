"""Verified loadout transaction (HANDOFF section 6.3).

``LoadoutTransaction`` is a small step-wise sub-state machine, same spirit as
``flows/respawn.py`` and ``flows/lobby.py``: each ``tick()`` call does *one*
small thing (click a tab, look once, scroll, click a tile, verify) and
returns control to the caller. That makes it naturally interruptible by the
state machine's own per-tick abort checks (death, picker closed, disconnect)
instead of blocking through an entire multi-second transaction - a slow
4-slot transaction never runs uninterruptibly.

Never guesses a grid position: a slot whose weapon can't be found after
``max_search_scrolls`` is left alone, logged, and the transaction moves on.
Commit (``result.success``) requires every *requested* slot (a preset may
leave a slot blank, meaning "don't touch it") to verify.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import cv2
import numpy as np

from warden.config.schema import SLOTS, LoadoutUI
from warden.geometry import frame_rect
from warden.vision.templates import TemplateLibrary, match_template

log = logging.getLogger(__name__)


def weapon_template_path(slot: str, weapon_name: str) -> str:
    """Naming convention for a weapon's captured template image."""
    safe = "".join(c if c.isalnum() or c in " _-" else "_" for c in weapon_name).strip().replace(" ", "_")
    return f"{slot}/{safe}.png"


class LoadoutActions(Protocol):
    def click_frac(self, fx: float, fy: float, what: str = "") -> bool: ...
    def scroll(self, notches: int, at: tuple[float, float]) -> bool: ...


@dataclass
class SlotOutcome:
    slot: str
    weapon: str
    verified: bool
    fixed: bool  # True if it actually needed clicking (wasn't already equipped)
    scrolls_used: int = 0
    reason: str = ""


@dataclass
class LoadoutResult:
    slots: dict[str, SlotOutcome] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        return all(o.verified for o in self.slots.values())

    @property
    def fixes(self) -> int:
        return sum(1 for o in self.slots.values() if o.fixed)


def _verify(frame: np.ndarray, roi, template: np.ndarray, threshold: float) -> bool:
    match = match_template(frame, template, roi, scale_steps=5)
    return match is not None and match.score >= threshold


class LoadoutTransaction:
    def __init__(
        self,
        actions: LoadoutActions,
        templates: TemplateLibrary,
        ui: LoadoutUI,
        get_frame: Callable[[], np.ndarray | None],
        diagnostics_dir: Path | None = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.actions = actions
        self.templates = templates
        self.ui = ui
        self.get_frame = get_frame
        self.diagnostics_dir = diagnostics_dir
        self.clock = clock
        self.reset(None)

    def reset(self, target: dict[str, str] | None) -> None:
        self.target = {slot: name for slot, name in (target or {}).items() if name}
        self._order = [s for s in SLOTS if s in self.target]
        self._index = 0
        self._stage = "check"  # check -> tab -> search -> verify -> (next slot)
        self._scrolls = 0
        self.result = LoadoutResult()
        self.done = len(self._order) == 0

    @property
    def current_slot(self) -> str | None:
        return self._order[self._index] if self._index < len(self._order) else None

    def tick(self) -> bool:
        """One step. Returns True once every requested slot has been resolved."""
        if self.done:
            return True
        slot = self.current_slot
        weapon = self.target[slot]
        slot_ui = self.ui.slots.get(slot)
        if slot_ui is None:
            log.warning("loadout: no UI calibration for slot '%s' - skipping", slot)
            self._finish_slot(slot, weapon, verified=False, fixed=False, reason="not calibrated")
            return self.done

        template = self.templates.get(weapon_template_path(slot, weapon))
        if template is None:
            self._finish_slot(slot, weapon, verified=False, fixed=False, reason="no template captured")
            return self.done

        frame = self.get_frame()
        if frame is None:
            return self.done  # nothing to do without a frame; try again next tick

        if self._stage == "check":
            if _verify(frame, slot_ui.verify_roi.as_list(), template, self.ui.verify_threshold):
                self._finish_slot(slot, weapon, verified=True, fixed=False, reason="already equipped")
                return self.done
            self._stage = "tab"
            return self.done

        if self._stage == "tab":
            self.actions.click_frac(*slot_ui.tab, what=f"{slot} tab")
            self._stage = "search"
            self._scrolls = 0
            return self.done

        if self._stage == "search":
            match = match_template(frame, template, slot_ui.grid_roi.as_list(), scale_steps=7)
            if match is not None and match.score >= self.ui.verify_threshold:
                self.actions.click_frac(*match.center, what=f"{slot} weapon tile ({weapon})")
                self._stage = "verify"
                return self.done
            if self._scrolls >= self.ui.max_search_scrolls:
                self._finish_slot(slot, weapon, verified=False, fixed=False,
                                   reason="weapon tile not found", scrolls_used=self._scrolls)
                return self.done
            center = ((slot_ui.grid_roi.x1 + slot_ui.grid_roi.x2) / 2, (slot_ui.grid_roi.y1 + slot_ui.grid_roi.y2) / 2)
            self.actions.scroll(-self.ui.scroll_notches, at=center)
            self._scrolls += 1
            return self.done

        if self._stage == "verify":
            if _verify(frame, slot_ui.verify_roi.as_list(), template, self.ui.verify_threshold):
                self._finish_slot(slot, weapon, verified=True, fixed=True, scrolls_used=self._scrolls)
            else:
                self._finish_slot(slot, weapon, verified=False, fixed=False,
                                   reason="verification failed after click", scrolls_used=self._scrolls)
            return self.done

        return self.done

    def _finish_slot(self, slot: str, weapon: str, verified: bool, fixed: bool,
                      reason: str = "", scrolls_used: int = 0) -> None:
        self.result.slots[slot] = SlotOutcome(slot, weapon, verified, fixed, scrolls_used, reason)
        if not verified:
            log.warning("loadout: %s -> '%s' failed (%s)", slot, weapon, reason)
            self._save_diagnostic(slot)
        self._index += 1
        self._stage = "check"
        if self._index >= len(self._order):
            self.done = True

    def _save_diagnostic(self, slot: str) -> None:
        if self.diagnostics_dir is None:
            return
        frame = self.get_frame()
        if frame is None:
            return
        self.diagnostics_dir.mkdir(parents=True, exist_ok=True)
        path = self.diagnostics_dir / f"{time.strftime('%Y%m%d_%H%M%S')}_{slot}.png"
        cv2.imwrite(str(path), frame)
