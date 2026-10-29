"""Mac port (warden-mac-handoff.md phases 1-4): Retina conversion, Quartz input,
key map, window detection with title bars, hotkeys, first-run defaults,
permissions, the setup screen, and --selftest.

Everything here fakes the macOS APIs, so it runs on Windows/Linux too; the
real-hardware checks are the handoff's Phase 5 checklist.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import numpy as np
import pytest
import yaml

from warden.geometry import Rect
from warden.platform import retina

from test_mac_platform import FakeQuartz, _cg_window, _FakeImage  # noqa: E402  (shared fakes)

ROOT = Path(__file__).resolve().parent.parent


# =================================================================== retina: pixels <-> points


@pytest.mark.parametrize("px, pt, expected", [(1440, 1440, 1.0), (2880, 1440, 2.0), (2940, 1470, 2.0),
                                               (2160, 1440, 1.5), (0, 100, 1.0), (100, 0, 1.0), (50, 100, 1.0)])
def test_backing_scale(px, pt, expected):
    assert retina.backing_scale(px, pt) == expected


@pytest.mark.parametrize("scale", [1.0, 2.0])
def test_pixel_point_round_trip_at_scale_1_and_2(scale):
    for x, y in [(0, 0), (10, 20), (733, 411), (1469, 955)]:
        px = retina.point_to_pixel(x, y, scale)
        assert px == (round(x * scale), round(y * scale))
        assert retina.pixel_to_point(*px, scale) == (x, y)


def test_frame_pixel_to_screen_point_on_retina_and_regular():
    client = Rect(100, 50, 800, 600)  # points
    # Centre of a 2x capture (1600x1200 px) -> centre of the window in points.
    assert retina.frame_px_to_screen_pt(800, 600, client, 2.0) == (500, 350)
    assert retina.frame_px_to_screen_pt(400, 300, client, 1.0) == (500, 350)


def test_rect_to_pixels():
    assert retina.rect_to_pixels(Rect(10, 20, 300, 200), 2.0) == Rect(20, 40, 600, 400)
    assert retina.rect_to_pixels(Rect(10, 20, 300, 200), 1.0) == Rect(10, 20, 300, 200)


def test_content_rect_trims_title_bar_only_when_windowed():
    display = retina.Display(Rect(0, 0, 1512, 982), 2.0)
    windowed = Rect(100, 100, 1000, 700)
    assert retina.content_rect(windowed, display, 28) == Rect(100, 128, 1000, 672)
    fullscreen = Rect(0, 0, 1512, 982)
    assert retina.content_rect(fullscreen, display, 28) == fullscreen
    assert retina.content_rect(windowed, display, 0) == windowed


def test_display_for_picks_the_display_under_the_window_centre():
    left = retina.Display(Rect(0, 0, 1512, 982), 2.0)
    right = retina.Display(Rect(1512, 0, 1920, 1080), 1.0)
    assert retina.display_for(Rect(1600, 100, 800, 600), [left, right]) is right
    assert retina.display_for(Rect(10, 10, 100, 100), [left, right]) is left
    assert retina.display_for(Rect(-5000, 0, 10, 10), [left, right]) is None


def test_to_point_size_downscales_retina_frames_and_leaves_1x_alone():
    from warden.vision.capture import to_point_size

    frame_1x = np.zeros((300, 400, 3), np.uint8)
    assert to_point_size(frame_1x, 400, 300) is frame_1x
    frame_2x = np.zeros((600, 800, 3), np.uint8)
    assert to_point_size(frame_2x, 400, 300).shape == (300, 400, 3)


def test_quartz_capture_clips_to_the_content_rect_and_returns_points(monkeypatch):
    from warden.vision.capture import WindowCapturer

    monkeypatch.setattr(sys, "platform", "darwin")
    quartz = FakeQuartz()
    w, h = 8, 6  # a 2x capture of a 4x3-point content rect
    quartz.images = {9: _FakeImage(w, h, bytes_per_row=w * 4, pixel_bytes=bytes([10, 20, 30, 255] * (w * h)))}
    monkeypatch.setitem(sys.modules, "Quartz", quartz)
    cap = WindowCapturer()
    cap.hwnd = 9
    frame = cap.grab(Rect(50, 78, 4, 3))
    assert cap.last_method == "window"
    assert quartz.last_capture_rect == (50, 78, 4, 3)
    assert frame.shape == (3, 4, 3)
    assert tuple(frame[0, 0]) == (10, 20, 30)


def test_screen_fallback_frames_are_also_point_sized_on_mac(monkeypatch):
    from warden.vision.capture import WindowCapturer

    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setitem(sys.modules, "Quartz", FakeQuartz())  # no image -> fallback

    class Retina2x:
        def grab(self, rect):
            return np.zeros((rect.height * 2, rect.width * 2, 3), np.uint8)

    cap = WindowCapturer(fallback=Retina2x())
    cap.hwnd = 1
    assert cap.grab(Rect(0, 0, 40, 30)).shape == (30, 40, 3)


def test_screen_fallback_frames_untouched_on_windows(monkeypatch):
    from warden.vision.capture import WindowCapturer

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(WindowCapturer, "_print_window", lambda self, *a: None)

    class Big:
        def grab(self, rect):
            return np.zeros((rect.height * 2, rect.width * 2, 3), np.uint8)

    cap = WindowCapturer(fallback=Big())
    assert cap.grab(Rect(0, 0, 40, 30)).shape == (60, 80, 3)  # Windows path unchanged


# =================================================================== MacWindows: title bar + detection


class _Pt:
    def __init__(self, x, y):
        self.x, self.y = x, y


class _Size:
    def __init__(self, w, h):
        self.width, self.height = w, h


class _CGRect:
    def __init__(self, x, y, w, h):
        self.origin, self.size = _Pt(x, y), _Size(w, h)


class DisplayQuartz(FakeQuartz):
    """FakeQuartz plus the display APIs MacWindows.displays() uses."""

    def __init__(self, windows=(), displays=((0, 0, 1512, 982, 3024),)):
        super().__init__(windows)
        self._displays = list(displays)

    def CGGetActiveDisplayList(self, _max, _a, _b):
        return 0, tuple(range(len(self._displays))), len(self._displays)

    def CGDisplayBounds(self, did):
        x, y, w, h, _ = self._displays[did]
        return _CGRect(x, y, w, h)

    def CGDisplayCopyDisplayMode(self, did):
        return did

    def CGDisplayModeGetPixelWidth(self, mode):
        return self._displays[mode][4]


@pytest.fixture
def mac_backend(monkeypatch):
    import test_mac_platform as tmp_mod
    import warden.platform.window_mac as window_mac_mod

    def build(windows, pid_names, displays=((0, 0, 1512, 982, 3024),), title_bar_pt=28):
        quartz = DisplayQuartz(windows, displays)
        apps = {pid: tmp_mod.FakeApp(pid) for pid in pid_names}
        monkeypatch.setitem(sys.modules, "Quartz", quartz)
        monkeypatch.setitem(sys.modules, "AppKit", tmp_mod._fake_appkit(apps, None))
        monkeypatch.setattr(window_mac_mod.sys, "platform", "darwin")
        monkeypatch.setattr("psutil.Process", tmp_mod.FakeProcess)
        tmp_mod.FakeProcess.names = pid_names
        return window_mac_mod.MacWindows(title_bar_pt=title_bar_pt)

    return build


def test_windowed_roblox_has_its_title_bar_trimmed(mac_backend):
    backend = mac_backend([_cg_window(5, 100, "Roblox", x=100, y=60, w=1000, h=700)], {100: "robloxplayer"})
    (win,) = backend.list_windows()
    assert win.client == Rect(100, 88, 1000, 672)


def test_fullscreen_roblox_is_left_whole(mac_backend):
    backend = mac_backend([_cg_window(5, 100, "Roblox", x=0, y=0, w=1512, h=982)], {100: "robloxplayer"})
    (win,) = backend.list_windows()
    assert win.client == Rect(0, 0, 1512, 982)


def test_displays_report_retina_scale(mac_backend):
    backend = mac_backend([], {}, displays=((0, 0, 1512, 982, 3024), (1512, 0, 1920, 1080, 1920)))
    assert [d.scale for d in backend.displays()] == [2.0, 1.0]


def test_roblox_detected_from_a_fake_window_list_ignoring_browsers(mac_backend, monkeypatch):
    from warden.platform import window as window_mod

    monkeypatch.setattr(window_mod.sys, "platform", "darwin")
    windows = [
        _cg_window(1, 200, "Roblox - Google Chrome", w=1400, h=900),       # browser tab titled Roblox
        _cg_window(2, 100, "Roblox", x=50, y=40, w=1200, h=800),            # the real client
        _cg_window(3, 300, "Warden", w=900, h=600),                         # Warden itself
        _cg_window(4, 100, "", onscreen=False, w=300, h=200),               # hidden helper window
    ]
    backend = mac_backend(windows, {100: "robloxplayer", 200: "google chrome", 300: "warden"})
    client = window_mod.pick_client(backend.list_windows())
    assert client is not None and client.hwnd == 2
    assert client.client == Rect(50, 68, 1200, 772)


def test_title_bar_setting_comes_from_config(mac_backend, monkeypatch):
    import warden.platform.window_mac as window_mac_mod
    from warden.config.schema import AppConfig
    from warden.platform import macos

    monkeypatch.setattr(window_mac_mod, "TITLE_BAR_PT", 28)
    cfg = AppConfig()
    cfg.mac.title_bar_pt = 32
    macos.configure(cfg, platform="darwin")
    assert window_mac_mod.TITLE_BAR_PT == 32
    backend = mac_backend([_cg_window(5, 100, x=0, y=100, w=800, h=600)], {100: "robloxplayer"}, title_bar_pt=None)
    assert backend.list_windows()[0].client.top == 132


# =================================================================== Quartz input + key map


def test_every_warden_key_has_a_unique_mac_key_code():
    from warden.platform.input import SCAN_CODES
    from warden.platform.input_mac import MAC_KEYCODES

    assert set(SCAN_CODES) == set(MAC_KEYCODES)
    assert len(set(MAC_KEYCODES.values())) == len(MAC_KEYCODES)


@pytest.mark.parametrize("key, code", [("W", 0x0D), ("A", 0x00), ("S", 0x01), ("D", 0x02), ("SPACE", 0x31),
                                       ("ESCAPE", 0x35), ("1", 0x12), ("4", 0x15), ("F8", 0x64), ("SHIFT", 0x38)])
def test_known_mac_key_codes(key, code):
    from warden.platform.input_mac import mac_keycode

    assert mac_keycode(key) == code


def test_unknown_key_raises():
    from warden.platform.input_mac import mac_keycode

    with pytest.raises(ValueError):
        mac_keycode("NUMPAD7")


class EventQuartz:
    """Records CGEvents instead of posting them."""

    kCGHIDEventTap = 0
    kCGEventMouseMoved, kCGEventLeftMouseDown, kCGEventLeftMouseUp = 5, 1, 2
    kCGEventRightMouseDown, kCGEventRightMouseUp = 3, 4
    kCGEventOtherMouseDown, kCGEventOtherMouseUp = 25, 26
    kCGEventLeftMouseDragged, kCGEventRightMouseDragged, kCGEventOtherMouseDragged = 6, 7, 27
    kCGMouseButtonLeft, kCGMouseButtonRight, kCGMouseButtonCenter = 0, 1, 2
    kCGMouseEventDeltaX, kCGMouseEventDeltaY = 4, 5
    kCGScrollEventUnitLine = 1

    def __init__(self):
        self.posted: list[dict] = []
        self.cursor = (100.0, 200.0)

    def CGEventCreate(self, _src):
        return {}

    def CGEventGetLocation(self, _e):
        return types.SimpleNamespace(x=self.cursor[0], y=self.cursor[1])

    def CGEventCreateMouseEvent(self, _src, etype, pos, button):
        return {"kind": "mouse", "type": etype, "pos": pos, "button": button}

    def CGEventCreateKeyboardEvent(self, _src, code, down):
        return {"kind": "key", "code": code, "down": down}

    def CGEventCreateScrollWheelEvent(self, _src, unit, count, delta):
        return {"kind": "wheel", "unit": unit, "delta": delta}

    def CGEventSetIntegerValueField(self, event, field, value):
        event[f"field{field}"] = value

    def CGEventSetFlags(self, event, flags):
        event["flags"] = flags

    def CGEventPost(self, tap, event):
        self.posted.append(event)


def test_quartz_click_sequence():
    from warden.platform.input_mac import QuartzMethod

    q = EventQuartz()
    m = QuartzMethod(quartz=q)
    m.move_abs(300, 400)
    m.button("left", True)
    m.move_rel(5, -3)
    m.button("left", False)
    kinds = [(e["kind"], e["type"]) for e in q.posted]
    assert kinds == [("mouse", q.kCGEventMouseMoved), ("mouse", q.kCGEventLeftMouseDown),
                     ("mouse", q.kCGEventLeftMouseDragged), ("mouse", q.kCGEventLeftMouseUp)]
    assert q.posted[0]["pos"] == (300.0, 400.0)
    drag = q.posted[2]
    assert drag["field4"] == 5 and drag["field5"] == -3  # camera-look deltas
    assert drag["pos"] == (105.0, 197.0)


def test_quartz_keys_carry_held_modifier_flags():
    from warden.platform.input_mac import QuartzMethod

    q = EventQuartz()
    m = QuartzMethod(quartz=q)
    m.key("SHIFT", True)
    m.key("W", True)
    m.key("W", False)
    m.key("SHIFT", False)
    m.key("W", True)
    assert [e["code"] for e in q.posted] == [0x38, 0x0D, 0x0D, 0x38, 0x0D]
    assert q.posted[1]["flags"] == 0x00020000
    assert "flags" not in q.posted[4]


def test_quartz_wheel_and_right_click():
    from warden.platform.input_mac import QuartzMethod

    q = EventQuartz()
    m = QuartzMethod(quartz=q)
    m.wheel(-1)
    m.button("right", True)
    m.button("right", False)
    assert q.posted[0] == {"kind": "wheel", "unit": 1, "delta": -1}
    assert [e["type"] for e in q.posted[1:]] == [q.kCGEventRightMouseDown, q.kCGEventRightMouseUp]


def test_quartz_method_refuses_off_mac(monkeypatch):
    from warden.platform.input_mac import QuartzMethod

    monkeypatch.setattr(sys, "platform", "linux")
    with pytest.raises(OSError):
        QuartzMethod()


def test_input_controller_drives_quartz_end_to_end():
    from warden.platform.input import InputController
    from warden.platform.input_mac import QuartzMethod

    class Gate:
        def is_focused(self):
            return True

    q = EventQuartz()
    ctrl = InputController([QuartzMethod(quartz=q)], Gate(), rect=lambda: Rect(0, 28, 1000, 600),
                           sleep=lambda s: None)
    assert ctrl.click_frac(0.5, 0.5)
    assert ctrl.key_tap("ESCAPE")
    first = q.posted[0]
    assert first["type"] == q.kCGEventMouseMoved and first["pos"] == (500.0, 328.0)
    assert any(e.get("code") == 0x35 for e in q.posted)


def test_quartz_goes_first_on_mac_only():
    from warden.platform.input import effective_order

    default = ["sendinput", "pydirectinput", "pynput"]
    assert effective_order(default, "darwin") == ["quartz", *default]
    assert effective_order(["quartz", "pynput"], "darwin") == ["quartz", "pynput"]
    assert effective_order(default, "win32") == default
    assert effective_order(default, "linux") == default


def test_input_config_accepts_quartz():
    from warden.config.schema import InputConfig

    assert InputConfig(methods=["quartz", "pynput"]).methods == ["quartz", "pynput"]
    assert InputConfig().methods == ["sendinput", "pydirectinput", "pynput"]  # Windows default unchanged


# =================================================================== hotkeys


def test_parse_combo():
    from warden.platform.hotkeys import parse_combo

    assert parse_combo("ctrl+shift+s") == (frozenset({"ctrl", "shift"}), "S")
    assert parse_combo("F8") == (frozenset(), "F8")
    assert parse_combo("Option+Command+1") == (frozenset({"alt", "cmd"}), "1")
    with pytest.raises(ValueError):
        parse_combo("ctrl+shift")


def test_combo_matcher_needs_exact_modifiers():
    from warden.platform.hotkeys import ComboMatcher

    fired = []
    m = ComboMatcher({"ctrl+shift+s": lambda: fired.append("start"), "F8": lambda: fired.append("stop")})
    m.press("S")
    assert fired == []
    m.press("ctrl")
    m.press("shift")
    m.press("S")
    assert fired == ["start"]
    m.press("F8")  # ctrl+shift still held -> not a bare F8
    assert fired == ["start"]
    m.release("ctrl")
    m.release("shift")
    m.press("F8")
    assert fired == ["start", "stop"]


def test_mac_key_names_from_pynput_keys():
    from warden.platform.hotkeys import _mac_key_name

    Key = types.SimpleNamespace
    assert _mac_key_name(Key(name="ctrl_l")) == "ctrl"
    assert _mac_key_name(Key(name="shift_r")) == "shift"
    assert _mac_key_name(Key(name="cmd")) == "cmd"
    assert _mac_key_name(Key(name="f8")) == "F8"
    assert _mac_key_name(Key(vk=0x01)) == "S"  # KeyCode with a control char: matched by key code
    assert _mac_key_name(Key(name="esc", value=Key(vk=0x35))) == "ESCAPE"
    assert _mac_key_name(Key(vk=0x7F)) is None


def test_hotkeys_use_keycode_listener_on_mac_and_global_hotkeys_elsewhere(monkeypatch):
    from warden.platform.hotkeys import Hotkeys

    made = {}

    class Listener:
        def __init__(self, on_press=None, on_release=None):
            made["listener"] = (on_press, on_release)

        def start(self):
            made["started"] = True

        def stop(self):
            pass

    class GlobalHotKeys:
        def __init__(self, mapping):
            made["global"] = mapping

        def start(self):
            pass

    fake_keyboard = types.SimpleNamespace(Listener=Listener, GlobalHotKeys=GlobalHotKeys)
    monkeypatch.setitem(sys.modules, "pynput", types.SimpleNamespace(keyboard=fake_keyboard))
    monkeypatch.setitem(sys.modules, "pynput.keyboard", fake_keyboard)

    fired = []
    hk = Hotkeys({"ctrl+shift+s": lambda: fired.append(1)}, platform="darwin")
    assert hk.start() and made.get("started")
    on_press, _ = made["listener"]
    on_press(types.SimpleNamespace(name="ctrl"))
    on_press(types.SimpleNamespace(name="shift"))
    on_press(types.SimpleNamespace(vk=0x01))
    assert fired == [1]

    Hotkeys({"F6": lambda: None}, platform="win32").start()
    assert list(made["global"]) == ["<f6>"]


# =================================================================== first-run defaults, OCR


def test_mac_first_run_defaults():
    from warden.platform.macos import MAC_HOTKEYS, mac_first_run_defaults

    data = yaml.safe_load((ROOT / "config" / "default.yaml").read_text(encoding="utf-8"))
    out = mac_first_run_defaults(data)
    assert out["hotkeys"] == MAC_HOTKEYS
    assert out["input"]["methods"] == ["quartz", "pynput"]
    assert out["estimate"]["ocr_verify"] is False
    assert out["mac"]["ocr"] is False


def test_mac_defaults_keep_a_hotkey_the_user_already_changed():
    from warden.platform.macos import mac_first_run_defaults

    out = mac_first_run_defaults({"hotkeys": {"start": "ctrl+alt+g", "pause": "F7"}})
    assert out["hotkeys"]["start"] == "ctrl+alt+g"
    assert out["hotkeys"]["pause"] == "ctrl+shift+p"


def test_seeding_on_a_mac_writes_mac_defaults_and_validates(monkeypatch, warden_home):
    from warden.config import loader

    monkeypatch.setattr(loader.sys, "platform", "darwin")
    loaded = loader.load_all()
    assert loaded.app.hotkeys.start == "ctrl+shift+s"
    assert loaded.app.input.methods == ["quartz", "pynput"]
    assert loaded.app.estimate.ocr_verify is False
    assert loaded.app.mac.ocr is False


def test_seeding_on_windows_is_a_byte_for_byte_copy(monkeypatch, warden_home):
    from warden.config import loader

    monkeypatch.setattr(loader.sys, "platform", "win32")
    loaded = loader.load_all()
    assert loaded.app_path.read_bytes() == (ROOT / "config" / "default.yaml").read_bytes()
    assert loaded.app.hotkeys.start == "F6"


def test_configure_is_a_noop_off_mac(monkeypatch):
    import warden.platform.window_mac as window_mac_mod
    from warden.config.schema import AppConfig
    from warden.platform import macos
    from warden.vision import ocr

    monkeypatch.setattr(window_mac_mod, "TITLE_BAR_PT", 28)
    monkeypatch.setattr(ocr, "_enabled", True)
    cfg = AppConfig()
    cfg.mac.title_bar_pt = 40
    macos.configure(cfg, platform="win32")
    assert window_mac_mod.TITLE_BAR_PT == 28 and ocr._enabled is True


def test_ocr_off_by_default_on_mac(monkeypatch):
    from warden.config.schema import AppConfig
    from warden.platform import macos
    from warden.vision import ocr

    monkeypatch.setattr(ocr, "_enabled", True)
    monkeypatch.setattr(ocr, "_find_engine", lambda: object())  # pretend Tesseract is installed
    assert ocr.available()
    macos.configure(AppConfig(), platform="darwin")
    assert not ocr.available()
    assert ocr.read_text(np.zeros((40, 40, 3), np.uint8)) is None  # callers already cope with None


# =================================================================== permissions


class FakeApi:
    def __init__(self, **granted):
        self.granted = {"accessibility": False, "screen_recording": False, "input_monitoring": False, **granted}
        self.requested = []

    def accessibility(self):
        return self.granted["accessibility"]

    def screen_recording(self):
        return self.granted["screen_recording"]

    def input_monitoring(self):
        return self.granted["input_monitoring"]

    def request_accessibility(self):
        self.requested.append("accessibility")

    def request_screen_recording(self):
        self.requested.append("screen_recording")

    def request_input_monitoring(self):
        self.requested.append("input_monitoring")


def test_permission_checker_status_and_deep_links():
    from warden.platform.permissions_mac import PERMISSIONS, PermissionChecker

    opened = []
    checker = PermissionChecker(api=FakeApi(accessibility=True), opener=lambda url: opened.append(url) or True)
    assert checker.status() == {"accessibility": True, "screen_recording": False, "input_monitoring": False}
    assert not checker.all_granted()
    assert checker.open_settings("screen_recording")
    assert opened == ["x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"]
    assert {p.key for p in PERMISSIONS} == {"accessibility", "screen_recording", "input_monitoring"}
    assert all(p.why.endswith(".") and p.steps for p in PERMISSIONS)


def test_failed_deep_link_reports_false():
    from warden.platform.permissions_mac import PermissionChecker

    def broken(url):
        raise OSError("no such pane")

    assert PermissionChecker(api=FakeApi(), opener=broken).open_settings("accessibility") is False
    assert PermissionChecker(api=FakeApi(), opener=lambda u: False).open_settings("input_monitoring") is False


def test_a_crashing_check_counts_as_not_granted():
    from warden.platform.permissions_mac import PermissionChecker

    api = FakeApi()
    api.accessibility = lambda: 1 / 0
    assert PermissionChecker(api=api).status()["accessibility"] is False


def test_relaunch_command():
    from warden.platform.permissions_mac import relaunch_command

    exe = "/Applications/Warden.app/Contents/MacOS/Warden"
    assert relaunch_command(exe, frozen=True) == ["open", "-n", "/Applications/Warden.app"]
    assert relaunch_command("/usr/bin/python3", frozen=False) == ["/usr/bin/python3", "-m", "warden"]


# =================================================================== Mac setup screen (GUI)


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6.QtWidgets")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def _checker(api, opened=None):
    from warden.platform.permissions_mac import PermissionChecker

    return PermissionChecker(api=api, opener=lambda url: (opened.append(url) if opened is not None else None) or True)


def test_setup_page_shows_all_three_permissions(qapp):
    from warden.gui.pages.mac_setup import GRANTED, MISSING, MacSetupPage

    api = FakeApi(input_monitoring=True)
    page = MacSetupPage(_checker(api), relaunch=lambda: None, poll_ms=0)
    assert list(page.rows) == ["accessibility", "screen_recording", "input_monitoring"]
    assert page.rows["input_monitoring"].chip.text() == GRANTED
    assert page.rows["accessibility"].chip.text() == MISSING
    assert not page.rows["accessibility"].button.isHidden()
    assert page.rows["input_monitoring"].button.isHidden()
    assert "Accessibility" in page.summary.text() and "Screen Recording" in page.summary.text()
    assert not page.all_granted()


def test_setup_page_open_button_requests_opens_and_shows_steps(qapp):
    from warden.gui.pages.mac_setup import MacSetupPage

    api, opened = FakeApi(), []
    page = MacSetupPage(_checker(api, opened), relaunch=lambda: None, poll_ms=0)
    page.rows["accessibility"].button.click()
    assert api.requested == ["accessibility"]
    assert opened and opened[0].endswith("Privacy_Accessibility")
    assert not page.rows["accessibility"].steps.isHidden()


def test_setup_page_offers_reopen_after_screen_recording(qapp):
    from warden.gui.pages.mac_setup import GRANTED, MacSetupPage

    relaunched = []
    api = FakeApi(accessibility=True, input_monitoring=True)
    page = MacSetupPage(_checker(api), relaunch=lambda: relaunched.append(1), poll_ms=0)
    assert page.reopen_btn.isHidden()
    page.rows["screen_recording"].button.click()  # macOS may still say "no" until restart
    assert not page.reopen_btn.isHidden()
    api.granted["screen_recording"] = True
    page.refresh()
    assert page.rows["screen_recording"].chip.text() == GRANTED
    page.reopen_btn.click()
    assert relaunched == [1]


def test_setup_page_all_granted(qapp):
    from warden.gui.pages.mac_setup import MacSetupPage

    api = FakeApi(accessibility=True, screen_recording=True, input_monitoring=True)
    page = MacSetupPage(_checker(api), relaunch=lambda: None, poll_ms=0)
    assert page.all_granted() and page.reopen_btn.isHidden()
    assert page.summary.text().startswith("All set")


def _loaded_config(bundled_config):
    from warden.config import load_all

    return load_all(bundled_config / "default.yaml", bundled_config / "presets")


def test_main_window_opens_on_mac_setup_while_permissions_are_missing(qapp, bundled_config, monkeypatch):
    from warden.gui import main_window
    from warden.gui.main_window import MAC_SETUP_PAGE, PAGES, MainWindow

    monkeypatch.setattr(main_window.MainWindow, "_setup_hotkeys", lambda self: None)
    window = MainWindow(_loaded_config(bundled_config), mac_setup=True,
                        permission_checker=_checker(FakeApi()))
    assert window.page_names == PAGES + (MAC_SETUP_PAGE,)
    assert window.stack.count() == len(PAGES) + 1
    assert window.stack.currentIndex() == len(PAGES)
    window._on_nav_clicked(len(PAGES))  # clicking the extra page must not index past PAGES
    window.close()


def test_main_window_starts_on_home_once_everything_is_granted(qapp, bundled_config, monkeypatch):
    from warden.gui import main_window
    from warden.gui.main_window import MainWindow

    monkeypatch.setattr(main_window.MainWindow, "_setup_hotkeys", lambda self: None)
    api = FakeApi(accessibility=True, screen_recording=True, input_monitoring=True)
    window = MainWindow(_loaded_config(bundled_config), mac_setup=True, permission_checker=_checker(api))
    assert window.stack.currentIndex() == 0
    window.close()


def test_main_window_has_no_mac_page_on_windows(qapp, bundled_config, monkeypatch):
    from warden.gui import main_window
    from warden.gui.main_window import PAGES, MainWindow

    monkeypatch.setattr(main_window.MainWindow, "_setup_hotkeys", lambda self: None)
    window = MainWindow(_loaded_config(bundled_config), mac_setup=False)
    assert window.page_names == PAGES and window.stack.count() == len(PAGES)
    assert "Mac setup" not in window.pages
    window.close()


# =================================================================== --selftest


def test_selftest_passes_here_and_reports_platform(capsys):
    from warden.tools import selftest

    lines = []
    assert selftest.run(platform_name=sys.platform if sys.platform != "darwin" else "linux",
                        emit=lines.append) == 0
    text = lines[0]
    assert "RESULT    PASS" in text and "bundled config validates" in text and "first-run config seed" in text


def test_selftest_fails_cleanly_when_mac_bindings_are_missing(monkeypatch):
    from warden.tools import selftest

    if sys.platform == "darwin":
        pytest.skip("real Mac: the bindings exist")
    monkeypatch.setitem(sys.modules, "Quartz", None)  # import -> ImportError
    lines = []
    assert selftest.run(platform_name="darwin", emit=lines.append) == 1
    assert "FAIL  import Quartz" in lines[0] and "RESULT    FAIL" in lines[0]


def test_cli_selftest_flag(monkeypatch):
    import warden.__main__ as entry
    from warden.tools import selftest

    seen = {}
    monkeypatch.setattr(selftest, "run", lambda emit: seen.setdefault("ran", 0))
    assert entry.main(["--selftest"]) == 0 and "ran" in seen


# =================================================================== packaging + CI files


def test_mac_release_workflow_shape():
    wf = yaml.safe_load((ROOT / ".github" / "workflows" / "mac-release.yml").read_text(encoding="utf-8"))
    on = wf.get("on") or wf.get(True)  # PyYAML reads a bare `on:` key as True
    assert "v*" in on["push"]["tags"]
    build = wf["jobs"]["build"]
    runners = {entry["runner"] for entry in build["strategy"]["matrix"]["include"]}
    assert runners == {"macos-15", "macos-15-intel"}
    steps = "\n".join(str(s.get("run", "")) for s in build["steps"])
    assert "pytest" in steps and "--selftest" in steps and "build_dmg.sh" in steps
    assert wf["jobs"]["release"]["needs"] == "build"
    assert wf["permissions"]["contents"] == "write"
    text = (ROOT / ".github" / "workflows" / "mac-release.yml").read_text(encoding="utf-8")
    assert "secrets." not in text.replace("secrets.GITHUB_TOKEN", "")  # no secrets beyond the built-in token


def test_build_dmg_script_uses_hdiutil_with_applications_link():
    script = (ROOT / "scripts" / "mac" / "build_dmg.sh").read_text(encoding="utf-8")
    assert 'hdiutil create -volname "Warden"' in script
    assert "-format UDZO" in script and "ln -s /Applications" in script


def test_spec_bundle_identifier_and_windows_branch_unchanged():
    spec = (ROOT / "warden.spec").read_text(encoding="utf-8")
    assert 'bundle_identifier="com.heelo1909.warden"' in spec
    assert 'icon=None,  # set once a real Lucide/MIT icon is chosen and converted to .ico' in spec
