"""Contract queue (HANDOFF §8.11): TickLoop emits schedule.target_reached
when a target is hit; AppContext owns advancing through the queue.
"""

import shutil

import pytest

from warden.config import load_all
from warden.core.events import EventBus
from warden.core.state_machine import State
from warden.core.tick import TickLoop
from warden.gui.context import AppContext


def make_ctx(bundled_config, tmp_path, monkeypatch):
    work = tmp_path / "config"
    shutil.copytree(bundled_config, work)
    monkeypatch.setenv("WARDEN_HOME", str(tmp_path / "home"))
    loaded = load_all(work / "default.yaml")
    loaded.app.observe_only = True
    return AppContext(loaded, EventBus())


def test_next_in_queue_returns_none_when_preset_not_in_queue(bundled_config, tmp_path, monkeypatch):
    ctx = make_ctx(bundled_config, tmp_path, monkeypatch)
    ctx.app.contract_queue = ["random"]  # active preset ("glass_wrap") isn't in it
    assert ctx.next_in_contract_queue() is None
    assert ctx.advance_contract_queue() is False


def test_next_in_queue_returns_none_when_last_in_queue(bundled_config, tmp_path, monkeypatch):
    ctx = make_ctx(bundled_config, tmp_path, monkeypatch)
    ctx.app.contract_queue = ["glass_wrap"]
    assert ctx.next_in_contract_queue() is None


def test_advance_contract_queue_switches_to_the_next_preset(bundled_config, tmp_path, monkeypatch):
    ctx = make_ctx(bundled_config, tmp_path, monkeypatch)
    ctx.app.contract_queue = ["glass_wrap", "random", "default"]
    assert ctx.next_in_contract_queue() == "random"
    assert ctx.advance_contract_queue() is True
    assert ctx.preset_id == "random"
    assert ctx.next_in_contract_queue() == "default"


def test_tick_loop_emits_target_reached_with_preset_id(bundled_config, tmp_path, monkeypatch):
    work = tmp_path / "config"
    shutil.copytree(bundled_config, work)
    monkeypatch.setenv("WARDEN_HOME", str(tmp_path / "home"))
    loaded = load_all(work / "default.yaml")
    loaded.app.observe_only = True
    bus = EventBus()
    events = []
    bus.subscribe(events.append, topics=["schedule.target_reached"])
    loop = TickLoop(loaded.app, loaded.preset, bus)
    loop.preset.contract.target_hours = 0.001
    loop.preset.contract.auto_stop_at_target = True

    loop._in_match_seconds = 0.0
    loop._last_tick_monotonic = 0.0
    loop._session_active = True
    loop.persistence.start_session(loop.app.active_preset, loop.preset.contract.label, 0.001)

    loop._bookkeep(State.IN_MATCH, now=10.0)
    assert len(events) == 1
    assert events[0].data["preset_id"] == loop.app.active_preset


def test_no_target_reached_event_for_clock_time_stop(bundled_config, tmp_path, monkeypatch):
    work = tmp_path / "config"
    shutil.copytree(bundled_config, work)
    monkeypatch.setenv("WARDEN_HOME", str(tmp_path / "home"))
    loaded = load_all(work / "default.yaml")
    loaded.app.observe_only = True
    from warden.config.schema import TimeWindow

    # A run window that (deterministically, regardless of wall-clock time)
    # excludes "now" - simpler than stop_at_time, which is HH:MM granularity
    # and so almost never within the scheduler's 1-second tolerance of "now".
    loaded.app.scheduler.windows = [TimeWindow(start="00:00", end="00:01")]
    bus = EventBus()
    events = []
    bus.subscribe(events.append, topics=["schedule.target_reached"])
    loop = TickLoop(loaded.app, loaded.preset, bus)
    import time

    loop.scheduler.clock = lambda: time.struct_time((2026, 1, 1, 12, 0, 0, 3, 1, -1))  # noon - never in the window

    loop._in_match_seconds = 0.0
    loop._last_tick_monotonic = 0.0
    loop._session_active = True
    loop.persistence.start_session(loop.app.active_preset, loop.preset.contract.label, 24.0)

    loop._bookkeep(State.IN_MATCH, now=0.25)
    assert events == []
    assert loop.sm.state is State.STOPPED  # it did stop - just not via the target-reached path
