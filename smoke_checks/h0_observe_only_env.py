"""H0 safety net: WARDEN_FORCE_OBSERVE_ONLY=1 makes TickLoop observe-only even if config says otherwise."""

import os

from _util import ROOT, check, run


class _FakeBackend:
    def list_windows(self): return []
    def foreground(self): return 0
    def focus(self, hwnd, timeout=0.6): return False
    def refresh(self, hwnd): return None
    def send_close(self, hwnd): pass
    def cursor_pos(self): return (0, 0)


class _FakeMethod:
    name = "fake"
    def move_abs(self, x, y): raise AssertionError("real input attempted")
    move_rel = button = key = wheel = move_abs


def main():
    from warden.config.loader import load_preset
    from warden.config.schema import AppConfig
    from warden.core import tick
    from warden.core.events import EventBus
    from warden.platform.input import forced_observe_only

    check("smoke sets the env var", os.environ.get("WARDEN_FORCE_OBSERVE_ONLY") == "1")
    check("forced_observe_only() reads it", forced_observe_only())
    tick.make_window_backend = lambda: _FakeBackend()
    tick.build_methods = lambda order: [_FakeMethod()]
    app = AppConfig()
    app.observe_only = False
    preset = load_preset(ROOT / "config" / "presets" / "glass_wrap.yaml")
    loop = tick.TickLoop(app, preset, EventBus())
    check("TickLoop input is observe-only", loop.input.observe_only is True)
    loop.input.gate.is_focused = lambda: True
    check("a click is swallowed, not sent", loop.input.key_tap("ESCAPE") is True)


run(main)
