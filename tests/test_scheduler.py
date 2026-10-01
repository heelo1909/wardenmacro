import time

from warden.config.schema import Scheduler as SchedulerConfig
from warden.config.schema import TimeWindow
from warden.core.scheduler import Scheduler, ShutdownCountdown, in_any_window, seconds_until_clock_time


def _struct(h, m, s=0):
    return time.struct_time((2026, 1, 1, h, m, s, 3, 1, -1))


def test_seconds_until_clock_time_same_day():
    assert seconds_until_clock_time(_struct(10, 0), (12, 0)) == 7200


def test_seconds_until_clock_time_wraps_to_tomorrow():
    assert seconds_until_clock_time(_struct(23, 0), (1, 0)) == 2 * 3600


def test_in_any_window_empty_means_always_allowed():
    assert in_any_window(_struct(3, 0), []) is True


def test_in_any_window_normal_window():
    windows = [TimeWindow(start="09:00", end="17:00")]
    assert in_any_window(_struct(12, 0), windows) is True
    assert in_any_window(_struct(20, 0), windows) is False


def test_in_any_window_wraps_past_midnight():
    windows = [TimeWindow(start="22:00", end="08:00")]
    assert in_any_window(_struct(23, 30), windows) is True
    assert in_any_window(_struct(2, 0), windows) is True
    assert in_any_window(_struct(12, 0), windows) is False


def test_check_stops_when_target_reached():
    sched = Scheduler(SchedulerConfig())
    decision = sched.check(in_match_hours=24.5, target_hours=24.0, auto_stop_at_target=True)
    assert decision and "target reached" in decision.reason


def test_check_does_not_stop_when_auto_stop_disabled():
    sched = Scheduler(SchedulerConfig())
    decision = sched.check(in_match_hours=30.0, target_hours=24.0, auto_stop_at_target=False)
    assert not decision


def test_check_stops_at_scheduled_clock_time():
    cfg = SchedulerConfig(stop_at_time="14:30")
    sched = Scheduler(cfg, clock=lambda: _struct(14, 30, 0))
    decision = sched.check(in_match_hours=1.0, target_hours=24.0, auto_stop_at_target=False)
    assert decision and "scheduled stop" in decision.reason


def test_check_stops_outside_configured_window():
    cfg = SchedulerConfig(windows=[TimeWindow(start="09:00", end="17:00")])
    sched = Scheduler(cfg, clock=lambda: _struct(20, 0))
    decision = sched.check(in_match_hours=1.0, target_hours=24.0, auto_stop_at_target=False)
    assert decision and "outside configured run window" in decision.reason


def test_check_no_stop_when_nothing_triggers():
    sched = Scheduler(SchedulerConfig(), clock=lambda: _struct(12, 0))
    decision = sched.check(in_match_hours=1.0, target_hours=24.0, auto_stop_at_target=True)
    assert not decision


def test_shutdown_countdown_fires_after_elapsed():
    t = [0.0]
    fired = []
    cd = ShutdownCountdown(seconds=0.3, action=lambda: fired.append(True),
                           clock=lambda: t[0], sleep=lambda s: t.__setitem__(0, t[0] + s))
    cd.start()
    cd.wait(timeout=2.0)
    assert fired == [True]
    assert cd.fired is True


def test_shutdown_countdown_cancel_prevents_action():
    fired = []
    cd = ShutdownCountdown(seconds=60.0, action=lambda: fired.append(True))
    cd.start()
    cd.cancel()
    assert fired == []
    assert cd.fired is False


def test_shutdown_countdown_reports_remaining_time():
    t = [0.0]
    remaining_values = []
    cd = ShutdownCountdown(seconds=1.0, action=lambda: None, on_tick=remaining_values.append,
                           clock=lambda: t[0], sleep=lambda s: t.__setitem__(0, t[0] + s))
    cd.start()
    cd.wait(timeout=2.0)
    assert remaining_values and remaining_values[0] <= 1.0


def test_power_action_noop_on_non_windows(monkeypatch, caplog):
    import logging

    import warden.core.scheduler as scheduler_mod

    monkeypatch.setattr(scheduler_mod.sys, "platform", "linux")
    with caplog.at_level(logging.WARNING):
        scheduler_mod.power_action("sleep")
    assert "ignoring" in caplog.text
