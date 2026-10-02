"""In-match behavior (HANDOFF section 6.7): what Warden does with the
character while it's alive in a match - move, look around, shoot, use
abilities, and react to Roblox's idle warning.

``InMatchBehavior.tick()`` is called once per main-loop tick while the state
machine is IN_MATCH. It never blocks for long: walking is done by pressing a
movement key down and releasing it on a later tick (``_release_at``), so the
state machine keeps seeing deaths / match end / disconnects in real time.
Short actions (a shot, a key tap) block for well under a second.

Profiles:
- ``idle_nudge`` - a tiny step + glance every ``anti_idle_seconds`` (just beats the idle kick)
- ``patrol``     - keeps walking/strafing in short bursts and looking around
- ``fire_loop``  - idle_nudge + shoots ``fire_slot`` every ``fire_every_seconds``
- ``fight``      - patrol + shooting (moves *and* shoots)
- ``hide_spot``  - walks the recorded ``hide_path`` after each spawn, then idle_nudge
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Protocol

from warden.behaviors.humanize import Humanizer
from warden.config.schema import Abilities, Behavior, GameKeys

log = logging.getLogger(__name__)

MOVING_PROFILES = frozenset({"patrol", "fight"})
FIRING_PROFILES = frozenset({"fire_loop", "fight"})


class BehaviorInput(Protocol):
    def key_tap(self, key: str, hold_s: float | None = None) -> bool: ...
    def key_down(self, key: str) -> bool: ...
    def key_up(self, key: str) -> bool: ...
    def look(self, dx: int, dy: int, steps: int = 6) -> bool: ...
    def fire(self, hold_s: float, button: str = "left") -> bool: ...
    def release_all(self) -> None: ...


class InMatchBehavior:
    def __init__(
        self,
        inp: BehaviorInput,
        behavior: Behavior,
        abilities: Abilities,
        keys: GameKeys,
        anti_idle: bool = True,
        abilities_enabled: bool = True,
        humanizer: Humanizer | None = None,
        clock: Callable[[], float] = time.monotonic,
        on_action: Callable[[str], None] | None = None,
    ):
        self.inp = inp
        self.cfg = behavior
        self.abilities = abilities
        self.keys = keys
        self.anti_idle = anti_idle
        self.abilities_enabled = abilities_enabled
        self.h = humanizer or Humanizer(behavior.jitter_pct)
        self.clock = clock
        self.on_action = on_action or (lambda _m: None)
        self._held: str | None = None
        self._release_at = 0.0
        self._next_move = 0.0
        self._next_nudge = 0.0
        self._next_fire = 0.0
        self._next_ability: dict[str, float] = {}
        self._equipped_slot: str | None = None
        self._hide_step = 0
        self._started = False

    # -- lifecycle -------------------------------------------------------

    def on_spawn(self, now: float | None = None) -> None:
        """New life (match join or respawn): restart timers and the hide path."""
        now = self.clock() if now is None else now
        self.stop()
        self._started = True
        self._hide_step = 0
        self._equipped_slot = None
        self._next_move = now + self.h.between(0.4, 1.2)
        self._next_nudge = now + self.h.jitter(min(self.cfg.anti_idle_seconds, 20.0))
        self._next_fire = now + self.h.between(0.8, 2.0)
        self._next_ability = {a.key: now + self.h.jitter(a.every_seconds) for a in self.abilities.keys}

    def stop(self) -> None:
        """Leaving IN_MATCH (death, match end, pause...): let go of every key."""
        if self._held is not None:
            self.inp.key_up(self._held)
            self._held = None
        self.inp.release_all()

    # -- main entry -------------------------------------------------------

    def tick(self, idle_warning: bool = False, now: float | None = None) -> None:
        now = self.clock() if now is None else now
        if not self._started:
            self.on_spawn(now)

        # Finish a walking burst that's due.
        if self._held is not None and now >= self._release_at:
            self.inp.key_up(self._held)
            self._held = None

        if idle_warning:
            self._nudge(now, reason="idle warning on screen")

        profile = self.cfg.profile
        if profile == "hide_spot" and self._hide_step < len(self.cfg.hide_path):
            self._hide_path_step(now)
            return

        if profile in MOVING_PROFILES:
            if self._held is None and now >= self._next_move:
                self._move_burst(now)
        elif self.anti_idle and now >= self._next_nudge:
            self._nudge(now)

        if profile in FIRING_PROFILES and now >= self._next_fire:
            self._fire(now)

        if self.abilities_enabled and self.abilities.enabled:
            for ability in self.abilities.keys:
                due = self._next_ability.get(ability.key, now)
                if now >= due:
                    self.inp.key_tap(ability.key)
                    self.on_action(f"ability {ability.key}")
                    self._next_ability[ability.key] = now + self.h.jitter(ability.every_seconds)

    # -- actions -------------------------------------------------------

    def _move_burst(self, now: float) -> None:
        fwd, left, back, right = self.keys.move
        r = self.h.rng.random()
        key = fwd if r < 0.55 else left if r < 0.72 else right if r < 0.89 else back
        if self.inp.key_down(key):
            self._held = key
            self._release_at = now + self.h.between(0.5, 1.8)
        # Look around while walking so we don't run into the same wall forever.
        self.inp.look(int(self.h.between(-320, 320)), int(self.h.between(-25, 25)))
        if self.h.chance(0.15):
            self.inp.key_tap(self.keys.jump)
        self._next_move = self._release_at + self.h.between(0.15, 0.9)

    def _nudge(self, now: float, reason: str = "anti-idle") -> None:
        fwd, left, back, right = self.keys.move
        key = self.h.rng.choice([fwd, left, back, right])
        self.inp.key_tap(key, hold_s=self.h.between(0.12, 0.4))
        self.inp.look(int(self.h.between(-120, 120)), int(self.h.between(-15, 15)))
        self.on_action(f"nudge ({reason})")
        self._next_nudge = now + self.h.jitter(self.cfg.anti_idle_seconds)

    def _fire(self, now: float) -> None:
        slot = self.cfg.fire_slot
        if self._equipped_slot != slot:
            key = self.keys.slot_keys.get(slot)
            if key:
                self.inp.key_tap(key)
            self._equipped_slot = slot
        ox, oy = self.cfg.aim_offset
        if ox or oy:
            self.inp.look(int(ox * 1000), int(oy * 1000))
        self.inp.fire(self.h.between(0.25, 0.9))
        self.on_action(f"fire {slot}")
        self._next_fire = now + self.h.jitter(self.cfg.fire_every_seconds)

    def _hide_path_step(self, now: float) -> None:
        if self._held is not None:
            return  # still walking the previous step
        step = self.cfg.hide_path[self._hide_step]
        key = str(step.get("key", "W"))
        hold = float(step.get("hold_s", 0.5))
        if self.inp.key_down(key):
            self._held = key
            self._release_at = now + hold
        self._hide_step += 1
        if self._hide_step >= len(self.cfg.hide_path):
            self._next_nudge = now + hold + self.h.jitter(self.cfg.anti_idle_seconds)
