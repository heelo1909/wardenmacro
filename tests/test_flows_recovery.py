from warden.config.schema import RecoveryConfig
from warden.core.state_machine import State
from warden.flows.recovery import RecoverySequence


class FakeActions:
    def __init__(self, running_after_close: bool = False):
        self.calls: list[str] = []
        self._running = True
        self._running_after_close = running_after_close

    def click_leave_or_reconnect(self, prefer):
        self.calls.append(f"click:{prefer}")

    def process_is_running(self):
        return self._running

    def process_close(self, grace_s):
        self.calls.append(f"close:{grace_s}")
        self._running = self._running_after_close

    def open_client(self):
        self.calls.append("open_client")

    def open_browser_and_play(self):
        self.calls.append("open_browser")

    def on_incident(self, cause):
        self.calls.append(f"incident:{cause}")


def cfg(**kw):
    base = dict(leave_wait_s=10, close_grace_s=10, max_attempts=3, backoff_initial_s=30,
                backoff_cap_s=600, alert_after_cycles=3, browser_fallback=True, prefer_button="leave")
    base.update(kw)
    return RecoveryConfig(**base)


def run_full_cycle(seq: RecoverySequence, t: list[float], cause: str = "disconnect") -> State:
    """Drives click_leave -> wait_leave -> close_process -> relaunch to completion.

    Each stage transition is its own tick (same "transition now, act on the
    next call" discipline as the main state machine), so a full cycle is
    four calls: idle+click, wait-elapsed, close, relaunch.
    """
    seq.tick(cause, now=t[0])           # idle -> click_leave (clicks immediately)
    t[0] += 11
    seq.tick(cause, now=t[0])           # wait_leave elapsed -> stage = close_process
    seq.tick(cause, now=t[0])           # close_process executes -> stage = relaunch
    return seq.tick(cause, now=t[0])    # relaunch executes -> LAUNCHING (or RECOVERING if backing off)


def test_full_sequence_clicks_leave_waits_closes_and_relaunches():
    actions = FakeActions()
    t = [0.0]
    seq = RecoverySequence(actions, cfg(), clock=lambda: t[0])
    result = run_full_cycle(seq, t)
    assert result is State.LAUNCHING
    assert actions.calls == ["incident:recovery_start:disconnect", "click:leave", "close:10.0", "open_client"]
    assert seq.stats.attempts == 1


def test_leave_wait_is_honored_before_closing():
    actions = FakeActions()
    t = [0.0]
    seq = RecoverySequence(actions, cfg(), clock=lambda: t[0])
    seq.tick("disconnect", now=0.0)  # click
    t[0] = 5.0
    seq.tick("disconnect", now=t[0])  # still waiting (< 10s)
    assert "close:10.0" not in actions.calls
    assert seq.stage == "wait_leave"
    t[0] = 11.0
    seq.tick("disconnect", now=t[0])  # elapsed -> stage advances...
    assert "close:10.0" not in actions.calls  # ...but the close itself is the next call
    seq.tick("disconnect", now=t[0])  # ...which happens here
    assert "close:10.0" in actions.calls


def test_process_not_running_skips_close_call():
    actions = FakeActions()
    actions._running = False
    t = [0.0]
    seq = RecoverySequence(actions, cfg(), clock=lambda: t[0])
    run_full_cycle(seq, t)
    assert not any(c.startswith("close:") for c in actions.calls)
    assert "open_client" in actions.calls


def test_prefer_reconnect_button_is_respected():
    actions = FakeActions()
    t = [0.0]
    seq = RecoverySequence(actions, cfg(prefer_button="reconnect"), clock=lambda: t[0])
    seq.tick("disconnect", now=0.0)
    assert "click:reconnect" in actions.calls


def test_rehandoff_after_relaunch_continues_the_same_incident():
    """A new RECOVERING entry before IN_MATCH (e.g. LAUNCHING timed out again)
    must pick the sequence back up and keep counting attempts, not restart."""
    actions = FakeActions()
    t = [0.0]
    seq = RecoverySequence(actions, cfg(), clock=lambda: t[0])
    run_full_cycle(seq, t)
    assert seq.stats.attempts == 1
    t[0] += 100
    run_full_cycle(seq, t)
    assert seq.stats.attempts == 2
    # Only one "recovery_start" incident log for the whole ongoing incident.
    assert actions.calls.count("incident:recovery_start:disconnect") == 1


def test_browser_fallback_used_once_after_max_attempts_exhausted():
    actions = FakeActions()
    t = [0.0]
    seq = RecoverySequence(actions, cfg(max_attempts=2), clock=lambda: t[0])
    for _ in range(2):
        run_full_cycle(seq, t)
        t[0] += 100
    assert actions.calls.count("open_client") == 2
    result = run_full_cycle(seq, t)
    assert result is State.LAUNCHING
    assert actions.calls.count("open_browser") == 1
    assert seq.stats.used_browser_fallback is True


def test_backoff_after_browser_fallback_also_exhausted():
    actions = FakeActions()
    t = [0.0]
    seq = RecoverySequence(actions, cfg(max_attempts=1, alert_after_cycles=2), clock=lambda: t[0])
    run_full_cycle(seq, t)              # attempt 1: normal client
    t[0] += 100
    run_full_cycle(seq, t)              # attempt 2: browser fallback
    t[0] += 100
    result = run_full_cycle(seq, t)     # attempt 3: both avenues used -> backoff
    assert result is State.RECOVERING
    assert seq.stage == "backoff"
    assert any(c.startswith("incident:recovery_alert") for c in actions.calls)


def test_backoff_wait_grows_exponentially_and_caps():
    actions = FakeActions()
    t = [0.0]
    # max_attempts=1 and no browser fallback: the first relaunch uses the
    # normal client, the second has nothing left to try -> straight to backoff.
    seq = RecoverySequence(actions, cfg(max_attempts=1, backoff_initial_s=30, backoff_cap_s=100,
                                        browser_fallback=False), clock=lambda: t[0])
    run_full_cycle(seq, t)
    t[0] += 100
    run_full_cycle(seq, t)
    assert seq.stage == "backoff"
    first_wait = seq._current_backoff()
    t[0] += first_wait - 1
    assert seq.tick("disconnect", now=t[0]) is State.RECOVERING
    assert seq.stage == "backoff"  # not elapsed yet
    t[0] += 2
    seq.tick("disconnect", now=t[0])
    assert seq.stage == "click_leave"  # backoff elapsed, retrying

    run_full_cycle(seq, t)  # click -> wait -> close -> relaunch -> second backoff (capped at 100)
    assert seq.stage == "backoff"
    second_wait = seq._current_backoff()
    assert second_wait > first_wait
    assert second_wait <= 100


def test_full_reset_logs_resolution_and_clears_state():
    actions = FakeActions()
    t = [0.0]
    seq = RecoverySequence(actions, cfg(), clock=lambda: t[0])
    run_full_cycle(seq, t)
    t[0] += 20
    seq.full_reset()
    assert seq.stage == "idle"
    assert seq.stats.attempts == 0
    assert any(c.startswith("incident:recovery_resolved") for c in actions.calls)


def test_full_reset_when_already_idle_is_a_no_op():
    actions = FakeActions()
    seq = RecoverySequence(actions, cfg(), clock=lambda: 0.0)
    seq.full_reset()
    assert actions.calls == []


def test_next_incident_after_resolution_starts_attempts_from_zero():
    actions = FakeActions()
    t = [0.0]
    seq = RecoverySequence(actions, cfg(), clock=lambda: t[0])
    run_full_cycle(seq, t)
    assert seq.stats.attempts == 1
    seq.full_reset()
    t[0] += 1000
    run_full_cycle(seq, t)
    assert seq.stats.attempts == 1  # fresh incident, not 2
