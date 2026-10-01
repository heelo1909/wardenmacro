import pytest

from tests.fixtures_frames import GREEN_BGR, blank, draw_frac_rect, make_template
from warden.config.schema import DetectorConfig
from warden.flows.calibration import (
    apply_hsv,
    apply_roi,
    crop_frame,
    list_unknown_frames,
    make_template_from_unknown,
    parse_contract_hours,
    px_rect_to_fractions,
    sample_hsv_from_selection,
    save_template_from_frame,
)
from warden.vision.templates import TemplateLibrary


def test_px_rect_to_fractions_normalizes_and_clamps():
    # Dragged bottom-right to top-left (reversed) - must still come out ordered.
    assert px_rect_to_fractions(80, 40, 20, 10, 100, 100) == (0.2, 0.1, 0.8, 0.4)


def test_px_rect_to_fractions_clamps_out_of_bounds():
    fx1, fy1, fx2, fy2 = px_rect_to_fractions(-10, -10, 200, 200, 100, 100)
    assert (fx1, fy1, fx2, fy2) == (0.0, 0.0, 1.0, 1.0)


def test_px_rect_to_fractions_never_degenerates_to_a_zero_size_box():
    fx1, fy1, fx2, fy2 = px_rect_to_fractions(50, 50, 50, 50, 100, 100)
    assert fx2 > fx1 and fy2 > fy1


def test_crop_frame_and_save_template_roundtrip(tmp_path):
    frame = draw_frac_rect(blank(), (0.3, 0.3, 0.6, 0.5), GREEN_BGR)
    lib = TemplateLibrary(tmp_path)
    path = save_template_from_frame(lib, "lobby_play.png", frame, (0.3, 0.3, 0.6, 0.5))
    assert path.exists()
    loaded = lib.get("lobby_play.png")
    assert loaded is not None
    cropped = crop_frame(frame, (0.3, 0.3, 0.6, 0.5))
    assert loaded.shape == cropped.shape


def test_sample_hsv_from_selection_covers_the_drawn_color():
    frame = draw_frac_rect(blank(), (0.2, 0.2, 0.8, 0.8), GREEN_BGR)
    lower, upper = sample_hsv_from_selection(frame, (0.2, 0.2, 0.8, 0.8))
    assert len(lower) == 3 and len(upper) == 3
    assert all(lo <= hi for lo, hi in zip(lower, upper))


def test_apply_roi_returns_a_new_config_without_mutating_the_original():
    cfg = DetectorConfig(method="color", hsv=[{"lower": (0, 0, 0), "upper": (10, 10, 10)}],
                         roi=[0.0, 0.0, 1.0, 1.0])
    updated = apply_roi(cfg, (0.1, 0.2, 0.3, 0.4))
    assert updated.roi.as_list() == [0.1, 0.2, 0.3, 0.4]
    assert cfg.roi.as_list() == [0.0, 0.0, 1.0, 1.0]  # original untouched


def test_apply_hsv_returns_a_new_config():
    cfg = DetectorConfig(method="color", hsv=[{"lower": (0, 0, 0), "upper": (10, 10, 10)}])
    updated = apply_hsv(cfg, [40, 100, 100], [80, 255, 255])
    assert updated.hsv[0].lower == (40, 100, 100)
    assert cfg.hsv[0].lower == (0, 0, 0)


def test_list_unknown_frames_newest_first(tmp_path):
    import time

    for i in range(3):
        (tmp_path / f"frame_{i}.png").write_bytes(b"\x89PNG")
        time.sleep(0.01)
    names = [p.name for p in list_unknown_frames(tmp_path)]
    assert names == ["frame_2.png", "frame_1.png", "frame_0.png"]


def test_make_template_from_unknown_crops_and_saves(tmp_path):
    import cv2

    frame = draw_frac_rect(blank(), (0.4, 0.4, 0.6, 0.6), GREEN_BGR)
    unknown_path = tmp_path / "unknown" / "20260101_000000.png"
    unknown_path.parent.mkdir(parents=True)
    cv2.imwrite(str(unknown_path), frame)

    lib = TemplateLibrary(tmp_path / "templates")
    saved = make_template_from_unknown(lib, unknown_path, "custom/new_icon.png", (0.4, 0.4, 0.6, 0.6))
    assert saved.exists()


def test_make_template_from_unknown_unreadable_file_raises(tmp_path):
    bad = tmp_path / "not_an_image.png"
    bad.write_text("not a png")
    lib = TemplateLibrary(tmp_path / "templates")
    with pytest.raises(ValueError):
        make_template_from_unknown(lib, bad, "x.png", (0, 0, 1, 1))


@pytest.mark.parametrize("text,expected", [
    ("12h 53m / 1d 0h 0m", 12 + 53 / 60),
    ("1d 0h 0m", 24.0),
    ("0h 5m", 5 / 60),
    (None, None),
    ("no numbers here", None),
    ("", None),
])
def test_parse_contract_hours(text, expected):
    result = parse_contract_hours(text)
    if expected is None:
        assert result is None
    else:
        assert result == pytest.approx(expected, abs=1e-6)
