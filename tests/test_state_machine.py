"""Replay tests over synthetic signal sequences - one per §6.1 transition,
the FFA-search early abort, the mid-game join prompt, and respawn counting.

Each scenario jumps the machine straight to the state under test (a fresh
``StateMachine``'s sub-helpers already start in their reset position, so
this is equivalent to having arrived there naturally) and then drives it
with real ``tick()`` calls on a ``ManualClock`` - exercising the exact same
transition code a live run would use, without re-deriving the LAUNCHING ->
LOADING -> LOBBY boot sequence in every single test. One full boot-to-match
test (`test_full_happy_path_launch_to_in_match`) covers that sequence for real.
"""

from __future__ import annotations

import itertools

import pytest

from warden.config.schema import StateTimeouts
from warden.core.state_machine import NullActions, Signals, State, StateMachine
from warden.tools.replay import ManualClock, replay

FAST_TIMEOUTS = StateTimeouts(
    launching=2, loading=2, lobby=2, mode_select=2, midgame_join=1,
    loadout=2, dead=2, match_end=2, unknown_after=2,
)


class FakeActions(NullActions):
    def __init__(self):
        self.calls: list[str] = []
        self.loadout_result = True
        self.recovering_result = State.RECOVERING
        self.reapplied = 0

    def launch(self):
        self.calls.append("launch")

    def click_play(self):
        self.calls.append("click_play")

    def scroll_mode_list(self):
        self.calls.append("scroll_mode_list")
        return True

    def click_ffa(self):
        self.calls.append("click_ffa")
        return True

    def click_map_vote(self):
        self.calls.append("click_map_vote")
        return True

    def click_midgame_join(self):
        self.calls.append("click_midgame_join")

    def click_match_continue(self):
        self.calls.append("click_match_continue")

    def press_respawn(self):
        self.calls.append("press_respawn")

    def run_loadout(self) -> bool:
        self.calls.append("run_loadout")
        return self.loadout_result

    def reapply_loadout_if_due(self) -> bool:
        self.reapplied += 1
        return True

    def save_unknown_frame(self):
        self.calls.append("save_unknown_frame")

    def press_escape(self):
        self.calls.append("press_escape")

    def handle_recovering(self, cause: str) -> State:
        self.calls.append(f"handle_recovering:{cause}")
        return self.recovering_result

    def on_incident(self, cause: str) -> None:
        self.calls.append(f"incident:{cause}")


def make(state: State = State.IDLE, timeouts: StateTimeouts = FAST_TIMEOUTS):
    """A fresh StateMachine, optionally dropped directly into ``state``.

    Direct assignment (not ``force_state``) is deliberate: it skips ``_go``'s
    entry side effects (counter bumps, sub-flow resets) since a brand new
    machine's sub-flows are already at their reset position - equivalent to
    having arrived there naturally, without double-counting anything the
    scenario's own ticks are about to trigger for real.
    """
    actions = FakeActions()
    clock = ManualClock(0.0)
    m = StateMachine(actions, timeouts=timeouts, clock=clock)
    if state is not State.IDLE:
        m.state = state
        m._entered_at = clock()
    return m, actions, clock


def tick(m: StateMachine, clock: ManualClock, signal: Signals, dt: float = 0.25) -> State:
    clock.advance(dt)
    return m.tick(signal)


def run(m, clock, signal: Signals, n: int, dt: float = 0.25) -> State:
    state = m.state
    for _ in range(n):
        state = tick(m, clock, signal, dt)
    return state


# --------------------------------------------------------------------------- true end-to-end boot


def test_full_happy_path_launch_to_in_match():
    actions = FakeActions()
    m = StateMachine(actions, timeouts=FAST_TIMEOUTS, clock=ManualClock(0.0))
    frames = [
        Signals(client_window_exists=False),   # still waiting to launch
        Signals(client_window_exists=True),    # client window appears -> LOADING
        Signals(lobby_play=True),              # -> LOBBY
        Signals(lobby_play=True),              # LOBBY handler runs (clicks play)
        Signals(mode_list=True),               # -> MODE_SELECT
        Signals(mode_list=True, ffa_tile=True),  # clicks FFA
        Signals(weapon_picker=True),           # -> LOADOUT
        Signals(health_bar=True),              # loadout commits -> IN_MATCH
    ]
    result = replay(frames, actions, sm=m)
    assert result.final_state is State.IN_MATCH
    assert "click_play" in actions.calls
    assert "click_ffa" in actions.calls
    assert "run_loadout" in actions.calls
    assert result.transitions[0].frm is State.IDLE and result.transitions[0].to is State.LAUNCHING


# --------------------------------------------------------------------------- LAUNCHING / LOADING


def test_launching_timeout_goes_to_recovering():
    m, actions, clock = make(State.LAUNCHING)
    final = run(m, clock, Signals(client_window_exists=False), 20)
    assert final is State.RECOVERING


def test_loading_timeout_goes_to_recovering():
    m, actions, clock = make(State.LOADING)
    final = run(m, clock, Signals(client_window_exists=True), 20)
    assert final is State.RECOVERING


def test_loading_jumps_straight_to_in_match_if_already_alive():
    m, actions, clock = make(State.LOADING)
    assert tick(m, clock, Signals(health_bar=True)) is State.IN_MATCH


def test_loading_to_lobby():
    m, actions, clock = make(State.LOADING)
    assert tick(m, clock, Signals(lobby_play=True)) is State.LOBBY


# --------------------------------------------------------------------------- LOBBY


def test_lobby_clicks_play_once_on_entry():
    m, actions, clock = make(State.LOBBY)
    tick(m, clock, Signals())
    tick(m, clock, Signals())
    tick(m, clock, Signals())
    assert actions.calls.count("click_play") == 1


def test_lobby_retries_once_then_recovers_on_repeated_timeout():
    # lobby_play=True throughout: we're genuinely still looking at the lobby
    # screen, just getting no response - a bare all-False signal would
    # instead trip the global "nothing recognized" timeout first (it starts
    # counting from the same zero point as LOBBY's own timeout).
    m, actions, clock = make(State.LOBBY)
    final = run(m, clock, Signals(lobby_play=True), 40)  # two 2s timeout windows at dt=0.25
    assert actions.calls.count("click_play") >= 2
    assert final is State.RECOVERING


def test_lobby_to_mode_select_on_mode_list():
    m, actions, clock = make(State.LOBBY)
    assert tick(m, clock, Signals(mode_list=True)) is State.MODE_SELECT


def test_lobby_jumps_to_in_match_if_already_alive():
    m, actions, clock = make(State.LOBBY)
    assert tick(m, clock, Signals(health_bar=True)) is State.IN_MATCH


# --------------------------------------------------------------------------- MODE_SELECT + early abort


@pytest.mark.parametrize("abort_signal,expected", [
    ("weapon_picker", State.LOADOUT),
    ("respawn_prompt", State.DEAD),
    ("health_bar", State.IN_MATCH),
])
def test_mode_select_aborts_early_when_already_in(abort_signal, expected):
    m, actions, clock = make(State.MODE_SELECT)
    final = tick(m, clock, Signals(**{abort_signal: True}))
    assert final is expected
    assert "click_ffa" not in actions.calls


def test_mode_select_scrolls_then_clicks_ffa_once_found():
    m, actions, clock = make(State.MODE_SELECT)
    tick(m, clock, Signals())
    tick(m, clock, Signals())
    final = tick(m, clock, Signals(ffa_tile=True))
    assert actions.calls.count("scroll_mode_list") >= 1
    assert actions.calls.count("click_ffa") == 1
    assert final is State.MODE_SELECT  # still waiting for weapon_picker/health_bar to confirm we joined


def test_mode_select_ffa_click_then_weapon_picker_moves_to_loadout():
    m, actions, clock = make(State.MODE_SELECT)
    tick(m, clock, Signals(ffa_tile=True))
    assert tick(m, clock, Signals(weapon_picker=True)) is State.LOADOUT


def test_mode_select_timeout_returns_to_lobby():
    # Stop right at the 2s timeout - one tick further and LOBBY's own
    # "mode_list visible" check would immediately bounce back to MODE_SELECT.
    m, actions, clock = make(State.MODE_SELECT)
    final = run(m, clock, Signals(mode_list=True), 8)
    assert final is State.LOBBY


# --------------------------------------------------------------------------- MIDGAME_JOIN


def test_midgame_join_prompt_preempts_mode_select_and_is_clicked():
    m, actions, clock = make(State.MODE_SELECT)
    assert tick(m, clock, Signals(midgame_join=True)) is State.MIDGAME_JOIN
    tick(m, clock, Signals(midgame_join=True))  # handler's own first tick does the click
    assert "click_midgame_join" in actions.calls


def test_midgame_join_resolved_returns_to_mode_select():
    m, actions, clock = make(State.MIDGAME_JOIN)
    assert tick(m, clock, Signals()) is State.MODE_SELECT


def test_midgame_join_timeout_also_returns_to_mode_select():
    # Stop right at the timeout - if the prompt is still (per the signal)
    # genuinely on screen, MODE_SELECT's own global pre-empt would otherwise
    # immediately bounce straight back into MIDGAME_JOIN on the next tick.
    m, actions, clock = make(State.MIDGAME_JOIN)
    final = run(m, clock, Signals(midgame_join=True), 4)  # lands exactly on the 1s timeout tick
    assert final is State.MODE_SELECT


# --------------------------------------------------------------------------- LOADOUT


def test_loadout_commits_and_moves_to_in_match():
    m, actions, clock = make(State.LOADOUT)
    final = tick(m, clock, Signals(weapon_picker=True))
    assert "run_loadout" in actions.calls
    assert final is State.IN_MATCH


def test_loadout_aborts_on_death_mid_transaction():
    m, actions, clock = make(State.LOADOUT)
    actions.loadout_result = False
    final = tick(m, clock, Signals(weapon_picker=True, respawn_prompt=True))
    assert final is State.DEAD


def test_loadout_timeout_falls_back_to_mode_select_or_in_match():
    m, actions, clock = make(State.LOADOUT)
    actions.loadout_result = False
    # Stop feeding weapon_picker the instant the timeout fires (exactly 8
    # ticks at dt=0.25 for a 2s timeout) - one tick further and MODE_SELECT's
    # own early-abort would immediately bounce back to LOADOUT (the picker
    # would still be genuinely open on screen).
    final = run(m, clock, Signals(weapon_picker=True), 8)
    assert final in (State.MODE_SELECT, State.IN_MATCH)
    assert "incident:loadout_timeout" in actions.calls


def test_loadout_picker_closing_on_its_own_falls_through():
    m, actions, clock = make(State.LOADOUT)
    actions.loadout_result = False
    tick(m, clock, Signals(weapon_picker=True))
    # The picker-closed check needs since_entry > 1.0s, not just one tick.
    run(m, clock, Signals(weapon_picker=False, health_bar=True), 4)
    final = tick(m, clock, Signals(weapon_picker=False, health_bar=True))
    assert final is State.IN_MATCH


# --------------------------------------------------------------------------- DEAD / respawn


def test_death_increments_respawns_and_runs_full_sequence():
    m, actions, clock = make(State.IN_MATCH)
    # Entering DEAD is one tick; the respawn flow's own stages (press ->
    # watch -> react to the switch window) each need a tick of their own.
    assert tick(m, clock, Signals(respawn_prompt=True)) is State.DEAD
    assert m.counters.respawns == 1
    tick(m, clock, Signals())  # respawn flow's first tick: press Space
    assert actions.calls.count("press_respawn") == 1
    tick(m, clock, Signals())  # respawn_prompt now gone -> start watching
    final = tick(m, clock, Signals(switch_weapons=True))  # switch window seen -> reapply, done
    assert final is State.IN_MATCH
    assert actions.reapplied == 1


def test_second_death_increments_respawns_again():
    def die_and_respawn():
        tick(m, clock, Signals(respawn_prompt=True))
        tick(m, clock, Signals())
        tick(m, clock, Signals())
        tick(m, clock, Signals(health_bar=True))

    m, actions, clock = make(State.IN_MATCH)
    die_and_respawn()
    assert m.state is State.IN_MATCH
    die_and_respawn()
    assert m.counters.respawns == 2


def test_dead_repress_after_1_5s_if_prompt_persists():
    m, actions, clock = make(State.DEAD)
    tick(m, clock, Signals(respawn_prompt=True))  # first press
    run(m, clock, Signals(respawn_prompt=True), 5)  # 5*0.25=1.25s, under 1.5s
    assert actions.calls.count("press_respawn") == 1
    tick(m, clock, Signals(respawn_prompt=True))  # now past 1.5s
    assert actions.calls.count("press_respawn") == 2


def test_dead_timeout_goes_to_unknown():
    # UNKNOWN is a one-tick waypoint on the way to RECOVERING (like the
    # global "nothing recognized" case) - check it was passed through rather
    # than expecting it to still be the state after many more ticks.
    m, actions, clock = make(State.DEAD)
    transitions = []
    m.on_transition = transitions.append
    run(m, clock, Signals(respawn_prompt=True), 20)
    assert any(t.frm is State.DEAD and t.to is State.UNKNOWN for t in transitions)


# --------------------------------------------------------------------------- MATCH_END


def test_match_end_requeue_counts_and_returns_to_mode_select():
    m, actions, clock = make(State.MATCH_END)
    final = tick(m, clock, Signals(mode_list=True))
    assert final is State.MODE_SELECT
    assert m.counters.re_queues == 1


def test_match_end_to_lobby():
    m, actions, clock = make(State.MATCH_END)
    assert tick(m, clock, Signals(lobby_play=True)) is State.LOBBY


def test_match_end_clicks_continue_periodically():
    # match_end's own 2s timeout and the 2s click cooldown would otherwise
    # race from the same zero point; give this one a longer state timeout
    # so a couple of periodic clicks get a chance to fire first.
    roomy = FAST_TIMEOUTS.model_copy(update={"match_end": 8})
    m, actions, clock = make(State.MATCH_END, timeouts=roomy)
    run(m, clock, Signals(match_end=True), 20)
    assert actions.calls.count("click_match_continue") >= 2


def test_match_end_timeout_falls_back_to_lobby():
    m, actions, clock = make(State.MATCH_END)
    final = run(m, clock, Signals(match_end=True), 20)
    assert final is State.LOBBY


# --------------------------------------------------------------------------- disconnect / recovery


def test_one_frame_modal_flash_does_not_trigger_recovery():
    m, actions, clock = make(State.IN_MATCH)
    tick(m, clock, Signals(disconnect_modal=True))
    final = tick(m, clock, Signals(health_bar=True))
    assert final is State.IN_MATCH
    assert m.state is not State.RECOVERING


def test_disconnect_vanishing_before_confirmed_resets_the_candidate():
    m, actions, clock = make(State.IN_MATCH)
    tick(m, clock, Signals(disconnect_modal=True))
    tick(m, clock, Signals(disconnect_modal=True))
    tick(m, clock, Signals(health_bar=True))  # vanished before 3 captures / 1.5s
    tick(m, clock, Signals(disconnect_modal=True))
    assert m.state is not State.RECOVERING  # candidate had to restart from zero


def test_sustained_disconnect_modal_triggers_recovery():
    m, actions, clock = make(State.IN_MATCH)
    final = run(m, clock, Signals(disconnect_modal=True), 10)
    assert final is State.RECOVERING
    assert "incident:disconnect" in actions.calls


def test_sustained_disconnect_modal_passes_through_disconnected_state():
    m, actions, clock = make(State.IN_MATCH)
    transitions = []
    m.on_transition = transitions.append
    run(m, clock, Signals(disconnect_modal=True), 10)
    assert any(t.to is State.DISCONNECTED for t in transitions)
    assert any(t.to is State.RECOVERING for t in transitions)


def test_recovery_exits_on_two_health_bar_confirmations_5s_apart():
    m, actions, clock = make(State.RECOVERING)
    tick(m, clock, Signals(health_bar=True))
    assert m.state is State.RECOVERING  # only one confirmation so far
    run(m, clock, Signals(), 25)  # >5s gap at dt=0.25
    final = tick(m, clock, Signals(health_bar=True))
    assert final is State.IN_MATCH


def test_recovery_calls_handle_recovering_each_tick_until_handed_off():
    m, actions, clock = make(State.RECOVERING)
    actions.recovering_result = State.RECOVERING
    run(m, clock, Signals(), 3)
    assert actions.calls.count("handle_recovering:retry") == 3
    actions.recovering_result = State.LAUNCHING
    final = tick(m, clock, Signals())
    assert final is State.LAUNCHING


def test_roblox_updating_triggers_recovery_from_any_state():
    m, actions, clock = make(State.IN_MATCH)
    final = tick(m, clock, Signals(roblox_updating=True))
    assert final is State.RECOVERING
    assert "incident:roblox_updating" in actions.calls


def test_process_gone_triggers_recovery_only_in_active_states():
    m, actions, clock = make(State.IN_MATCH)
    final = tick(m, clock, Signals(process_running=False))
    assert final is State.RECOVERING


def test_process_gone_ignored_while_still_launching():
    m, actions, clock = make(State.LAUNCHING)
    final = tick(m, clock, Signals(client_window_exists=False, process_running=False))
    assert final is State.LAUNCHING


def test_frozen_while_in_match_triggers_recovery():
    m, actions, clock = make(State.IN_MATCH)
    final = tick(m, clock, Signals(health_bar=True, frozen=True))
    assert final is State.RECOVERING


def test_frozen_ignored_outside_in_match():
    m, actions, clock = make(State.LOBBY)
    final = tick(m, clock, Signals(frozen=True))
    assert final is State.LOBBY


# --------------------------------------------------------------------------- unknown screen


def test_unknown_after_nothing_recognized_for_too_long():
    m, actions, clock = make(State.IN_MATCH)
    final = run(m, clock, Signals(), 20)  # 20*0.25=5s > 2s unknown_after, nothing primary detected
    assert "save_unknown_frame" in actions.calls
    assert "press_escape" in actions.calls
    assert final is State.RECOVERING


def test_unknown_passes_through_unknown_state():
    m, actions, clock = make(State.IN_MATCH)
    transitions = []
    m.on_transition = transitions.append
    run(m, clock, Signals(), 20)
    assert any(t.to is State.UNKNOWN for t in transitions)


def test_unknown_not_triggered_while_launching_or_loading():
    m, actions, clock = make(State.LAUNCHING)
    final = run(m, clock, Signals(client_window_exists=False), 20)
    assert final is State.RECOVERING  # via the launching timeout, never via UNKNOWN
    assert "save_unknown_frame" not in actions.calls


def test_health_bar_resets_the_unknown_clock():
    m, actions, clock = make(State.IN_MATCH)
    run(m, clock, Signals(), 6)  # 1.5s of nothing - close to the 2s limit but not past it
    tick(m, clock, Signals(health_bar=True))  # resets the clock
    final = run(m, clock, Signals(), 6)  # only 1.5s since the reset - still not enough to trip
    assert final is State.IN_MATCH
    assert "save_unknown_frame" not in actions.calls


# --------------------------------------------------------------------------- counters & lifecycle


def test_counters_start_at_zero():
    m, actions, clock = make()
    assert m.counters.respawns == 0
    assert m.counters.reconnects == 0
    assert m.counters.re_queues == 0
    assert m.counters.loadout_fixes == 0


def test_pause_resume_preserves_state_and_blocks_ticking():
    m, actions, clock = make(State.LOBBY)
    m.pause()
    assert m.state is State.PAUSED
    before = len(actions.calls)
    tick(m, clock, Signals(mode_list=True))  # must be ignored while paused
    assert m.state is State.PAUSED
    assert len(actions.calls) == before
    m.resume()
    assert m.state is State.LOBBY
    assert tick(m, clock, Signals(mode_list=True)) is State.MODE_SELECT


def test_stop_then_start_relaunches():
    actions = FakeActions()
    m = StateMachine(actions, timeouts=FAST_TIMEOUTS, clock=ManualClock(0.0))
    m.start()
    m.stop()
    assert m.state is State.STOPPED
    m.start()
    assert m.state is State.LAUNCHING
    assert actions.calls.count("launch") == 2
