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
        settle_s: float = 0.0,
        verify_attempts: int = 1,
    ):
        self.actions = actions
        self.templates = templates
        self.ui = ui
        self.get_frame = get_frame
        self.diagnostics_dir = diagnostics_dir
        self.clock = clock
        # After any click the game needs a moment to redraw (tab switch
        # animation, equip animation). Reading the screen immediately after a
        # click sees the *old* picker, which used to make every freshly
        # clicked weapon fail verification - so wait settle_s first, and give
        # verification a few looks before declaring the slot failed.
        self.settle_s = settle_s
        self.verify_attempts = max(1, verify_attempts)
        self.reset(None)

    def reset(self, target: dict[str, str] | None) -> None:
        self.target = {slot: name for slot, name in (target or {}).items() if name}
        self._order = [s for s in SLOTS if s in self.target]
        self._index = 0
        self._stage = "check"  # check -> tab -> search -> verify -> (next slot)
        self._scrolls = 0
        self._settle_until = 0.0
        self._verify_tries = 0
        self.result = LoadoutResult()
        self.done = len(self._order) == 0

    def _clicked(self) -> None:
        self._settle_until = self.clock() + self.settle_s

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

        if self.settle_s and self.clock() < self._settle_until:
            return self.done  # let the UI catch up with the last click

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
            self._clicked()
            self._stage = "search"
            self._scrolls = 0
            return self.done

        if self._stage == "search":
            match = match_template(frame, template, slot_ui.grid_roi.as_list(), scale_steps=7)
            if match is not None and match.score >= self.ui.verify_threshold:
                self.actions.click_frac(*match.center, what=f"{slot} weapon tile ({weapon})")
                self._clicked()
                self._stage = "verify"
                self._verify_tries = 0
                return self.done
            if self._scrolls >= self.ui.max_search_scrolls:
                self._finish_slot(slot, weapon, verified=False, fixed=False,
                                   reason="weapon tile not found", scrolls_used=self._scrolls)
                return self.done
            center = ((slot_ui.grid_roi.x1 + slot_ui.grid_roi.x2) / 2, (slot_ui.grid_roi.y1 + slot_ui.grid_roi.y2) / 2)
            self.actions.scroll(-self.ui.scroll_notches, at=center)
            self._clicked()
            self._scrolls += 1
            return self.done

        if self._stage == "verify":
            if _verify(frame, slot_ui.verify_roi.as_list(), template, self.ui.verify_threshold):
                self._finish_slot(slot, weapon, verified=True, fixed=True, scrolls_used=self._scrolls)
            elif self._verify_tries + 1 < self.verify_attempts:
                self._verify_tries += 1
                self._clicked()  # look again after another settle period
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


# --------------------------------------------------------------------------- sequential (RIVALS) picker


class SequentialLoadoutTransaction:
    """RIVALS-style picker: one weapon list per slot, shown in order primary ->
    secondary -> melee -> utility, and clicking a weapon moves the picker on to
    the next slot by itself. So there are no tabs to click and no way to read
    back "what's equipped" - success for a slot is "found the weapon's row,
    clicked it, and the list changed".

    Same interface as ``LoadoutTransaction`` (``reset``/``tick``/``done``/
    ``result``) so ``LiveActions`` can use either one. If a slot can't be
    picked, the transaction stops there (later slots aren't on screen yet).
    """

    def __init__(
        self,
        actions: LoadoutActions,
        templates: TemplateLibrary,
        ui: LoadoutUI,
        get_frame: Callable[[], np.ndarray | None],
        diagnostics_dir: Path | None = None,
        clock: Callable[[], float] = time.monotonic,
        settle_s: float = 0.6,
        verify_attempts: int = 3,
        change_threshold: float = 10.0,
        learn_missing: bool = True,
    ):
        # learn_missing: a weapon Warden has never seen isn't a failure - it
        # waits for the player to pick it themselves once and learns it from
        # that click (see learn_from_click). Zero setup for weapons.
        self.learn_missing = learn_missing
        self.actions = actions
        self.templates = templates
        self.ui = ui
        self.get_frame = get_frame
        self.diagnostics_dir = diagnostics_dir
        self.clock = clock
        self.settle_s = settle_s
        self.verify_attempts = max(1, verify_attempts)
        self.change_threshold = change_threshold
        self.reset(None)

    def reset(self, target: dict[str, str] | None) -> None:
        target = target or {}
        # The picker always walks every slot in order; stop at the first slot
        # the preset leaves blank and let the game keep whatever it shows.
        self._order: list[str] = []
        for slot in SLOTS:
            if not target.get(slot):
                break
            self._order.append(slot)
        self.target = {s: target[s] for s in self._order}
        self._index = 0
        self._stage = "top"
        self._scrolls = 0
        self._settle_until = 0.0
        self._verify_tries = 0
        self._snapshot: np.ndarray | None = None
        self._clicked_at: tuple[float, float] | None = None
        self.result = LoadoutResult()
        self.done = len(self._order) == 0

    @property
    def current_slot(self) -> str | None:
        return self._order[self._index] if self._index < len(self._order) else None

    def _list_center(self) -> tuple[float, float]:
        r = self.ui.list_roi
        return ((r.x1 + r.x2) / 2, (r.y1 + r.y2) / 2)

    def _list_crop(self, frame: np.ndarray) -> np.ndarray:
        rect = frame_rect(frame)
        x1, y1, x2, y2 = rect.roi_px(self.ui.list_roi.as_list())
        crop = frame[y1:y2, x1:x2]
        return cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop

    def _wait(self) -> None:
        self._settle_until = self.clock() + self.settle_s

    def tick(self) -> bool:
        if self.done:
            return True
        if self.settle_s and self.clock() < self._settle_until:
            return False
        slot = self.current_slot
        weapon = self.target[slot]
        template = self.templates.get(weapon_template_path(slot, weapon))
        if template is None:
            if self.learn_missing:
                self._stage = "learn"  # wait for the player's own click (learn_from_click)
                return False
            self._fail(slot, weapon, "no template - pick it yourself once so Warden can learn it")
            return self.done
        frame = self.get_frame()
        if frame is None:
            return False

        if self._stage == "learn":
            self._stage = "top"  # template appeared (learned elsewhere) - carry on
        if self._stage == "top":
            # Lists keep their scroll position; start each search from the top.
            self.actions.scroll(abs(self.ui.scroll_notches) * max(self.ui.max_search_scrolls, 1),
                                at=self._list_center())
            self._wait()
            self._stage = "search"
            self._scrolls = 0
            return False

        if self._stage == "search":
            match = match_template(frame, template, self.ui.list_roi.as_list(),
                                   scale_min=0.85, scale_max=1.15, scale_steps=7)
            if match is not None and match.score >= self.ui.verify_threshold:
                self._snapshot = self._list_crop(frame)
                self._clicked_at = match.center
                self.actions.click_frac(*match.center, what=f"{slot} weapon ({weapon})")
                self._wait()
                self._stage = "verify"
                self._verify_tries = 0
                return False
            if self._scrolls >= self.ui.max_search_scrolls:
                self._fail(slot, weapon, "weapon not found in the list", scrolls=self._scrolls)
                return self.done
            self.actions.scroll(-self.ui.scroll_notches, at=self._list_center())
            self._scrolls += 1
            self._wait()
            return False

        if self._stage == "verify":
            now_crop = self._list_crop(frame)
            changed = (self._snapshot is None or now_crop.shape != self._snapshot.shape
                       or float(np.mean(cv2.absdiff(now_crop, self._snapshot))) >= self.change_threshold)
            if not changed:
                # The next slot's list doesn't contain this weapon - if it's
                # gone from the list, the click registered.
                again = match_template(frame, template, self.ui.list_roi.as_list(),
                                       scale_min=0.85, scale_max=1.15, scale_steps=7)
                moved = (again is not None and self._clicked_at is not None
                         and max(abs(again.center[0] - self._clicked_at[0]),
                                 abs(again.center[1] - self._clicked_at[1])) > 0.01)
                changed = again is None or again.score < self.ui.verify_threshold or moved
            if changed:
                self.result.slots[slot] = SlotOutcome(slot, weapon, True, True, self._scrolls)
                self._index += 1
                self._stage = "top"
                self._snapshot = None
                if self._index >= len(self._order):
                    self.done = True
                return self.done
            self._verify_tries += 1
            if self._verify_tries >= self.verify_attempts:
                self._fail(slot, weapon, "clicked, but the picker didn't move on", scrolls=self._scrolls)
                return self.done
            self._wait()
            return False
        return self.done

    @property
    def waiting_to_learn(self) -> bool:
        return not self.done and self._stage == "learn"

    def learn_from_click(self, frame: np.ndarray, fx: float, fy: float) -> bool:
        """The player clicked (fx, fy) in the list while we were waiting to learn
        the current slot's weapon: remember what that row looks like. Their
        click already picked it in-game, so move on to the next slot."""
        if not self.waiting_to_learn:
            return False
        crop = learn_row_template(frame, fx, fy, self.ui)
        if crop is None:
            return False
        slot = self.current_slot
        weapon = self.target[slot]
        self.templates.save(weapon_template_path(slot, weapon), crop)
        log.info("loadout: learned %s '%s' from the player's pick", slot, weapon)
        self.result.slots[slot] = SlotOutcome(slot, weapon, True, False, 0, "learned from your pick")
        self._index += 1
        self._stage = "top"
        self._wait()
        if self._index >= len(self._order):
            self.done = True
        return True

    def _fail(self, slot: str, weapon: str, reason: str, scrolls: int = 0) -> None:
        self.result.slots[slot] = SlotOutcome(slot, weapon, False, False, scrolls, reason)
        log.warning("loadout: %s -> '%s' failed (%s)", slot, weapon, reason)
        frame = self.get_frame() if self.diagnostics_dir is not None else None
        if frame is not None:
            self.diagnostics_dir.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(self.diagnostics_dir / f"{time.strftime('%Y%m%d_%H%M%S')}_{slot}.png"), frame)
        for later in self._order[self._index + 1:]:
            self.result.slots[later] = SlotOutcome(later, self.target[later], False, False, 0,
                                                   f"skipped - {slot} couldn't be picked")
        self._index = len(self._order)
        self.done = True


def learn_row_template(frame: np.ndarray, fx: float, fy: float, ui: LoadoutUI) -> np.ndarray | None:
    """The bit of a RIVALS weapon-list row under a click at (fx, fy), to use as
    that weapon's template - or None if the click wasn't on the list.

    Weapon art overlaps the left part of each row and some names sparkle, so
    the crop is the centre of the row (where the name is) at the click height.
    """
    r = ui.list_roi
    if not (r.x1 <= fx <= r.x2 and r.y1 <= fy <= r.y2):
        return None
    width = r.x2 - r.x1
    cx = (r.x1 + r.x2) / 2
    x1, x2 = cx - width * 0.18, cx + width * 0.18
    y1, y2 = max(fy - 0.021, r.y1), min(fy + 0.021, r.y2)
    rect = frame_rect(frame)
    px1, py1, px2, py2 = rect.roi_px((x1, y1, x2, y2))
    crop = frame[py1:py2, px1:px2]
    return crop.copy() if crop.size else None
