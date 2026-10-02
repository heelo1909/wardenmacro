import shutil

import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from tests.fixtures_frames import GREEN_BGR, blank, draw_frac_rect  # noqa: E402
from warden.config import load_all  # noqa: E402
from warden.core.events import EventBus  # noqa: E402
from warden.gui.context import AppContext  # noqa: E402
from warden.gui.pages.calibration import CalibrationPage  # noqa: E402
from warden.gui.widgets import ImageCanvas  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def ctx(qapp, bundled_config, tmp_path):
    import shutil as _sh

    work = tmp_path / "config"
    _sh.copytree(bundled_config, work)
    loaded = load_all(work / "default.yaml")
    loaded.app.observe_only = True
    return AppContext(loaded, EventBus())


def test_image_canvas_selection_fractions_round_trip(qapp):
    canvas = ImageCanvas()
    canvas.resize(400, 300)
    frame = draw_frac_rect(blank(200, 100), (0.2, 0.2, 0.8, 0.8), GREEN_BGR)
    canvas.set_frame(frame)
    canvas._selection_px = (40, 20, 160, 80)  # frame pixels (200x100 frame)
    fx1, fy1, fx2, fy2 = canvas.selection_fractions()
    assert fx1 == pytest.approx(0.2, abs=0.01)
    assert fy1 == pytest.approx(0.2, abs=0.01)
    assert fx2 == pytest.approx(0.8, abs=0.01)
    assert fy2 == pytest.approx(0.8, abs=0.01)


def test_image_canvas_no_selection_returns_none(qapp):
    canvas = ImageCanvas()
    assert canvas.selection_fractions() is None


def test_load_image_from_disk(ctx, tmp_path):
    import cv2

    page = CalibrationPage(ctx, templates_root=tmp_path)
    frame = draw_frac_rect(blank(), (0.3, 0.3, 0.6, 0.6), GREEN_BGR)
    img_path = tmp_path / "test_frame.png"
    cv2.imwrite(str(img_path), frame)

    from PySide6.QtWidgets import QFileDialog

    QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (str(img_path), ""))
    page._load_image()
    assert page._frame is not None
    assert "test_frame.png" in page.result_label.text()


def test_capture_live_without_roblox_open_warns(ctx, tmp_path, monkeypatch):
    # Never touch a real Roblox window from a test (warden-testing-safety).
    monkeypatch.setattr("warden.vision.capture.grab_roblox_client", lambda focus=True: None)
    page = CalibrationPage(ctx, templates_root=tmp_path)
    page._capture_live()
    assert "roblox window" in page.result_label.text().lower()


def test_capture_live_works_without_a_running_session(ctx, tmp_path, monkeypatch):
    """Calibrating used to require Start - which ran the very loop that kept
    relaunching Roblox. It must now grab the client window directly."""
    frame = blank()
    monkeypatch.setattr("warden.vision.capture.grab_roblox_client", lambda focus=True: frame)
    assert ctx.tick_loop is None
    page = CalibrationPage(ctx, templates_root=tmp_path)
    page._capture_live()
    assert page._frame is frame
    assert "captured" in page.result_label.text().lower()


def test_saving_a_template_for_a_color_detector_switches_it_to_template(ctx, tmp_path):
    page = CalibrationPage(ctx, templates_root=tmp_path)
    assert ctx.app.detectors["lobby_play"].method == "color"
    page._frame = blank()
    page.screen_combo.setCurrentText("lobby_play")
    page.canvas.set_frame(page._frame)
    page.canvas._selection_px = (10, 10, 60, 40)
    page._save_template()
    cfg = ctx.app.detectors["lobby_play"]
    assert cfg.method == "template"
    assert (tmp_path / cfg.template.path).exists()


def test_save_template_without_selection_warns(ctx, tmp_path):
    page = CalibrationPage(ctx, templates_root=tmp_path)
    page._frame = blank()
    page._save_template()
    assert "selection" in page.result_label.text().lower()


def test_sample_hsv_applies_to_detector_config_and_persists(ctx, tmp_path):
    page = CalibrationPage(ctx, templates_root=tmp_path)
    page.screen_combo.setCurrentText("lobby_play")
    page._frame = draw_frac_rect(blank(), (0.2, 0.2, 0.8, 0.8), GREEN_BGR)
    page.canvas.set_frame(page._frame)
    page.canvas._selection_px = (
        int(0.2 * page._frame.shape[1]), int(0.2 * page._frame.shape[0]),
        int(0.8 * page._frame.shape[1]), int(0.8 * page._frame.shape[0]),
    )
    original = ctx.app.detectors["lobby_play"].hsv[0].lower
    page._sample_hsv()
    assert ctx.app.detectors["lobby_play"].hsv[0].lower != original
    assert "applied" in page.result_label.text().lower()
    assert ctx.app_path.exists()


def test_set_roi_applies_and_persists(ctx, tmp_path):
    page = CalibrationPage(ctx, templates_root=tmp_path)
    page.screen_combo.setCurrentText("health_bar")
    page._frame = blank()
    page.canvas.set_frame(page._frame)
    page.canvas._selection_px = (10, 10, 100, 50)
    page._set_roi()
    assert ctx.app.detectors["health_bar"].roi.as_list() != [0.30, 0.85, 0.70, 1.0]


def test_run_detection_reports_hit_and_confidence(ctx, tmp_path):
    page = CalibrationPage(ctx, templates_root=tmp_path)
    page.screen_combo.setCurrentText("lobby_play")
    cfg = ctx.app.detectors["lobby_play"]
    from warden.flows.calibration import apply_roi

    ctx.app.detectors["lobby_play"] = apply_roi(cfg, (0.0, 0.0, 1.0, 1.0))
    page._frame = draw_frac_rect(blank(), (0.42, 0.85, 0.58, 0.95), GREEN_BGR)
    page._run_detection()
    assert "hit=" in page.result_label.text()
    assert "confidence=" in page.result_label.text()


def test_weapon_tab_name_options_prefill_from_preset_and_owned_weapons(ctx, tmp_path):
    page = CalibrationPage(ctx, templates_root=tmp_path)
    page.weapon_slot_combo.setCurrentText("primary")
    names = [page.weapon_name_combo.itemText(i) for i in range(page.weapon_name_combo.count())]
    assert "Grenade Launcher" in names  # the glass_wrap preset's primary slot


def test_save_weapon_template_without_selection_warns(ctx, tmp_path):
    page = CalibrationPage(ctx, templates_root=tmp_path)
    page._save_weapon_template()
    assert "selection" in page.weapon_result.text().lower()


def test_save_weapon_template_without_a_name_warns(ctx, tmp_path):
    page = CalibrationPage(ctx, templates_root=tmp_path)
    page._weapon_frame_store = draw_frac_rect(blank(), (0.3, 0.3, 0.6, 0.6), GREEN_BGR)
    page.weapon_canvas.set_frame(page._weapon_frame_store)
    page.weapon_canvas._selection_px = (10, 10, 100, 50)
    page.weapon_name_combo.setCurrentText("")
    page._save_weapon_template()
    assert "name" in page.weapon_result.text().lower()


def test_save_weapon_template_saves_under_the_loadout_path(ctx, tmp_path):
    from warden.vision.templates import TemplateLibrary

    page = CalibrationPage(ctx, templates_root=tmp_path)
    page.weapon_slot_combo.setCurrentText("primary")
    page.weapon_name_combo.setCurrentText("Grenade Launcher")
    frame = draw_frac_rect(blank(), (0.3, 0.3, 0.6, 0.6), GREEN_BGR)
    page._weapon_frame_store = frame
    page.weapon_canvas.set_frame(frame)
    page.weapon_canvas._selection_px = (
        int(0.3 * frame.shape[1]), int(0.3 * frame.shape[0]),
        int(0.6 * frame.shape[1]), int(0.6 * frame.shape[0]),
    )
    page._save_weapon_template()
    assert "Saved" in page.weapon_result.text()

    expected = tmp_path / ctx.app.weapon_templates_dir / "primary" / "Grenade_Launcher.png"
    assert expected.exists()
    # The real loadout flow must be able to find it through the same path convention.
    lib = TemplateLibrary(tmp_path / ctx.app.weapon_templates_dir)
    from warden.flows.loadout import weapon_template_path

    assert lib.get(weapon_template_path("primary", "Grenade Launcher")) is not None


def test_unknown_gallery_lists_saved_frames(ctx, warden_home, tmp_path):
    import cv2

    unknown_dir = warden_home / "unknown"
    unknown_dir.mkdir(parents=True)
    cv2.imwrite(str(unknown_dir / "20260101_120000.png"), blank())
    page = CalibrationPage(ctx, templates_root=tmp_path)
    assert page.gallery_list.count() == 1


def test_make_template_from_gallery_without_selection_warns(ctx, warden_home, tmp_path):
    import cv2

    unknown_dir = warden_home / "unknown"
    unknown_dir.mkdir(parents=True)
    cv2.imwrite(str(unknown_dir / "20260101_120000.png"), blank())
    page = CalibrationPage(ctx, templates_root=tmp_path)
    page.gallery_list.setCurrentRow(0)
    page._make_template_from_gallery()
    assert "selection" in page.gallery_result.text().lower()


def test_make_template_from_gallery_with_selection_saves(ctx, warden_home, tmp_path):
    import cv2

    unknown_dir = warden_home / "unknown"
    unknown_dir.mkdir(parents=True)
    frame = draw_frac_rect(blank(), (0.3, 0.3, 0.6, 0.6), GREEN_BGR)
    cv2.imwrite(str(unknown_dir / "20260101_120000.png"), frame)
    page = CalibrationPage(ctx, templates_root=tmp_path)
    page.gallery_list.setCurrentRow(0)
    page.gallery_canvas._selection_px = (
        int(0.3 * frame.shape[1]), int(0.3 * frame.shape[0]),
        int(0.6 * frame.shape[1]), int(0.6 * frame.shape[0]),
    )
    page._make_template_from_gallery()
    assert "Saved" in page.gallery_result.text()
