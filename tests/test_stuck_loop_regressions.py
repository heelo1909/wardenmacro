"""Regression tests for the "keeps rejoining/refreshing, never opens FFA or
picks weapons" bug reported after the first real run (2026-10-01).

Root causes covered here:
1. Start always opened the roblox:// launch URI, even with Roblox already
   open - which makes Roblox leave and rejoin.
2. Any screen-recognition timeout (loading / lobby / mode select / unknown)
   jumped straight to RECOVERING, which closes and relaunches the client -
   with uncalibrated detectors that repeats forever.
3. Play and the FFA tile were each clicked once; a lost click meant waiting
   out the timeout (-> relaunch).
4. Recovery clicked the disconnect-modal "Leave" spot even when there was no
   modal, i.e. a stray click into the lobby.
5. Loadout verified the screen the very next tick after clicking, before
   the game redrew, so a correct click was reported as a failure.
"""

from __future__ import annotations

from warden.config.schema import LoadoutSlotUI, LoadoutUI, RecoveryConfig, ROI, StateTimeouts
from warden.core.state_machine import Signals, State, StateMachine
from warden.flows.recovery import RecoverySequence
from warden.tools.replay import ManualClock

from tests.test_state_machine import FAST_TIMEOUTS, FakeActions


class StuckActions(FakeActions):
    def __init__(self):
        super().__init__()
        self.stuck_messages: list[str] = []

    def on_stuck(self, message: str) -> None:
        self.stuck_messages.append(message)


def make(state=State.IDLE, **kw):
    actions = StuckActions()
    clock = ManualClock(0.0)
    m = StateMachine(actions, timeouts=FAST_TIMEOUTS, clock=clock, **kw)
    if state is not State.IDLE:
        m.state = state
        m._entered_at = clock()
    return m, actions, clock


def run(m, clock, signal, seconds, dt=0.25):
    for _ in range(int(seconds / dt)):
        clock.advance(dt)
        m.tick(signal)
    return m.state


def test_start_attaches_to_a_running_client_instead_of_relaunching():
    m, actions, clock = make()
    m.start(attach=True)
    assert m.state is State.LOADING
    assert "launch" not in actions.calls


def test_start_without_a_client_still_launches():
    m, actions, clock = make()
    m.start()
    assert m.state is State.LAUNCHING
    assert actions.calls == ["launch"]


def test_unrecognized_lobby_never_relaunches_a_healthy_client_before_pausing():
    """Nothing calibrated: the old code relaunched every ~lobby timeout,
    forever. Now: soft retries, a bounded number of relaunches, then pause."""
    m, actions, clock = make(State.LOBBY, max_soft_resets=3, max_stuck_relaunches=1)
    m._last_seen = clock()
    healthy_but_unrecognized = Signals(lobby_play=True)  # lobby visible, mode list never detected
    relaunches = 0
    for _ in range(4000):
        clock.advance(0.25)
        before = m.state
        m.tick(healthy_but_unrecognized)
        if before is not State.RECOVERING and m.state is State.RECOVERING:
            relaunches += 1
            # pretend the relaunch worked and we're back at the lobby
            m.force_state(State.LOBBY, "relaunched")
        if m.state is State.PAUSED:
            break
    assert m.state is State.PAUSED
    assert relaunches == 1
    assert actions.stuck_messages and "mode list" in actions.stuck_messages[0]
    assert actions.calls.count("press_escape") >= 3


def test_lobby_timeout_soft_resets_instead_of_recovering():
    m, actions, clock = make(State.LOBBY)
    m._last_seen = clock()
    run(m, clock, Signals(lobby_play=True), FAST_TIMEOUTS.lobby + 0.5)
    assert m.state is State.LOBBY
    assert "press_escape" in actions.calls
    assert not any(c.startswith("handle_recovering") for c in actions.calls)


def test_play_is_reclicked_while_the_mode_list_hasnt_opened():
    timeouts = StateTimeouts(lobby=30, unknown_after=60)
    actions = StuckActions()
    clock = ManualClock(0.0)
    m = StateMachine(actions, timeouts=timeouts, clock=clock, lobby_click_interval=4.0)
    m.state, m._entered_at = State.LOBBY, 0.0
    run(m, clock, Signals(lobby_play=True), 13)
    assert actions.calls.count("click_play") == 4  # t=0.25, ~4.25, ~8.25, ~12.25


def test_ffa_tile_is_reclicked_if_the_first_click_was_lost():
    timeouts = StateTimeouts(mode_select=30, unknown_after=60)
    actions = StuckActions()
    clock = ManualClock(0.0)
    m = StateMachine(actions, timeouts=timeouts, clock=clock, ffa_click_interval=2.5)
    m.state, m._entered_at = State.MODE_SELECT, 0.0
    run(m, clock, Signals(mode_list=True, ffa_tile=True), 6)
    assert actions.calls.count("click_ffa") == 3


def test_a_long_pause_does_not_trigger_a_false_stuck_detection_on_resume():
    """2026-10-03 user report: paused Warden mid-match, resumed ~46s later
    (longer than unknown_after) and it immediately treated the screen as
    stuck - escaping, soft-resetting, eventually relaunching - even though
    nothing was wrong; it had just been sitting there paused. tick() is a
    no-op for the whole pause (see tick()), so the "nothing recognized"
    clock (_last_seen) never advances either, but real time keeps passing;
    _entered_at already gets refreshed by _go() on resume, _last_seen didn't."""
    timeouts = StateTimeouts(unknown_after=45)
    actions = StuckActions()
    clock = ManualClock(0.0)
    m = StateMachine(actions, timeouts=timeouts, clock=clock)
    m.state, m._entered_at = State.IN_MATCH, 0.0
    m._last_seen = 0.0
    m.tick(Signals(health_bar=True))   # confirmed healthy right before pausing
    clock.advance(1.0)
    m.pause()
    clock.advance(46.0)                # longer than unknown_after, entirely while paused
    m.resume()
    clock.advance(0.25)
    m.tick(Signals(health_bar=False))  # one frame with nothing recognized right after resume
    assert m.state is State.IN_MATCH   # must not jump to UNKNOWN/RECOVERING over paused time


def test_map_vote_screen_gets_clicked_instead_of_sitting_idle():
    """2026-10-03 user report: after picking FFA, 'it needed help' / 'it just
    clicked the leave button' - the real gap was RIVALS' map-vote screen
    (countdown + map tiles) having no detector at all, so Warden sat doing
    nothing until the mode_select timeout gave up and soft-reset (escape back
    to the lobby), which looked like it had quit."""
    m, actions, clock = make(State.MODE_SELECT)
    clock.advance(0.25)
    m.tick(Signals(map_vote=True))
    assert "click_map_vote" in actions.calls
    assert m.state is State.MODE_SELECT  # stays put - the click resolves the screen itself


def test_map_vote_click_has_a_cooldown_not_spammed_every_tick():
    m, actions, clock = make(State.MODE_SELECT)
    for _ in range(5):
        clock.advance(0.25)
        m.tick(Signals(map_vote=True))
    assert actions.calls.count("click_map_vote") == 1  # well under ffa_click_interval (2.5s default)


def test_map_vote_does_not_trigger_a_false_stuck_escalation():
    """map_vote must count as 'something recognized' (like ffa_tile/mode_list
    do) so sitting on this screen for a while never looks like an unknown,
    stuck screen on its own. FAST_TIMEOUTS' mode_select=2s and unknown_after=2s
    both actively "try" to fire well before the 10s this loop runs for -
    neither should win while map_vote stays visible."""
    m, actions, clock = make(State.MODE_SELECT)
    for _ in range(40):
        clock.advance(0.25)
        m.tick(Signals(map_vote=True))
    assert m.state is State.MODE_SELECT


def test_map_vote_cooldown_resets_on_a_fresh_mode_select_entry():
    m, actions, clock = make(State.LOBBY)
    clock.advance(0.25)
    m.tick(Signals(mode_list=True))
    assert m.state is State.MODE_SELECT
    clock.advance(0.25)
    m.tick(Signals(map_vote=True))
    assert actions.calls.count("click_map_vote") == 1


def test_ffa_tile_visible_in_lobby_skips_straight_to_mode_select():
    m, actions, clock = make(State.LOBBY)
    clock.advance(0.25)
    m.tick(Signals(ffa_tile=True))
    assert m.state is State.MODE_SELECT


def test_loading_timeout_with_running_client_goes_to_lobby_not_recovery():
    m, actions, clock = make(State.LOADING)
    run(m, clock, Signals(client_window_exists=True, process_running=True), FAST_TIMEOUTS.loading + 0.5)
    assert m.state is State.LOBBY


def test_loading_timeout_with_no_client_still_recovers():
    m, actions, clock = make(State.LOADING)
    run(m, clock, Signals(client_window_exists=False, process_running=False), FAST_TIMEOUTS.loading + 0.5)
    assert m.state is State.RECOVERING


def test_reaching_a_match_clears_the_stuck_counters():
    m, actions, clock = make(State.LOBBY)
    m._soft_resets = 3
    m._stuck_relaunches = 1
    m.force_state(State.IN_MATCH, "test")
    assert m._soft_resets == 0 and m._stuck_relaunches == 0


def test_recovery_passes_the_real_cause_through():
    m, actions, clock = make(State.IN_MATCH)
    clock.advance(0.25)
    m.tick(Signals(process_running=False))
    clock.advance(0.25)
    m.tick(Signals(process_running=False))
    assert "handle_recovering:process_gone" in actions.calls


class _RecoveryActions:
    def __init__(self):
        self.calls = []

    def click_leave_or_reconnect(self, prefer):
        self.calls.append("click_leave")

    def process_is_running(self):
        return True

    def process_close(self, grace_s):
        self.calls.append("close")

    def open_client(self):
        self.calls.append("open_client")

    def open_browser_and_play(self):
        self.calls.append("browser")

    def on_incident(self, cause):
        pass


def test_recovery_only_clicks_leave_for_a_real_disconnect_modal():
    for cause, expect_click in (("disconnect", True), ("stuck", False), ("process_gone", False)):
        acts = _RecoveryActions()
        seq = RecoverySequence(acts, RecoveryConfig(leave_wait_s=0), clock=lambda: 0.0)
        for _ in range(6):
            if seq.tick(cause, now=0.0) is State.LAUNCHING:
                break
        assert ("click_leave" in acts.calls) is expect_click, cause
        assert "open_client" in acts.calls


def test_loadout_waits_for_the_ui_to_settle_before_verifying():
    import numpy as np

    from warden.flows.loadout import LoadoutTransaction

    class Lib:
        def get(self, path):
            return np.full((12, 12, 3), 255, np.uint8)

    clicks = []

    class Acts:
        def click_frac(self, fx, fy, what=""):
            clicks.append(what)
            return True

        def scroll(self, n, at):
            return True

    now = [0.0]
    frames = {"f": np.zeros((100, 100, 3), np.uint8)}
    ui = LoadoutUI(slots={"primary": LoadoutSlotUI(
        tab=(0.1, 0.1), grid_roi=ROI(x1=0, y1=0, x2=1, y2=1), verify_roi=ROI(x1=0, y1=0, x2=1, y2=1))})
    tx = LoadoutTransaction(Acts(), Lib(), ui, get_frame=lambda: frames["f"], clock=lambda: now[0],
                            settle_s=0.6, verify_attempts=3)
    tx.reset({"primary": "Thing"})
    tx.tick()            # check: not equipped -> tab stage
    tx.tick()            # clicks tab, starts settle
    assert clicks == ["primary tab"]
    tx.tick()            # still settling - must not search the stale frame yet
    assert len(clicks) == 1
    now[0] += 0.7
    assert tx._stage == "search"


def test_calibration_gaps_flag_uncalibrated_ffa_path_and_weapons(bundled_config, tmp_path):
    from warden.config import load_all
    from warden.flows.calibration import calibration_gaps
    from warden.vision.templates import TemplateLibrary

    loaded = load_all(bundled_config / "default.yaml")
    empty = TemplateLibrary(tmp_path / "none")
    gaps = calibration_gaps(loaded.app, loaded.preset, empty, empty)
    errors = [m for sev, m in gaps if sev == "error"]
    assert any("ffa_tile" in m for m in errors)
    # Weapons aren't a blocker any more: they're learned from the player's first pick.
    assert any("Grenade Launcher" in m for sev, m in gaps if sev == "info")


def test_calibration_gaps_clear_once_templates_exist(bundled_config, tmp_path):
    import numpy as np

    from warden.config import load_all
    from warden.flows.calibration import calibration_gaps
    from warden.flows.loadout import weapon_template_path
    from warden.vision.templates import TemplateLibrary

    loaded = load_all(bundled_config / "default.yaml")
    det, weap = TemplateLibrary(tmp_path / "d"), TemplateLibrary(tmp_path / "w")
    img = np.zeros((10, 10, 3), np.uint8)
    for name, cfg in loaded.app.detectors.items():
        if cfg.method == "template" and cfg.template:
            det.save(cfg.template.path, img)
    for slot, weapon in loaded.preset.loadout.slots().items():
        if weapon:
            weap.save(weapon_template_path(slot, weapon), img)
    assert calibration_gaps(loaded.app, loaded.preset, det, weap) == []


def test_template_library_falls_back_to_older_install_folder(tmp_path):
    import numpy as np

    from warden.vision.templates import TemplateLibrary

    old = TemplateLibrary(tmp_path / "install")
    old.save("templates/ffa_tile.png", np.zeros((8, 8, 3), np.uint8))
    lib = TemplateLibrary(tmp_path / "home", fallbacks=[tmp_path / "install"])
    assert lib.get("templates/ffa_tile.png") is not None
    saved = lib.save("templates/new.png", np.zeros((8, 8, 3), np.uint8))
    assert saved.parent.parent == tmp_path / "home"
