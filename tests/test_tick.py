import numpy as np

from warden.config import load_all
from warden.core.events import EventBus
from warden.core.state_machine import State
from warden.core.tick import TickLoop


def test_tick_loop_constructs_and_ticks_without_roblox_running(bundled_config):
    loaded = load_all(bundled_config / "default.yaml")
    loaded.app.observe_only = True  # never send real input during tests, regardless of what's running on the host
    loop = TickLoop(loaded.app, loaded.preset, EventBus())
    state = loop.tick_once()
    assert state is State.IDLE  # nothing started yet, and that must not crash


def test_tick_once_is_safe_to_call_repeatedly(bundled_config):
    loaded = load_all(bundled_config / "default.yaml")
    loaded.app.observe_only = True  # never send real input during tests, regardless of what's running on the host
    loop = TickLoop(loaded.app, loaded.preset, EventBus())
    for _ in range(3):
        loop.tick_once()  # no exception with no client window present


def test_live_actions_click_falls_back_to_default_position(bundled_config):
    # observe_only stays False here on purpose, to exercise the "blocked, not
    # observed" path - safe because FocusGate.set_target() is never called in
    # this test (we never run tick_once()), so gate.hwnd stays 0 and
    # is_focused() is unconditionally False regardless of what's running on
    # the host: no real input can be sent no matter what.
    loaded = load_all(bundled_config / "default.yaml")
    bus = EventBus()
    events = []
    bus.subscribe(events.append)
    loop = TickLoop(loaded.app, loaded.preset, bus)
    assert loop.focus_gate.hwnd == 0
    loop.actions.update_detections({})  # nothing detected -> fallback position
    loop.actions.click_play()  # focus gate blocks (hwnd never set -> never "focused")
    assert any(e.topic == "input.blocked" for e in events)


def test_live_actions_run_loadout_without_captured_templates_fails_safely(bundled_config):
    # No weapon templates exist yet (Calibration is Phase 8) - it must never
    # guess a click, just report the slots it couldn't verify.
    loaded = load_all(bundled_config / "default.yaml")
    loaded.app.observe_only = True  # never send real input during tests, regardless of what's running on the host
    loop = TickLoop(loaded.app, loaded.preset, EventBus())
    assert loop.actions.run_loadout() is False
    assert loop.actions.reapply_loadout_if_due() is False


def test_start_stop_background_loop(bundled_config):
    import time

    loaded = load_all(bundled_config / "default.yaml")
    loaded.app.observe_only = True  # never send real input during tests, regardless of what's running on the host
    loop = TickLoop(loaded.app, loaded.preset, EventBus())
    loop.start()
    time.sleep(0.6)
    loop.stop()
    assert loop.sm.state is State.STOPPED
