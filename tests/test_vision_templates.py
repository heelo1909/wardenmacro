import pytest

from tests.fixtures_frames import blank, make_template, paste
from warden.vision.templates import TemplateLibrary, match_template


@pytest.mark.parametrize("scale", [0.8, 1.0, 1.2])
def test_matches_template_across_scales(scale):
    template = make_template()
    frame = paste(blank(), template, (0.35, 0.40), scale=scale)
    match = match_template(frame, template, scale_min=0.75, scale_max=1.25, scale_steps=21)
    assert match is not None
    assert match.score > 0.85
    assert abs(match.scale - scale) < 0.05
    cx, cy = match.center
    assert abs(cx - (0.35 + 0.05 * scale)) < 0.03  # template is 120px wide -> ~0.0469 at 1280 width


def test_no_match_below_threshold_in_blank_frame():
    template = make_template()
    match = match_template(blank(), template, scale_steps=5)
    assert match is None or match.score < 0.5


def test_roi_restricts_search_area():
    template = make_template()
    frame = paste(blank(), template, (0.05, 0.05))
    far_roi_match = match_template(frame, template, roi=(0.5, 0.5, 1.0, 1.0), scale_steps=3)
    assert far_roi_match is None or far_roi_match.score < 0.5
    near_roi_match = match_template(frame, template, roi=(0.0, 0.0, 0.3, 0.3), scale_steps=3)
    assert near_roi_match is not None and near_roi_match.score > 0.85


def test_flat_template_does_not_crash(tmp_path):
    import numpy as np

    flat = (np.ones((40, 120, 3), dtype="uint8") * 100)
    assert match_template(blank(), flat, scale_steps=3) is None


def test_template_library_loads_reloads_and_warns_once(tmp_path, caplog):
    lib = TemplateLibrary(tmp_path)
    assert lib.get("missing.png") is None
    img = make_template()
    path = lib.save("sub/one.png", img)
    assert path.exists()
    loaded = lib.get("sub/one.png")
    assert loaded is not None and loaded.shape == img.shape
    # Mutate on disk; mtime-based cache must pick up the new content.
    lib.save("sub/one.png", make_template(bgr=(1, 2, 3)))
    reloaded = lib.get("sub/one.png")
    assert tuple(int(c) for c in reloaded[20, 60]) != tuple(int(c) for c in loaded[20, 60])
