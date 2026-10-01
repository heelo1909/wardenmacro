import numpy as np
import pytest

from tests.fixtures_frames import GREEN_BGR, blank, draw_frac_rect
from warden.config.schema import DetectorConfig, HSVRange, OCRSpec, ROI
from warden.vision.detectors import Detector, FrozenDetector, WindowStateDetector


def color_cfg(**kw):
    base = dict(method="color", roi=[0.3, 0.8, 0.7, 0.95],
                hsv=[HSVRange(lower=(45, 140, 140), upper=(80, 255, 255))],
                min_area=0.001, max_area=0.5, confirm_frames=2)
    base.update(kw)
    return DetectorConfig(**base)


def test_requires_consecutive_frames_to_confirm():
    det = Detector("lobby_play", color_cfg(confirm_frames=3))
    frame = draw_frac_rect(blank(), (0.4, 0.84, 0.6, 0.92), GREEN_BGR)
    results = [det.evaluate(frame) for _ in range(4)]
    assert [r.confirmed for r in results] == [False, False, True, True]
    assert all(r.hit for r in results)


def test_dropout_resets_the_streak():
    det = Detector("lobby_play", color_cfg(confirm_frames=2))
    hit_frame = draw_frac_rect(blank(), (0.4, 0.84, 0.6, 0.92), GREEN_BGR)
    miss_frame = blank()
    sequence = [hit_frame, hit_frame, miss_frame, hit_frame, hit_frame]
    confirmed = [det.evaluate(f).confirmed for f in sequence]
    assert confirmed == [False, True, False, False, True]


def test_disabled_detector_never_hits():
    det = Detector("lobby_play", color_cfg(enabled=False))
    frame = draw_frac_rect(blank(), (0.4, 0.84, 0.6, 0.92), GREEN_BGR)
    result = det.evaluate(frame)
    assert not result.hit and not result.confirmed


def test_fallback_hsv_used_when_primary_misses():
    cfg = color_cfg(hsv=[HSVRange(lower=(0, 0, 0), upper=(1, 1, 1))],
                     fallback_hsv=[HSVRange(lower=(45, 90, 90), upper=(90, 255, 255))],
                     confirm_frames=1)
    det = Detector("lobby_play", cfg)
    frame = draw_frac_rect(blank(), (0.4, 0.84, 0.6, 0.92), GREEN_BGR)
    assert det.evaluate(frame).confirmed


def test_reset_clears_streak():
    det = Detector("lobby_play", color_cfg(confirm_frames=2))
    frame = draw_frac_rect(blank(), (0.4, 0.84, 0.6, 0.92), GREEN_BGR)
    det.evaluate(frame)
    det.reset()
    result = det.evaluate(frame)
    assert not result.confirmed  # streak restarted, needs 2 frames again


def _checkerboard(dark_on_top_left: bool) -> np.ndarray:
    # A flat-colour frame hashes to all-zero bits (every pixel equals the mean),
    # which can't tell "unchanged" apart from "changed to a different flat colour".
    # A textured pattern gives the mean-threshold phash something real to compare.
    frame = blank()
    h, w = frame.shape[:2]
    light, dark = (230, 230, 230), (10, 10, 10)
    for gy in range(4):
        for gx in range(4):
            on = (gx + gy) % 2 == 0
            if not dark_on_top_left:
                on = not on
            color = dark if on else light
            frame[gy * h // 4:(gy + 1) * h // 4, gx * w // 4:(gx + 1) * w // 4] = color
    return frame


def test_frozen_detector_fires_after_hold_then_resets_on_change():
    t = [0.0]
    det = FrozenDetector(seconds=5.0, clock=lambda: t[0])
    frame = _checkerboard(dark_on_top_left=True)
    assert not det.evaluate(frame).confirmed
    t[0] = 2.0
    assert not det.evaluate(frame).confirmed  # same frame, but not long enough yet
    t[0] = 6.0
    assert det.evaluate(frame).confirmed
    t[0] = 6.1
    changed = _checkerboard(dark_on_top_left=False)  # inverted pattern -> every tile flips
    assert not det.evaluate(changed).confirmed  # frame changed -> timer resets
    t[0] = 6.2
    assert not det.evaluate(changed).confirmed


def test_window_state_detector_wraps_a_predicate():
    flag = {"v": False}
    det = WindowStateDetector("roblox_updating", lambda: flag["v"])
    assert not det.evaluate().hit
    flag["v"] = True
    assert det.evaluate().confirmed
