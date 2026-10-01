from warden.behaviors.humanize import Humanizer


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
