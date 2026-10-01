import numpy as np
import pytest

from warden.geometry import Rect, frame_rect


@pytest.mark.parametrize("scale", [1.0, 1.25, 1.5])
def test_frac_px_round_trip_at_scaling(scale):
    # A client rect sized as if captured on a 100/125/150%-scaled monitor.
    rect = Rect(left=100, top=50, width=int(1920 * scale), height=int(1080 * scale))
    for fx, fy in [(0.0, 0.0), (0.5, 0.5), (1.0, 1.0), (0.3333, 0.777)]:
        x, y = rect.frac_to_px(fx, fy)
        bx, by = rect.px_to_frac(x, y)
        assert abs(bx - fx) < 0.002
        assert abs(by - fy) < 0.002
        assert rect.left <= x < rect.right
        assert rect.top <= y < rect.bottom


def test_frac_to_px_clamps_out_of_range():
    rect = Rect(0, 0, 100, 100)
    assert rect.frac_to_px(-1, 2) == (0, 99)


def test_roi_px_is_relative_to_origin():
    rect = Rect(500, 300, 200, 100)  # origin offset must not leak into roi_px
    x1, y1, x2, y2 = rect.roi_px([0.25, 0.5, 0.75, 1.0])
    assert (x1, y1, x2, y2) == (50, 50, 150, 100)


def test_roi_px_never_empty():
    rect = Rect(0, 0, 10, 10)
    x1, y1, x2, y2 = rect.roi_px([0.0, 0.0, 0.01, 0.01])
    assert x2 > x1 and y2 > y1


def test_frame_rect_matches_array_shape():
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    rect = frame_rect(frame)
    assert (rect.width, rect.height) == (640, 480)


def test_intersects():
    a, b, c = Rect(0, 0, 10, 10), Rect(5, 5, 10, 10), Rect(20, 20, 5, 5)
    assert a.intersects(b) and not a.intersects(c)
