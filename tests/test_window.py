from warden.geometry import Rect
from warden.platform.window import (
    FocusGate,
    WindowInfo,
    is_browser,
    pick_browser_with_title,
    pick_client,
    pick_updater,
)


def win(**kw):
    base = dict(hwnd=1, title="", class_name="", process_name="", pid=1, visible=True,
                minimized=False, client=Rect(0, 0, 800, 600))
    base.update(kw)
    return WindowInfo(**base)


def test_ignores_browser_tab_titled_roblox():
    windows = [
        win(hwnd=1, title="Roblox", process_name="chrome.exe", class_name="Chrome_WidgetWin_1"),
        win(hwnd=2, title="Roblox", process_name="robloxplayerbeta.exe", client=Rect(0, 0, 1920, 1080)),
    ]
    picked = pick_client(windows)
    assert picked is not None and picked.hwnd == 2


def test_picks_largest_restored_client_among_candidates():
    windows = [
        win(hwnd=1, process_name="robloxplayerbeta.exe", client=Rect(0, 0, 400, 300)),
        win(hwnd=2, process_name="robloxplayerbeta.exe", minimized=True, client=Rect(0, 0, 1920, 1080)),
        win(hwnd=3, process_name="robloxplayerbeta.exe", client=Rect(0, 0, 1280, 720)),
    ]
    picked = pick_client(windows)
    assert picked.hwnd == 3  # restored beats minimized even though smaller


def test_invisible_window_not_picked():
    windows = [win(hwnd=1, process_name="robloxplayerbeta.exe", visible=False)]
    assert pick_client(windows) is None


def test_no_client_returns_none():
    assert pick_client([win(hwnd=1, process_name="explorer.exe")]) is None


def test_is_browser_by_class_or_process():
    assert is_browser(win(class_name="MozillaWindowClass"))
    assert is_browser(win(process_name="msedge.exe"))
    assert not is_browser(win(process_name="robloxplayerbeta.exe", class_name="WINDOWSCLIENT"))


def test_pick_updater_ignores_browsers_and_client():
    windows = [
        win(hwnd=1, process_name="robloxplayerbeta.exe"),
        win(hwnd=2, process_name="robloxplayerlauncher.exe", title="Roblox Bootstrapper"),
    ]
    updater = pick_updater(windows)
    assert updater is not None and updater.hwnd == 2


def test_pick_browser_with_title_for_fallback():
    windows = [
        win(hwnd=1, process_name="chrome.exe", class_name="Chrome_WidgetWin_1", title="New Tab"),
        win(hwnd=2, process_name="chrome.exe", class_name="Chrome_WidgetWin_1", title="Rivals - Roblox"),
    ]
    found = pick_browser_with_title(windows, "roblox")
    assert found.hwnd == 2


class FakeBackend:
    def __init__(self, fg=0):
        self.fg = fg
        self.focus_calls = []

    def foreground(self):
        return self.fg

    def focus(self, hwnd):
        self.focus_calls.append(hwnd)
        self.fg = hwnd
        return True

    def list_windows(self):
        return []

    def refresh(self, hwnd):
        return None


def test_focus_gate_blocks_when_not_foreground():
    backend = FakeBackend(fg=99)
    gate = FocusGate(backend)
    gate.set_target(42)
    assert not gate.is_focused()
    assert gate.refocus()
    assert gate.is_focused()
    assert backend.focus_calls == [42]


def test_focus_gate_with_no_target():
    gate = FocusGate(FakeBackend())
    assert not gate.is_focused()
    assert not gate.refocus()
