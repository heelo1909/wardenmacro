"""macOS support, tested the same way the rest of this project tests
platform-specific code it can't run live (see tests/test_power.py,
tests/test_window.py): fake just enough of the OS-level API surface that the
*logic* built on top of it is exercised without needing pyobjc installed or
real macOS hardware - this project is developed and tested without a Mac.

Quartz/AppKit are faked with plain objects shaped like the documented API
(dict keys CGWindowListCopyWindowInfo returns, the handful of CoreGraphics
functions used for capture, NSRunningApplication's activate/terminate). None
of this proves the real frameworks behave identically - only that Warden's
own code does the right thing with whatever they hand back.
"""

from __future__ import annotations

import ctypes.util  # noqa: F401 (see below)
import subprocess
import sys
import types

import numpy as np
import psutil  # noqa: F401
import pytest

from warden.geometry import Rect

# Importing these two here, before any test monkeypatches sys.platform,
# matters: psutil (and ctypes.util, which it uses) picks its OS backend the
# first time it's imported in this process by inspecting the *real*
# sys.platform. If that first import instead happens lazily, inside a test
# that has already patched sys.platform to "darwin" to exercise mac-only
# code, it tries to load psutil's real macOS backend module on this Linux
# box, fails, and leaves `psutil` half-initialized in sys.modules for every
# test that runs afterwards - not just the one that did the patching. Doing
# the real import first, while sys.platform is still whatever this machine
# actually is, means every later `import psutil` in this file (however
# sys.platform has been monkeypatched by then) just reuses this same,
# correctly-initialized module.


# =================================================================== paths.data_home()


def test_data_home_uses_application_support_on_macos(monkeypatch, tmp_path):
    import warden.paths as paths_mod

    monkeypatch.delenv("WARDEN_HOME", raising=False)
    monkeypatch.setattr(paths_mod.sys, "platform", "darwin")
    monkeypatch.setattr(paths_mod.Path, "home", lambda: tmp_path)
    assert paths_mod.data_home() == tmp_path / "Library" / "Application Support" / "Warden"


def test_warden_home_override_still_wins_on_macos(monkeypatch, tmp_path):
    import warden.paths as paths_mod

    monkeypatch.setenv("WARDEN_HOME", str(tmp_path / "custom"))
    monkeypatch.setattr(paths_mod.sys, "platform", "darwin")
    assert paths_mod.data_home() == tmp_path / "custom"


# =================================================================== window.make_window_backend()


def test_make_window_backend_dispatches_to_win32(monkeypatch):
    import warden.platform.window as window_mod

    sentinel = object()
    monkeypatch.setattr(window_mod, "Win32Windows", lambda: sentinel)
    monkeypatch.setattr(window_mod.sys, "platform", "win32")
    assert window_mod.make_window_backend() is sentinel


def test_make_window_backend_dispatches_to_mac(monkeypatch):
    import warden.platform.window as window_mod

    sentinel = object()
    fake_module = types.SimpleNamespace(MacWindows=lambda: sentinel)
    monkeypatch.setitem(sys.modules, "warden.platform.window_mac", fake_module)
    monkeypatch.setattr(window_mod.sys, "platform", "darwin")
    assert window_mod.make_window_backend() is sentinel


def test_make_window_backend_gives_an_actionable_error_without_pyobjc(monkeypatch):
    import warden.platform.window as window_mod

    def boom():
        raise ImportError("no module named Quartz")

    monkeypatch.setitem(sys.modules, "warden.platform.window_mac", types.SimpleNamespace(MacWindows=boom))
    monkeypatch.setattr(window_mod.sys, "platform", "darwin")
    with pytest.raises(OSError, match="pyobjc"):
        window_mod.make_window_backend()


def test_make_window_backend_rejects_an_unsupported_os(monkeypatch):
    import warden.platform.window as window_mod

    monkeypatch.setattr(window_mod.sys, "platform", "freebsd")
    with pytest.raises(OSError, match="doesn't support this OS"):
        window_mod.make_window_backend()


# =================================================================== fake Quartz/AppKit


def _cg_window(number, pid, name="", onscreen=True, layer=0, x=0, y=0, w=800, h=600):
    """One dict shaped like a CGWindowListCopyWindowInfo entry."""
    raw = {
        "kCGWindowNumber": number,
        "kCGWindowOwnerPID": pid,
        "kCGWindowName": name,
        "kCGWindowLayer": layer,
        "kCGWindowBounds": {"X": x, "Y": y, "Width": w, "Height": h},
    }
    if onscreen:
        raw["kCGWindowIsOnscreen"] = True  # Apple's docs: the key is simply absent when it's not
    return raw


class _FakeImage:
    """Stands in for a CGImageRef: just the handful of fields capture.py reads."""

    def __init__(self, width, height, bytes_per_row, pixel_bytes):
        self.width, self.height = width, height
        self.bytes_per_row, self.pixel_bytes = bytes_per_row, pixel_bytes


class FakeQuartz:
    kCGWindowListOptionOnScreenOnly = 1 << 0
    kCGWindowListOptionAll = 0
    kCGWindowListExcludeDesktopElements = 1 << 4
    kCGWindowListOptionIncludingWindow = 1 << 3
    kCGWindowImageBoundsIgnoreFraming = 1 << 0
    kCGWindowImageBestResolution = 1 << 3
    kCGNullWindowID = 0
    CGRectNull = None

    def __init__(self, windows=()):
        self.windows = list(windows)
        self.images: dict[int, _FakeImage] = {}  # window id -> fake image, for capture tests

    def CGWindowListCopyWindowInfo(self, option, _relative_to):
        if option & self.kCGWindowListOptionOnScreenOnly:
            return [w for w in self.windows if w.get("kCGWindowIsOnscreen")]
        return list(self.windows)

    def CGWindowListCreateImage(self, _rect, _option, window_id, _flags):
        return self.images.get(window_id)

    def CGEventCreate(self, _source):
        return object()

    def CGEventGetLocation(self, _event):
        return types.SimpleNamespace(x=12.0, y=34.0)

    # -- CGImage reading (used by vision.capture._cgimage_to_bgr) ------------

    def CGImageGetWidth(self, image):
        return image.width

    def CGImageGetHeight(self, image):
        return image.height

    def CGImageGetBytesPerRow(self, image):
        return image.bytes_per_row

    def CGImageGetDataProvider(self, image):
        return image  # the provider and the image are the same fake object here

    def CGDataProviderCopyData(self, provider):
        return provider.pixel_bytes


class FakeApp:
    def __init__(self, pid):
        self.pid = pid
        self.activated_with = None
        self.terminated = False

    def processIdentifier(self):
        return self.pid

    def activateWithOptions_(self, options):
        self.activated_with = options

    def terminate(self):
        self.terminated = True


def _fake_appkit(apps_by_pid: dict[int, FakeApp], frontmost_pid: int | None):
    class RunningApplication:
        @staticmethod
        def runningApplicationWithProcessIdentifier_(pid):
            return apps_by_pid.get(pid)

    class Workspace:
        @staticmethod
        def sharedWorkspace():
            return Workspace

        @staticmethod
        def frontmostApplication():
            return apps_by_pid.get(frontmost_pid) if frontmost_pid is not None else None

    return types.SimpleNamespace(
        NSRunningApplication=RunningApplication,
        NSWorkspace=Workspace,
        NSApplicationActivateIgnoringOtherApps=2,
    )


class FakeProcess:
    names: dict[int, str] = {}

    def __init__(self, pid):
        self.pid = pid

    def name(self):
        if self.pid not in self.names:
            raise LookupError(self.pid)  # psutil.NoSuchProcess-shaped failure
        return self.names[self.pid]


@pytest.fixture
def mac_windows_factory(monkeypatch):
    """Builds a MacWindows wired to fake Quartz/AppKit + psutil. Returns a
    (backend, quartz) pair so tests can also stuff fake capture images in.
    """
    import warden.platform.window_mac as window_mac_mod

    def build(windows, pid_names: dict[int, str], frontmost_pid: int | None = None):
        quartz = FakeQuartz(windows)
        apps = {pid: FakeApp(pid) for pid in pid_names}
        monkeypatch.setitem(sys.modules, "Quartz", quartz)
        monkeypatch.setitem(sys.modules, "AppKit", _fake_appkit(apps, frontmost_pid))
        monkeypatch.setattr(window_mac_mod.sys, "platform", "darwin")
        monkeypatch.setattr("psutil.Process", FakeProcess)
        FakeProcess.names = pid_names
        backend = window_mac_mod.MacWindows()
        return backend, quartz, apps

    return build


# =================================================================== MacWindows


def test_mac_windows_requires_darwin(monkeypatch):
    import warden.platform.window_mac as window_mac_mod

    monkeypatch.setattr(window_mac_mod.sys, "platform", "linux")
    with pytest.raises(OSError):
        window_mac_mod.MacWindows()


def test_list_windows_maps_bounds_and_process_name(mac_windows_factory):
    windows = [_cg_window(101, pid=500, name="Rivals", x=10, y=20, w=1920, h=1080)]
    backend, _q, _apps = mac_windows_factory(windows, {500: "robloxplayer"})
    found = backend.list_windows()
    assert len(found) == 1
    info = found[0]
    assert info.hwnd == 101 and info.pid == 500
    assert info.process_name == "robloxplayer"
    assert info.client == Rect(10, 20, 1920, 1080)
    assert info.visible is True and info.minimized is False


def test_list_windows_excludes_non_normal_layers(mac_windows_factory):
    windows = [
        _cg_window(1, pid=10, layer=0),    # a normal app window
        _cg_window(2, pid=11, layer=24),   # e.g. the menu bar - must not show up as a "window"
    ]
    backend, _q, _apps = mac_windows_factory(windows, {10: "robloxplayer", 11: "windowserver"})
    hwnds = {w.hwnd for w in backend.list_windows()}
    assert hwnds == {1}


def test_offscreen_window_reported_as_not_visible_and_minimized(mac_windows_factory):
    windows = [_cg_window(5, pid=20, onscreen=False)]
    backend, _q, _apps = mac_windows_factory(windows, {20: "robloxplayer"})
    info = backend.list_windows()[0]
    assert info.visible is False
    assert info.minimized is True


def test_pick_client_works_against_a_mac_window_list(mac_windows_factory):
    from warden.platform.window import pick_client

    windows = [
        _cg_window(1, pid=10, layer=0, w=400, h=300),   # Finder or similar - wrong process
        _cg_window(2, pid=20, layer=0, w=1920, h=1080),  # the real Roblox client
    ]
    backend, _q, _apps = mac_windows_factory(windows, {10: "finder", 20: "robloxplayer"})
    picked = pick_client(backend.list_windows(), client_processes={"robloxplayer"})
    assert picked is not None and picked.hwnd == 2


def test_refresh_finds_an_offscreen_window_too(mac_windows_factory):
    windows = [_cg_window(7, pid=30, onscreen=False)]
    backend, _q, _apps = mac_windows_factory(windows, {30: "robloxplayer"})
    assert backend.refresh(7) is not None
    assert backend.refresh(999) is None


def test_foreground_returns_frontmost_apps_window_id(mac_windows_factory):
    windows = [
        _cg_window(1, pid=10, layer=0),
        _cg_window(2, pid=20, layer=0),
    ]
    backend, _q, _apps = mac_windows_factory(windows, {10: "finder", 20: "robloxplayer"}, frontmost_pid=20)
    assert backend.foreground() == 2


def test_foreground_is_zero_with_no_frontmost_app(mac_windows_factory):
    backend, _q, _apps = mac_windows_factory([_cg_window(1, pid=10)], {10: "x"}, frontmost_pid=None)
    assert backend.foreground() == 0


def test_focus_activates_the_owning_application(mac_windows_factory):
    windows = [_cg_window(9, pid=40, layer=0)]
    backend, _q, apps = mac_windows_factory(windows, {40: "robloxplayer"}, frontmost_pid=40)
    assert backend.focus(9) is True
    assert apps[40].activated_with == 2  # NSApplicationActivateIgnoringOtherApps


def test_focus_returns_false_for_an_unknown_window(mac_windows_factory):
    backend, _q, _apps = mac_windows_factory([], {})
    assert backend.focus(12345) is False


def test_send_close_terminates_the_owning_application(mac_windows_factory):
    windows = [_cg_window(3, pid=50, layer=0)]
    backend, _q, apps = mac_windows_factory(windows, {50: "robloxplayer"})
    backend.send_close(3)
    assert apps[50].terminated is True


def test_send_close_on_an_unknown_window_does_not_raise(mac_windows_factory):
    backend, _q, _apps = mac_windows_factory([], {})
    backend.send_close(404)  # must not raise


def test_cursor_pos_reads_through_cgevent(mac_windows_factory):
    backend, _q, _apps = mac_windows_factory([], {})
    assert backend.cursor_pos() == (12, 34)


# =================================================================== capture: CGImage -> np.ndarray


def _fake_cgimage_quartz(width, height, bytes_per_row, pixel_bytes):
    class Img:
        pass

    image = Img()

    class Quartz:
        @staticmethod
        def CGImageGetWidth(_img):
            return width

        @staticmethod
        def CGImageGetHeight(_img):
            return height

        @staticmethod
        def CGImageGetBytesPerRow(_img):
            return bytes_per_row

        @staticmethod
        def CGImageGetDataProvider(_img):
            return object()

        @staticmethod
        def CGDataProviderCopyData(_provider):
            return pixel_bytes

    return Quartz(), image


def test_cgimage_to_bgr_drops_alpha_and_keeps_bgr_order():
    from warden.vision.capture import _cgimage_to_bgr

    w, h = 2, 1
    # One BGRA pixel each: pure blue, pure red (alpha ignored either way).
    pixels = bytes([255, 0, 0, 255,  0, 0, 255, 255])
    quartz, image = _fake_cgimage_quartz(w, h, bytes_per_row=w * 4, pixel_bytes=pixels)
    frame = _cgimage_to_bgr(quartz, image, want_w=w, want_h=h)
    assert frame.shape == (1, 2, 3)
    assert list(frame[0, 0]) == [255, 0, 0]  # B,G,R
    assert list(frame[0, 1]) == [0, 0, 255]


def test_cgimage_to_bgr_strips_row_padding():
    from warden.vision.capture import _cgimage_to_bgr

    w, h = 1, 2
    row_stride = 16  # wider than the 4 real bytes/row - CoreGraphics often pads rows
    rows = bytearray(row_stride * h)
    rows[0:4] = bytes([10, 20, 30, 255])
    rows[row_stride:row_stride + 4] = bytes([40, 50, 60, 255])
    quartz, image = _fake_cgimage_quartz(w, h, bytes_per_row=row_stride, pixel_bytes=bytes(rows))
    frame = _cgimage_to_bgr(quartz, image, want_w=w, want_h=h)
    assert frame.shape == (2, 1, 3)
    assert list(frame[0, 0]) == [10, 20, 30]
    assert list(frame[1, 0]) == [40, 50, 60]


def test_cgimage_to_bgr_downscales_a_retina_capture():
    from warden.vision.capture import _cgimage_to_bgr

    native_w, native_h = 4, 4  # pretend this is a 2x capture of a 2x2-point window
    pixels = bytes([100, 150, 200, 255] * (native_w * native_h))
    quartz, image = _fake_cgimage_quartz(native_w, native_h, bytes_per_row=native_w * 4, pixel_bytes=pixels)
    frame = _cgimage_to_bgr(quartz, image, want_w=2, want_h=2)
    assert frame.shape == (2, 2, 3)


def test_cgimage_to_bgr_returns_none_for_an_all_black_image():
    from warden.vision.capture import _cgimage_to_bgr

    quartz, image = _fake_cgimage_quartz(1, 1, bytes_per_row=4, pixel_bytes=bytes(4))
    assert _cgimage_to_bgr(quartz, image, want_w=1, want_h=1) is None


def test_window_capturer_uses_quartz_path_on_darwin(monkeypatch):
    from warden.vision.capture import WindowCapturer

    monkeypatch.setattr(sys, "platform", "darwin")
    pixels = bytes([5, 6, 7, 255] * 4)
    quartz = FakeQuartz()
    quartz.images = {77: _FakeImage(2, 2, bytes_per_row=8, pixel_bytes=pixels)}
    monkeypatch.setitem(sys.modules, "Quartz", quartz)

    capturer = WindowCapturer()
    capturer.hwnd = 77
    frame = capturer.grab(Rect(0, 0, 2, 2))
    assert isinstance(frame, np.ndarray) and frame.shape == (2, 2, 3)
    assert capturer.last_method == "window"


def test_window_capturer_falls_back_to_screen_when_quartz_finds_nothing(monkeypatch):
    from warden.vision.capture import MssCapturer, WindowCapturer

    monkeypatch.setattr(sys, "platform", "darwin")
    quartz = FakeQuartz([])  # CGWindowListCreateImage will return None for any id
    monkeypatch.setitem(sys.modules, "Quartz", quartz)

    calls = []

    class FallbackCapturer:
        def grab(self, rect):
            calls.append(rect)
            return np.zeros((rect.height, rect.width, 3), dtype=np.uint8)

    capturer = WindowCapturer(fallback=FallbackCapturer())
    capturer.hwnd = 1
    frame = capturer.grab(Rect(0, 0, 10, 10))
    assert calls == [Rect(0, 0, 10, 10)]
    assert capturer.last_method == "screen"
    assert frame.shape == (10, 10, 3)


# =================================================================== power.SleepGuard (caffeinate)


class FakePopen:
    instances: list["FakePopen"] = []

    def __init__(self, args, **kw):
        self.args = args
        self.terminated = False
        self._poll = None
        FakePopen.instances.append(self)

    def poll(self):
        return self._poll

    def terminate(self):
        self.terminated = True
        self._poll = 0


@pytest.fixture(autouse=True)
def _reset_fake_popen():
    FakePopen.instances.clear()
    yield
    FakePopen.instances.clear()


def test_sleep_guard_acquire_runs_caffeinate_with_display_flag(monkeypatch):
    import warden.platform.power as power_mod

    monkeypatch.setattr(power_mod.sys, "platform", "darwin")
    monkeypatch.setattr(power_mod.subprocess, "Popen", FakePopen)
    guard = power_mod.SleepGuard(keep_display_on=True)
    assert guard.acquire() is True
    assert FakePopen.instances[-1].args == ["caffeinate", "-i", "-d"]


def test_sleep_guard_acquire_without_display_flag(monkeypatch):
    import warden.platform.power as power_mod

    monkeypatch.setattr(power_mod.sys, "platform", "darwin")
    monkeypatch.setattr(power_mod.subprocess, "Popen", FakePopen)
    guard = power_mod.SleepGuard(keep_display_on=False)
    guard.acquire()
    assert FakePopen.instances[-1].args == ["caffeinate", "-i"]


def test_sleep_guard_release_terminates_caffeinate(monkeypatch):
    import warden.platform.power as power_mod

    monkeypatch.setattr(power_mod.sys, "platform", "darwin")
    monkeypatch.setattr(power_mod.subprocess, "Popen", FakePopen)
    guard = power_mod.SleepGuard()
    guard.acquire()
    proc = FakePopen.instances[-1]
    guard.release()
    assert proc.terminated is True
    assert guard.active is False


def test_sleep_guard_acquire_twice_reuses_the_same_process(monkeypatch):
    import warden.platform.power as power_mod

    monkeypatch.setattr(power_mod.sys, "platform", "darwin")
    monkeypatch.setattr(power_mod.subprocess, "Popen", FakePopen)
    guard = power_mod.SleepGuard()
    guard.acquire()
    guard.acquire()
    assert len(FakePopen.instances) == 1


def test_sleep_guard_missing_caffeinate_degrades_gracefully(monkeypatch):
    import warden.platform.power as power_mod

    def boom(*a, **kw):
        raise FileNotFoundError("no caffeinate")

    monkeypatch.setattr(power_mod.sys, "platform", "darwin")
    monkeypatch.setattr(power_mod.subprocess, "Popen", boom)
    guard = power_mod.SleepGuard()
    assert guard.acquire() is False
    guard.release()  # must not raise


# =================================================================== scheduler.power_action (macOS)


def test_power_action_sleep_uses_pmset(monkeypatch):
    import warden.core.scheduler as scheduler_mod

    calls = []
    monkeypatch.setattr(scheduler_mod.sys, "platform", "darwin")
    monkeypatch.setattr(scheduler_mod.subprocess, "run", lambda args, **kw: calls.append(args))
    scheduler_mod.power_action("sleep")
    assert calls == [["pmset", "sleepnow"]]


def test_power_action_shutdown_uses_osascript(monkeypatch):
    import warden.core.scheduler as scheduler_mod

    calls = []
    monkeypatch.setattr(scheduler_mod.sys, "platform", "darwin")
    monkeypatch.setattr(scheduler_mod.subprocess, "run", lambda args, **kw: calls.append(args))
    scheduler_mod.power_action("shutdown")
    assert calls and calls[0][0] == "osascript"


# =================================================================== process.py (macOS)


def test_startfile_uses_open_on_macos(monkeypatch):
    import warden.platform.process as process_mod

    calls = []
    monkeypatch.setattr(process_mod.sys, "platform", "darwin")
    monkeypatch.setattr(process_mod.subprocess, "run", lambda args, **kw: calls.append(args))
    process_mod._startfile("roblox://experiences/start?placeId=1")
    assert calls == [["open", "roblox://experiences/start?placeId=1"]]


def test_roblox_process_pids_matches_mac_process_name(monkeypatch):
    import warden.platform.window as window_mod
    from warden.platform.process import RobloxProcess

    class Proc:
        def __init__(self, pid, name):
            self.pid = pid
            self.info = {"name": name}

    monkeypatch.setattr(window_mod.sys, "platform", "darwin")  # client_process_names() reads this
    monkeypatch.setattr(
        "psutil.process_iter",
        lambda attrs: [Proc(1, "RobloxPlayer"), Proc(2, "Safari"), Proc(3, "Finder")],
    )
    assert RobloxProcess.pids() == [1]


# =================================================================== toast.py (macOS)


def test_default_backend_is_mac_notification_on_darwin(monkeypatch):
    import warden.integrations.toast as toast_mod

    monkeypatch.setattr(toast_mod.sys, "platform", "darwin")
    assert toast_mod._default_backend() is toast_mod._MacNotification


def test_mac_notification_show_calls_osascript_with_quoted_strings(monkeypatch):
    import warden.integrations.toast as toast_mod

    calls = []
    monkeypatch.setattr(toast_mod.subprocess, "run", lambda args, **kw: calls.append((args, kw)))
    toast_mod._MacNotification(app_id="Warden", title='Say "hi"', msg="4h reached").show()
    (args, kw), = calls
    assert args[0] == "osascript"
    script = args[2]
    assert 'display notification "4h reached" with title "Say \\"hi\\""' == script
    assert kw.get("check") is True


def test_toast_notifier_end_to_end_on_mac(monkeypatch):
    from warden.integrations.toast import ToastNotifier

    calls = []
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(subprocess, "run", lambda args, **kw: calls.append(args))
    notifier = ToastNotifier()
    assert notifier.available() is True
    assert notifier.notify("Milestone", "4h reached") is True
    assert calls and calls[0][0] == "osascript"
