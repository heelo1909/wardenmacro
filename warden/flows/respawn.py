"""Respawn sequence (HANDOFF section 6.4) as a small internal sub-state machine.

Kept separate from ``core/state_machine.py`` because its timing is finer
grained (sub-second stages inside the DEAD state) than the main machine's
state-to-state transitions.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol


class RespawnActions(Protocol):
    def press_respawn(self) -> None: ...
    def reapply_loadout_if_due(self) -> bool: ...


class RespawnFlow:
    """Press Space -> re-press if still visible after ~1.5s -> watch for the
    switch-weapons window (~6s) -> reapply loadout if due -> done.
    """

    def __init__(
        self,
        actions: RespawnActions,
        clock: Callable[[], float],
        repress_s: float = 1.5,
        switch_watch_s: float = 6.0,
    ):
        self.actions = actions
        self.clock = clock
        self.repress_s = repress_s
        self.switch_watch_s = switch_watch_s
        self.reset()

    def reset(self) -> None:
        self.stage = "pending"  # pending -> pressed -> watching -> done
        self._press_time: float | None = None
        self._watch_start: float | None = None
        self._did_repress = False

    def tick(self, respawn_visible: bool, switch_visible: bool, health_visible: bool, now: float | None = None) -> bool:
        """One tick of the sequence. Returns True once it's complete (caller should move on)."""
        now = self.clock() if now is None else now

        if self.stage == "pending":
            self.actions.press_respawn()
            self._press_time = now
            self.stage = "pressed"
            return False

        if self.stage == "pressed":
            if not respawn_visible:
                self.stage = "watching"
                self._watch_start = now
                return False
            if not self._did_repress and self._press_time is not None and now - self._press_time >= self.repress_s:
                self.actions.press_respawn()
                self._did_repress = True
                self._press_time = now
            return False

        if self.stage == "watching":
            if switch_visible:
                self.actions.reapply_loadout_if_due()
                self.stage = "done"
                return True
            if health_visible:  # back in without a switch-weapons window this time
                self.stage = "done"
                return True
            if self._watch_start is not None and now - self._watch_start >= self.switch_watch_s:
                self.stage = "done"
                return True
            return False

        return True  # already done; caller should have moved states by now
