"""Stop-at-target, stop-at-clock-time, time windows, and the post-stop
sleep/shutdown countdown (HANDOFF section 8.9).

Pure logic, no OS calls except the actual sleep/shutdown commands (and even
those go through an injectable callable so tests never really touch the
machine's power state).
"""

from __future__ import annotations

import logging
import subprocess
import sys
import threading
import time
from collections.abc import Callable

from warden.config.schema import Scheduler as SchedulerConfig

log = logging.getLogger(__name__)


def parse_hhmm(value: str) -> tuple[int, int]:
    h, m = value.split(":")
    return int(h), int(m)


def seconds_until_clock_time(now: time.struct_time, target: tuple[int, int]) -> float:
    """Seconds from ``now`` until the next occurrence of ``target`` (today or tomorrow)."""
    target_today = now.tm_hour * 3600 + now.tm_min * 60 + now.tm_sec
    target_secs = target[0] * 3600 + target[1] * 60
    delta = target_secs - target_today
    if delta < 0:
        delta += 24 * 3600
    return float(delta)


def in_any_window(now: time.struct_time, windows: list) -> bool:
    """True if ``now`` falls inside any configured [start, end) window (end may wrap past midnight)."""
    if not windows:
        return True  # no windows configured = always allowed to run
    now_m = now.tm_hour * 60 + now.tm_min
    for w in windows:
        sh, sm = parse_hhmm(w.start)
        eh, em = parse_hhmm(w.end)
        start_m, end_m = sh * 60 + sm, eh * 60 + em
        if start_m <= end_m:
            if start_m <= now_m < end_m:
                return True
        else:  # wraps past midnight, e.g. 22:00 - 08:00
            if now_m >= start_m or now_m < end_m:
                return True
    return False


class StopDecision:
    def __init__(self, should_stop: bool, reason: str = ""):
        self.should_stop = should_stop
        self.reason = reason

    def __bool__(self) -> bool:
        return self.should_stop


class Scheduler:
    def __init__(self, config: SchedulerConfig, clock: Callable[[], time.struct_time] = time.localtime):
        self.config = config
        self.clock = clock

    def check(self, in_match_hours: float, target_hours: float, auto_stop_at_target: bool) -> StopDecision:
        now = self.clock()
        if auto_stop_at_target and in_match_hours >= target_hours:
            return StopDecision(True, f"target reached ({in_match_hours:.2f}h >= {target_hours:.2f}h)")
        if self.config.stop_at_time:
            target = parse_hhmm(self.config.stop_at_time)
            if seconds_until_clock_time(now, target) < 1.0:  # tick granularity tolerance
                return StopDecision(True, f"scheduled stop time {self.config.stop_at_time} reached")
        if not in_any_window(now, self.config.windows):
            return StopDecision(True, "outside configured run window")
        return StopDecision(False)


class ShutdownCountdown:
    """A cancelable countdown that runs ``action`` (sleep/shutdown) unless cancelled first."""

    def __init__(self, seconds: float, action: Callable[[], None], on_tick: Callable[[float], None] | None = None,
                 clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep):
        self.seconds = seconds
        self.action = action
        self.on_tick = on_tick
        self.clock = clock
        self.sleep = sleep
        self._cancelled = threading.Event()
        self._thread: threading.Thread | None = None
        self.fired = False

    def start(self) -> None:
        def loop():
            start = self.clock()
            while not self._cancelled.is_set():
                remaining = self.seconds - (self.clock() - start)
                if remaining <= 0:
                    self.fired = True
                    self.action()
                    return
                if self.on_tick:
                    self.on_tick(remaining)
                self.sleep(min(0.2, remaining))

        self._thread = threading.Thread(target=loop, name="warden-shutdown-countdown", daemon=True)
        self._thread.start()

    def cancel(self) -> None:
        self._cancelled.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)

    def wait(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout=timeout)


def power_action(kind: str) -> None:
    """Real sleep/shutdown. Never called by tests - they pass their own ``action``."""
    if sys.platform != "win32":
        log.warning("power action '%s' requested on non-Windows platform; ignoring", kind)
        return
    if kind == "sleep":
        import ctypes

        ctypes.windll.powrprof.SetSuspendState(False, True, False)
    elif kind == "shutdown":
        subprocess.run(["shutdown", "/s", "/t", "0"], check=False)
