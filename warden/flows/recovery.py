"""Disconnect & recovery (HANDOFF section 6.5).

``RecoverySequence`` does steps 1-3 and 5-7 of the spec (click Leave, wait,
close the client if it's still around, relaunch, up to ``max_attempts``
before trying the browser fallback once, then exponential backoff forever);
step 4 - "success = two independent confirmations we're in a match" - is
already handled by ``StateMachine``'s own ``_GapConfirmer`` while in
RECOVERING (Phase 2), and the ordinary path back through LAUNCHING ->
LOADING -> LOBBY -> MODE_SELECT -> FFA covers the rest once a relaunch is
kicked off, so this flow only ever needs to hand off to ``State.LAUNCHING``
once it has done so.

Call ``full_reset()`` whenever the state machine reaches IN_MATCH by any
path - that's what tells this flow the incident is actually over, so a
later, unrelated disconnect starts a fresh attempt count rather than
inheriting a stale one.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from warden.config.schema import RecoveryConfig
from warden.core.state_machine import State


class RecoveryActions(Protocol):
    def click_leave_or_reconnect(self, prefer: str) -> None: ...
    def process_is_running(self) -> bool: ...
    def process_close(self, grace_s: float) -> None: ...
    def open_client(self) -> None: ...
    def open_browser_and_play(self) -> None: ...
    def on_incident(self, cause: str) -> None: ...


@dataclass
class RecoveryStats:
    attempts: int = 0
    backoff_cycles: int = 0
    used_browser_fallback: bool = False
    incident_start: float | None = None
    alerted: bool = False


class RecoverySequence:
    def __init__(self, actions: RecoveryActions, config: RecoveryConfig, clock: Callable[[], float]):
        self.actions = actions
        self.cfg = config
        self.clock = clock
        self.stats = RecoveryStats()
        self.stage = "idle"
        self._stage_started = 0.0

    def full_reset(self) -> None:
        """Call when the state machine reaches IN_MATCH - the incident is resolved."""
        if self.stage != "idle" and self.stats.incident_start is not None:
            self.actions.on_incident(
                f"recovery_resolved after {self.stats.attempts} attempt(s), "
                f"{self.clock() - self.stats.incident_start:.0f}s"
            )
        self.stats = RecoveryStats()
        self.stage = "idle"

    def tick(self, cause: str, now: float | None = None) -> State:
        """One step. Returns State.RECOVERING to keep waiting, or State.LAUNCHING
        once a relaunch has actually been kicked off this call.
        """
        now = self.clock() if now is None else now
        if self.stage == "idle":
            self.stats.incident_start = now
            self.actions.on_incident(f"recovery_start:{cause}")
            self.stage = "click_leave"
            self._stage_started = now

        if self.stage == "click_leave":
            self.actions.click_leave_or_reconnect(self.cfg.prefer_button)
            self.stage = "wait_leave"
            self._stage_started = now
            return State.RECOVERING

        if self.stage == "wait_leave":
            if now - self._stage_started >= self.cfg.leave_wait_s:
                self.stage = "close_process"
            return State.RECOVERING

        if self.stage == "close_process":
            if self.actions.process_is_running():
                self.actions.process_close(self.cfg.close_grace_s)
            self.stage = "relaunch"
            return State.RECOVERING

        if self.stage == "relaunch":
            return self._relaunch(now)

        if self.stage == "backoff":
            if now - self._stage_started >= self._current_backoff():
                self.stage = "click_leave"
            return State.RECOVERING

        if self.stage == "handed_off":
            # Ticked again means we re-entered RECOVERING for a new reason
            # before ever reaching IN_MATCH - pick the sequence back up
            # (attempt count carries over; it's still the same incident).
            self.stage = "click_leave"
            self._stage_started = now
            return self.tick(cause, now)

        return State.RECOVERING

    def _current_backoff(self) -> float:
        return min(self.cfg.backoff_initial_s * (2 ** self.stats.backoff_cycles), self.cfg.backoff_cap_s)

    def _relaunch(self, now: float) -> State:
        self.stats.attempts += 1
        if self.stats.attempts <= self.cfg.max_attempts:
            self.actions.open_client()
            self.stage = "handed_off"
            return State.LAUNCHING

        if self.cfg.browser_fallback and not self.stats.used_browser_fallback:
            self.stats.used_browser_fallback = True
            self.actions.open_browser_and_play()
            self.stage = "handed_off"
            return State.LAUNCHING

        # Every avenue tried this incident - back off before trying again.
        if not self.stats.alerted and self.stats.attempts >= self.cfg.alert_after_cycles:
            self.stats.alerted = True
            self.actions.on_incident(f"recovery_alert after {self.stats.attempts} failed attempts")
        self.stage = "backoff"
        self._stage_started = now
        self.stats.backoff_cycles += 1
        return State.RECOVERING
