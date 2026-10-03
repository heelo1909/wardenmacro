from warden.behaviors.humanize import Humanizer, post_loadout_flourish


class FakeFlourishInput:
    def __init__(self):
        self.calls: list[tuple] = []

    def look(self, dx, dy, steps=6):
        self.calls.append(("look", dx, dy))
        return True

    def fire(self, hold_s, button="left"):
        self.calls.append(("fire", round(hold_s, 2)))
        return True

    def key_tap(self, key, hold_s=None):
        self.calls.append(("jump", key))
        return True


def test_jitter_is_centered_and_bounded():
    h = Humanizer(jitter_pct=20, seed=1)
    samples = [h.jitter(100) for _ in range(500)]
    assert all(s >= 0 for s in samples)
    assert 60 <= min(samples) and max(samples) <= 140
    assert abs(sum(samples) / len(samples) - 100) < 5


def test_jitter_zero_base_or_pct_is_stable():
    h = Humanizer(jitter_pct=0, seed=2)
    assert h.jitter(50) == 50
    assert Humanizer(seed=3).jitter(0) == 0


def test_between_stays_in_range():
    h = Humanizer(seed=4)
    for _ in range(300):
        v = h.between(10, 20)
        assert 10 <= v <= 20


def test_between_degenerate_range_returns_low():
    assert Humanizer(seed=5).between(5, 5) == 5
    assert Humanizer(seed=5).between(10, 5) == 10


def test_hold_seconds_within_configured_ms_range():
    h = Humanizer(seed=6)
    for _ in range(200):
        s = h.hold_seconds((40, 110))
        assert 0.04 <= s <= 0.11


def test_seeded_sequences_are_reproducible():
    a = Humanizer(jitter_pct=15, seed=42)
    b = Humanizer(jitter_pct=15, seed=42)
    assert [a.jitter(10) for _ in range(5)] == [b.jitter(10) for _ in range(5)]


def test_no_fixed_intervals_across_calls():
    h = Humanizer(seed=7)
    values = {h.jitter(75) for _ in range(20)}
    assert len(values) > 15  # overwhelmingly likely to differ every time


# --------------------------------------------------------------------------- post_loadout_flourish


def test_flourish_always_moves_the_camera_a_few_times_then_stops():
    """2026-10-03 user ask: after picking weapons, do some randomized screen
    movement (and maybe fire/jump) so the handoff doesn't look like a bot
    that went perfectly still - but keep it simple and bounded."""
    for seed in range(25):
        inp = FakeFlourishInput()
        sleeps = []
        post_loadout_flourish(inp, Humanizer(seed=seed), "SPACE", sleep=sleeps.append)
        looks = [c for c in inp.calls if c[0] == "look"]
        assert 2 <= len(looks) <= 4
        for _, dx, dy in looks:
            assert -140 <= dx <= 140 and -70 <= dy <= 70
        # cheap and bounded - this must never become a new source of slowness
        assert sum(sleeps) < 1.0
        assert len(inp.calls) <= len(looks) + 2  # at most one fire, one jump


def test_flourish_fire_and_jump_are_each_sometimes_skipped_and_sometimes_sent():
    fires = jumps = 0
    n = 200
    for seed in range(n):
        inp = FakeFlourishInput()
        post_loadout_flourish(inp, Humanizer(seed=seed), "SPACE", sleep=lambda s: None)
        kinds = [c[0] for c in inp.calls]
        fires += "fire" in kinds
        jumps += "jump" in kinds
    assert 0 < fires < n   # neither "always fires" nor "never fires"
    assert 0 < jumps < n   # same for jumping


def test_flourish_jump_uses_the_configured_key():
    for seed in range(50):
        inp = FakeFlourishInput()
        post_loadout_flourish(inp, Humanizer(seed=seed), "E", sleep=lambda s: None)
        jumps = [c for c in inp.calls if c[0] == "jump"]
        assert all(key == "E" for _, key in jumps)


def test_flourish_does_not_swallow_errors_from_the_input_backend():
    """post_loadout_flourish doesn't catch anything itself - the "never let
    this break the macro" guarantee is LiveActions' job at the call site
    (it wraps this in try/except), which keeps this function simple and the
    failure mode visible in a direct test rather than silently absorbed."""
    import pytest

    class FlakyInput(FakeFlourishInput):
        def fire(self, hold_s, button="left"):
            raise RuntimeError("button stuck")

    def fired(seed):
        inp = FakeFlourishInput()
        post_loadout_flourish(inp, Humanizer(seed=seed), "SPACE", sleep=lambda s: None)
        return any(c[0] == "fire" for c in inp.calls)

    seed = next(s for s in range(200) if fired(s))  # a seed that actually reaches fire()
    with pytest.raises(RuntimeError):
        post_loadout_flourish(FlakyInput(), Humanizer(seed=seed), "SPACE", sleep=lambda s: None)
