"""Auto-capture + one-click calibration (2026-10-02: user found manual
capture/box/save confusing and asked for screenshots to be taken automatically)."""

import shutil

import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from tests.fixtures_frames import GREEN_BGR, blank, draw_frac_rect  # noqa: E402
from warden.config import load_all  # noqa: E402
from warden.core.events import EventBus  # noqa: E402
from warden.flows.calibration import (  # noqa: E402
    CAPTURE_STEPS,
    calibration_capture_path,
    expand_roi,
    is_screen_calibrated,
    quick_calibrate,
    selection_problem,
)
from warden.gui.context import AppContext  # noqa: E402
from warden.gui.guided_capture import GuidedCapture  # noqa: E402
from warden.gui.pages.calibration import CalibrationPage  # noqa: E402
from warden.vision.templates import TemplateLibrary  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def ctx(qapp, bundled_config, tmp_path):
    work = tmp_path / "config"
    shutil.copytree(bundled_config, work)
    loaded = load_all(work / "default.yaml")
    loaded.app.observe_only = True
    return AppContext(loaded, EventBus())


def test_selection_problem_rejects_whole_screen_boxes():
    assert selection_problem(None)
    assert "most of the screen" in selection_problem((0.0, 0.0, 0.98, 1.0))
    assert selection_problem((0.4, 0.4, 0.5, 0.45)) is None


def test_expand_roi_stays_in_bounds_and_contains_the_box():
    x1, y1, x2, y2 = expand_roi((0.9, 0.9, 0.99, 0.99))
    assert 0 <= x1 < 0.9 and 0 <= y1 < 0.9 and x2 == 1.0 and y2 == 1.0


def test_quick_calibrate_health_bar_learns_color_and_detects(ctx, tmp_path):
    from warden.vision.detectors import Detector

    frame = draw_frac_rect(blank(400, 200), (0.02, 0.95, 0.2, 0.98), (60, 230, 120))  # lime-ish
    lib = TemplateLibrary(tmp_path / "t")
    new, _ = quick_calibrate(ctx.app, "health_bar", frame, (0.02, 0.95, 0.2, 0.98), lib)
    assert new.method == "color" and new.params["calibrated"] == 1.0
    assert Detector("health_bar", new, lib).evaluate(frame).hit


def test_quick_calibrate_button_becomes_a_template(ctx, tmp_path):
    from warden.vision.detectors import Detector

    frame = blank(400, 200)
    frame[60:90, 100:180] = (40, 120, 230)
    frame[70:80, 120:160] = (255, 255, 255)
    lib = TemplateLibrary(tmp_path / "t")
    ctx.app.detectors["ffa_tile"] = ctx.app.detectors["ffa_tile"].model_copy(update={"ocr": None})
    new, _ = quick_calibrate(ctx.app, "ffa_tile", frame, (0.25, 0.3, 0.45, 0.45), lib)
    ctx.app.detectors["ffa_tile"] = new
    assert new.method == "template"
    assert is_screen_calibrated(ctx.app, "ffa_tile", lib)
    assert Detector("ffa_tile", new, lib).evaluate(frame).hit


def test_guided_capture_saves_each_step_and_finishes(qapp):
    frames, finished = [], []
    frame = np.full((90, 160, 3), 50, np.uint8)
    g = GuidedCapture(CAPTURE_STEPS[:2], grab=lambda: frame,
                      on_captured=lambda keys, f: frames.append(tuple(keys)),
                      on_finished=finished.append, countdown_s=3)
    g._do_capture()            # step 1 grabbed
    g._advance()
    g._do_capture()            # step 2 grabbed (mode menu fills two screens)
    g._advance()               # past the last step -> finish
    assert frames == [("lobby_play",), ("mode_list", "ffa_tile")]
    assert finished and set(finished[0]) == {"lobby_play", "mode_list", "ffa_tile"}


def test_guided_capture_retries_when_roblox_is_missing(qapp):
    got = []
    g = GuidedCapture(CAPTURE_STEPS[:1], grab=lambda: None,
                      on_captured=lambda k, f: got.append(k), on_finished=lambda c: None, countdown_s=3)
    g._do_capture()
    assert got == [] and g.index == 0
    assert "not found" in g.countdown_label.text().lower()
    g.finish()


def test_page_quick_save_with_auto_captured_frame(ctx, tmp_path, warden_home):
    import cv2

    frame = draw_frac_rect(blank(400, 200), (0.02, 0.95, 0.2, 0.98), (60, 230, 120))
    cv2.imwrite(str(calibration_capture_path("health_bar")), frame)
    page = CalibrationPage(ctx, templates_root=tmp_path)
    page.open_screen("health_bar")
    assert page._frame is not None and page._frame_source == "health_bar"
    page.canvas._selection_px = (8, 190, 80, 196)
    page._quick_save()
    assert "✓" in page.result_label.text()
    assert page.checklist_buttons["health_bar"].property("state") == "done"


def test_page_quick_save_refuses_a_giant_box(ctx, tmp_path):
    page = CalibrationPage(ctx, templates_root=tmp_path)
    page._frame = blank(400, 200)
    page.canvas.set_frame(page._frame)
    page.canvas._selection_px = (0, 0, 400, 200)
    page._quick_save()
    assert "most of the screen" in page.result_label.text()


def test_loadout_teacher_learns_from_clicks_on_the_list(qapp, tmp_path):
    import time

    from tests.test_behaviors_and_sequential_loadout import picker_frame
    from warden.config.schema import LoadoutUI
    from warden.flows.loadout import learn_row_template
    from warden.geometry import Rect
    from warden.gui.loadout_teacher import LoadoutTeacher

    ui = LoadoutUI(mode="sequential")
    saved, finished = {}, []
    frame = picker_frame(["Random", "Energy Rifle", "Grenade Launcher"])

    class Cap:
        hwnd = 0

        def grab(self, rect):
            return frame

    def learn(slot, weapon, f, fx, fy):
        crop = learn_row_template(f, fx, fy, ui)
        if crop is None:
            return False
        saved[slot] = (weapon, crop.shape)
        return True

    t = LoadoutTeacher({"primary": "Grenade Launcher", "secondary": "Slingshot"}, learn=learn,
                       on_finished=finished.append, find_client=lambda: (1, Rect(0, 0, 1280, 720)),
                       make_capturer=Cap)
    t._capture()
    time.sleep(0.05)
    now = time.monotonic()
    t.handle_click(now, 100, 300)          # off the list -> ignored
    assert t.current_slot() == "primary"
    t.handle_click(now, 640, 180 + 2 * 60 + 26)  # the Grenade Launcher row
    assert saved["primary"][0] == "Grenade Launcher"
    assert t.current_slot() == "secondary"
    t.finish()
    assert finished == [["primary"]]
