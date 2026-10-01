"""Humanized timing. Every wait in Warden goes through here - no fixed intervals."""

from __future__ import annotations

import random


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
