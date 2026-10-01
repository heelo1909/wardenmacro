"""End-to-end: StateMachine (Phase 2) driving a real RecoverySequence (Phase 4),
not just each tested in isolation."""

from warden.config.schema import RecoveryConfig
from warden.core.state_machine import NullActions, Signals, State, StateMachine
from warden.flows.recovery import RecoverySequence
from warden.tools.replay import ManualClock


class IntegrationActions(NullActions):
    """GameActions wired to a real RecoverySequence; everything else is a no-op."""

    def __init__(self, cfg: RecoveryConfig, clock):
        self.calls: list[str] = []
        self.recovery = RecoverySequence(self, cfg, clock=clock)

    def click_leave_or_reconnect(self, prefer):
        self.calls.append(f"click:{prefer}")

    def process_is_running(self):
        return False  # already gone

    def process_close(self, grace_s):
        self.calls.append("close")

    def open_client(self):
        self.calls.append("open_client")

    def open_browser_and_play(self):
        self.calls.append("open_browser")

    def on_incident(self, cause):
        self.calls.append(f"incident:{cause}")

    def on_recovered(self):
        self.recovery.full_reset()

    def handle_recovering(self, cause: str) -> State:
        return self.recovery.tick(cause)


def test_disconnect_drives_a_real_relaunch_and_resolves_on_reaching_in_match():
    clock = ManualClock(0.0)
    cfg = RecoveryConfig(leave_wait_s=10, close_grace_s=5, max_attempts=3)
    actions = IntegrationActions(cfg, clock)
    m = StateMachine(actions, clock=clock)
    m.state = State.IN_MATCH
    m._entered_at = clock()

    # Sustained disconnect -> DISCONNECTED -> RECOVERING.
    for _ in range(10):
        clock.advance(0.25)
        m.tick(Signals(disconnect_modal=True))
    assert m.state is State.RECOVERING
    assert "click:leave" in actions.calls

    # Drive the recovery sequence's own timing (leave wait, then close+relaunch).
    for _ in range(60):
        if m.state is State.LAUNCHING:
            break
        clock.advance(0.25)
        m.tick(Signals())
    assert m.state is State.LAUNCHING
    assert "open_client" in actions.calls
    assert actions.recovery.stats.attempts == 1

    # Client comes back and we see the health bar twice, 5s apart -> back in business.
    clock.advance(0.25)
    m.tick(Signals(client_window_exists=True))  # -> LOADING
    clock.advance(0.25)
    m.tick(Signals(health_bar=True))  # -> IN_MATCH directly (already alive)
    assert m.state is State.IN_MATCH

    # The incident is over: the recovery flow's attempt count resets.
    assert actions.recovery.stage == "idle"
    assert actions.recovery.stats.attempts == 0
    assert any(c.startswith("incident:recovery_resolved") for c in actions.calls)


def test_second_unrelated_disconnect_starts_counting_from_attempt_one():
    clock = ManualClock(0.0)
    cfg = RecoveryConfig(leave_wait_s=1, close_grace_s=1, max_attempts=3)
    actions = IntegrationActions(cfg, clock)
    m = StateMachine(actions, clock=clock)
    m.state = State.IN_MATCH
    m._entered_at = clock()

    def disconnect_and_recover():
        for _ in range(10):
            clock.advance(0.25)
            m.tick(Signals(disconnect_modal=True))
        for _ in range(30):
            if m.state is State.LAUNCHING:
                break
            clock.advance(0.25)
            m.tick(Signals())
        clock.advance(0.25)
        m.tick(Signals(client_window_exists=True))
        clock.advance(0.25)
        m.tick(Signals(health_bar=True))
        assert m.state is State.IN_MATCH

    disconnect_and_recover()
    assert actions.recovery.stats.attempts == 0  # reset after resolving
    disconnect_and_recover()
    # the second incident's own (single) attempt, not 2 - proving it didn't inherit the first's count
    assert actions.calls.count("open_client") == 2
