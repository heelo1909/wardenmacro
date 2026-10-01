import pytest

from warden.platform import dpi


@pytest.mark.parametrize("scale", [1.0, 1.25, 1.5])
def test_logical_physical_round_trip(scale):
    logical = 400.0
    physical = dpi.to_physical(logical, scale)
    assert abs(dpi.to_logical(physical, scale) - logical) < 1e-6
    assert physical == pytest.approx(logical * scale)


def test_logical_rect_to_physical_scales_all_fields():
    from warden.geometry import Rect

    rect = Rect(10, 20, 100, 50)
    out = dpi.logical_rect_to_physical(rect, 1.25)
    # 10*1.25=12.5 and 50*1.25=62.5 land exactly on round()'s banker's-rounding boundary.
    assert (out.left, out.top, out.width, out.height) == (12, 25, 125, 62)


def test_window_scale_non_windows_or_no_handle_defaults_to_one():
    assert dpi.window_scale(0) == 1.0
