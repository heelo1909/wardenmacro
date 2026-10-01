import numpy as np

from warden.config import load_all
from warden.core.events import EventBus
from warden.core.state_machine import State
from warden.core.tick import TickLoop


def test_tick_loop_constructs_and_ticks_without_roblox_running(bundled_config):
    loaded = load_all(bundled_config / "default.yaml")
    loop = TickLoop(loaded.app, loaded.preset, EventBus())
    state = loop.tick_once()
    assert state is State.IDLE  # nothing started yet, and that must not crash


def test_tick_once_is_safe_to_call_repeatedly(bundled_config):
    loaded = load_all(bundled_config / "default.yaml")
    loop = TickLoop(loaded.app, loaded.preset, EventBus())
    for _ in range(3):
        loop.tick_once()  # no exception with no client window present


def test_live_actions_click_falls_back_to_default_position(bundled_config):
    loaded = load_all(bundled_config / "default.yaml")
    bus = EventBus()
    events = []
    bus.subscribe(events.append)
    loop = TickLoop(loaded.app, loaded.preset, bus)
    loop.actions.update_detections({})  # nothing detected -> fallback position
    loop.actions.click_play()  # observe_only is False by default but no client -> focus gate blocks
    assert any(e.topic == "input.blocked" for e in events)


def test_live_actions_run_loadout_stub_accepts_current_equipment(bundled_config):
    loaded = load_all(bundled_config / "default.yaml")
    loop = TickLoop(loaded.app, loaded.preset, EventBus())
    assert loop.actions.run_loadout() is True
    assert loop.actions.reapply_loadout_if_due() is False


def test_start_stop_background_loop(bundled_config):
    import time

    loaded = load_all(bundled_config / "default.yaml")
    loop = TickLoop(loaded.app, loaded.preset, EventBus())
    loop.start()
    time.sleep(0.6)
    loop.stop()
    assert loop.sm.state is State.STOPPED
