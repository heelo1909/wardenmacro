"""Phase 6 integration: TickLoop's own bookkeeping, wired to a real
PersistenceManager/Scheduler (not re-testing their internals - see
tests/test_persistence.py and tests/test_scheduler.py for that).

Uses ``_bookkeep()`` directly (see its docstring) so these drive the exact
production code path without needing a real Roblox window - observe_only is
still forced per warden-testing-safety for anything that constructs a real
TickLoop.
"""

from warden.config import load_all
from warden.core.events import EventBus
from warden.core.persistence import load_state
from warden.core.state_machine import State
from warden.core.tick import TickLoop


def make_loop(bundled_config, tmp_path, monkeypatch, **app_overrides):
    import shutil

    work = tmp_path / "config"
    shutil.copytree(bundled_config, work)
    monkeypatch.setenv("WARDEN_HOME", str(tmp_path / "home"))
    loaded = load_all(work / "default.yaml")
    loaded.app.observe_only = True
    for k, v in app_overrides.items():
        setattr(loaded.app, k, v)
    return TickLoop(loaded.app, loaded.preset, EventBus())


def begin_session(loop: TickLoop) -> None:
    """Everything start() does except spawning the real background thread -
    these tests drive _bookkeep() by hand and must never race a second,
    real thread also polling the (possibly tiny) target_hours concurrently.
    """
    loop._in_match_seconds = 0.0
    loop._last_tick_monotonic = 0.0
    loop._incidents = []
    loop._session_active = True
    loop.persistence.start_session(loop.app.active_preset, loop.preset.contract.label,
                                    loop.preset.contract.target_hours)
    loop.sm.start()


def test_credited_time_accumulates_only_in_match_by_default(bundled_config, tmp_path, monkeypatch):
    loop = make_loop(bundled_config, tmp_path, monkeypatch)
    begin_session(loop)
    loop._last_tick_monotonic = 0.0
    loop.sm.state = State.LOBBY
    loop._bookkeep(State.LOBBY, now=1.0)
    assert loop._in_match_seconds == 0.0  # LOBBY doesn't count by default
    loop._bookkeep(State.IN_MATCH, now=2.0)
    assert loop._in_match_seconds == 1.0
    loop.stop()


def test_count_lobby_time_credits_any_active_state(bundled_config, tmp_path, monkeypatch):
    loop = make_loop(bundled_config, tmp_path, monkeypatch)
    loop.app.estimate.count_lobby_time = True
    begin_session(loop)
    loop._last_tick_monotonic = 0.0
    loop._bookkeep(State.LOBBY, now=5.0)
    assert loop._in_match_seconds == 5.0
    loop._bookkeep(State.LAUNCHING, now=10.0)  # LAUNCHING never counts, even with the toggle on
    assert loop._in_match_seconds == 5.0
    loop.stop()


def test_stop_at_small_target_hours_triggers_scheduled_stop(bundled_config, tmp_path, monkeypatch):
    loop = make_loop(bundled_config, tmp_path, monkeypatch)
    loop.preset.contract.target_hours = 0.01  # 36 seconds
    loop.preset.contract.auto_stop_at_target = True
    begin_session(loop)
    loop._last_tick_monotonic = 0.0
    loop._bookkeep(State.IN_MATCH, now=40.0)  # 40s > 36s target
    assert loop.sm.state is State.STOPPED
    assert loop._session_active is False  # finalized


def test_scheduled_stop_does_not_deadlock_without_a_running_thread(bundled_config, tmp_path, monkeypatch):
    # _scheduled_stop must never try to join self._thread (it would be the
    # thread joining itself when called from inside the tick loop); calling
    # it with no thread running at all is the simplest proof it never tries.
    loop = make_loop(bundled_config, tmp_path, monkeypatch)
    loop.preset.contract.target_hours = 0.001
    begin_session(loop)
    assert loop._thread is None  # tick_once()/bookkeep driven manually in this test, not start()'s loop
    loop._bookkeep(State.IN_MATCH, now=100.0)
    assert loop.sm.state is State.STOPPED


def test_persisted_state_survives_a_simulated_crash(bundled_config, tmp_path, monkeypatch):
    loop = make_loop(bundled_config, tmp_path, monkeypatch)
    begin_session(loop)
    loop._last_tick_monotonic = 0.0
    loop._bookkeep(State.IN_MATCH, now=500.0)
    loop.persistence.maybe_flush(loop._in_match_seconds, loop.sm.counters, force=True)
    # "crash": no stop()/_finalize_session() ever called.
    reloaded = load_state(loop.persistence.state_path)
    assert reloaded.last_session_incomplete is True
    assert reloaded.contracts["glass_wrap"].cumulative_seconds == 500.0


def test_clean_stop_clears_incomplete_flag_and_writes_session_summary(bundled_config, tmp_path, monkeypatch):
    loop = make_loop(bundled_config, tmp_path, monkeypatch)
    begin_session(loop)
    loop._last_tick_monotonic = 0.0
    loop._bookkeep(State.IN_MATCH, now=120.0)
    loop.sm.counters.respawns = 2
    loop.stop()
    reloaded = load_state(loop.persistence.state_path)
    assert reloaded.last_session_incomplete is False
    from warden.core.persistence import load_session_summaries

    summaries = load_session_summaries(loop.persistence.sessions_dir)
    assert len(summaries) == 1
    assert summaries[0]["counters"]["respawns"] == 2


def test_incidents_are_collected_from_the_bus_and_saved_on_stop(bundled_config, tmp_path, monkeypatch):
    loop = make_loop(bundled_config, tmp_path, monkeypatch)
    begin_session(loop)
    loop.bus.emit("incident", "disconnect detected", level="warn")
    loop.stop()
    from warden.core.persistence import load_session_summaries

    summaries = load_session_summaries(loop.persistence.sessions_dir)
    assert any("disconnect detected" in i for i in summaries[0]["incidents"])


def test_shutdown_countdown_is_cancelable_after_scheduled_stop(bundled_config, tmp_path, monkeypatch):
    loop = make_loop(bundled_config, tmp_path, monkeypatch)
    loop.app.scheduler.after_stop = "sleep"
    loop.app.scheduler.countdown_s = 60
    loop.preset.contract.target_hours = 0.001
    begin_session(loop)
    loop._bookkeep(State.IN_MATCH, now=100.0)
    assert loop._countdown is not None
    assert loop.cancel_shutdown_countdown() is True
    assert loop._countdown.fired is False
