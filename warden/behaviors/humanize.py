"""Humanized timing. Every wait in Warden goes through here - no fixed intervals."""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from typing import Protocol


class Humanizer:
    def __init__(self, jitter_pct: float = 15.0, seed: int | None = None):
        self.jitter_pct = jitter_pct
        self.rng = random.Random(seed)

    def jitter(self, base: float, pct: float | None = None) -> float:
        """Gaussian around ``base`` (sigma = pct% of base), clamped to +/-2 sigma and >= 0."""
        pct = self.jitter_pct if pct is None else pct
        if base <= 0 or pct <= 0:
            return max(base, 0.0)
        sigma = base * pct / 100.0
        value = self.rng.gauss(base, sigma)
        return max(0.0, min(max(value, base - 2 * sigma), base + 2 * sigma))

    def between(self, low: float, high: float) -> float:
        """Gaussian centred in [low, high], clamped to it."""
        if high <= low:
            return low
        mid, sigma = (low + high) / 2, (high - low) / 4
        return min(max(self.rng.gauss(mid, sigma), low), high)

    def hold_seconds(self, hold_ms: tuple[int, int]) -> float:
        return self.between(hold_ms[0], hold_ms[1]) / 1000.0

    def chance(self, p: float) -> bool:
        return self.rng.random() < p

    def micro_pause(self, p: float = 0.04, low: float = 0.15, high: float = 0.9) -> float:
        """Occasionally returns a small extra pause (seconds), else 0."""
        return self.between(low, high) if self.chance(p) else 0.0

    def offset_px(self, max_px: int) -> int:
        if max_px <= 0:
            return 0
        return int(round(self.between(-max_px, max_px)))


class FlourishInput(Protocol):
    def look(self, dx: int, dy: int, steps: int = 6) -> bool: ...
    def fire(self, hold_s: float, button: str = "left") -> bool: ...
    def key_tap(self, key: str, hold_s: float | None = None) -> bool: ...


def post_loadout_flourish(
    input_ctl: FlourishInput,
    humanizer: Humanizer,
    jump_key: str,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """A handful of quick, randomized look/fire/jump touches for right after a
    loadout is picked - so the handoff into the match isn't four clean clicks
    followed by dead stillness. Deliberately small and simple (a few camera
    nudges, maybe a shot, maybe a jump): this is cosmetic, not a
    humanization engine, and every action already goes through the normal
    input gate (focus/emergency-stop/observe-only all still apply), so this
    can't do anything the rest of Warden couldn't already do. Bounded to well
    under a second so it can't become a new source of slowness itself.
    """
    for _ in range(round(humanizer.between(2, 4))):
        input_ctl.look(humanizer.offset_px(140), humanizer.offset_px(70))
        sleep(humanizer.between(0.04, 0.12))
    if humanizer.chance(0.5):
        input_ctl.fire(humanizer.hold_seconds((60, 150)))
    if humanizer.chance(0.35):
        input_ctl.key_tap(jump_key)
