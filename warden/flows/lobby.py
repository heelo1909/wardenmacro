"""Lobby -> mode list -> FFA (HANDOFF section 6.1 MODE_SELECT row).

``ModeSelectSearch`` is the scroll-and-look-for-FFA sub-logic the main
state machine delegates to while in MODE_SELECT; it never drags (wheel
only, per spec) and gives up scrolling after ``max_attempts`` so a stuck
search doesn't spam input forever (the outer state timeout still applies).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol


class ModeSelectActions(Protocol):
    def click_ffa(self) -> None: ...
    def scroll_mode_list(self) -> None: ...


class ModeSelectSearch:
    def __init__(
        self,
        actions: ModeSelectActions,
        clock: Callable[[], float],
        max_attempts: int = 12,
        scroll_cooldown_s: float = 1.0,
        click_interval_s: float = 2.5,
    ):
        self.actions = actions
        self.clock = clock
        self.max_attempts = max_attempts
        self.scroll_cooldown_s = scroll_cooldown_s
        # The first click on the FFA tile can land while the menu is still
        # animating in (or get eaten by a focus change); if the tile is still
        # on screen this long after a click, click it again rather than
        # sitting there until the mode-select timeout.
        self.click_interval_s = click_interval_s
        self.reset()

    def reset(self) -> None:
        self.attempts = 0
        self._last_scroll: float = float("-inf")  # so the very first attempt scrolls immediately
        self._last_click: float | None = None
        self.clicks = 0

    def tick(self, ffa_visible: bool, now: float | None = None) -> None:
        now = self.clock() if now is None else now
        if ffa_visible:
            if self._last_click is None or now - self._last_click >= self.click_interval_s:
                self.actions.click_ffa()
                self._last_click = now
                self.clicks += 1
            return
        self._last_click = None
        if self.attempts >= self.max_attempts:
            return  # give up; the state machine's own timeout will bail to LOBBY
        if now - self._last_scroll >= self.scroll_cooldown_s:
            self.actions.scroll_mode_list()
            self.attempts += 1
            self._last_scroll = now
