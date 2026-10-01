import numpy as np

from warden.geometry import Rect
from warden.vision.capture import measure_fps


class FakeCapturer:
    def __init__(self):
        self.calls = 0

    def grab(self, rect: Rect) -> np.ndarray:
        self.calls += 1
        return np.zeros((rect.height, rect.width, 3), dtype=np.uint8)


def test_measure_fps_counts_grabs_over_the_window():
    cap = FakeCapturer()
    fps = measure_fps(cap, Rect(0, 0, 100, 100), seconds=0.1)
    assert cap.calls > 0
    assert fps > 0


def test_mss_capturer_rejects_empty_rect():
    from warden.vision.capture import MssCapturer

    import pytest

    with pytest.raises(ValueError):
        MssCapturer().grab(Rect(0, 0, 0, 0))
