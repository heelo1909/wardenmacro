"""The state machine from HANDOFF.md section 6.1.

``StateMachine`` is pure decision logic: given the current state, how long
we've been in it, and this tick's detector ``Signals``, it decides the next
state and calls the matching method(s) on a ``GameActions`` implementation.
It never touches capture/input/detectors directly, so it's fully testable
with synthetic signal sequences (see tests/test_state_machine.py and
tools/replay.py) with no Roblox client anywhere nearby.

Global interrupts (disconnect, Roblox updating, process gone, frozen) are
checked before any per-state logic, matching "always-on detectors" in
section 4.2. The finicky respawn and mode-select-search timing live in
``flows/respawn.py`` and ``flows/lobby.py`` so this file stays about *when
to change state*, not *how to click things*.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field, fields
from enum import Enum
from typing import Protocol

from warden.config.schema import StateTimeouts
from warden.flows.lobby import ModeSelectSearch
from warden.flows.respawn import RespawnFlow

log = logging.getLogger(__name__)


class State(Enum):
    IDLE = "IDLE"
    LAUNCHING = "LAUNCHING"
    LOADING = "LOADING"
    LOBBY = "LOBBY"
    MODE_SELECT = "MODE_SELECT"
    MIDGAME_JOIN = "MIDGAME_JOIN"
    LOADOUT = "LOADOUT"
    IN_MATCH = "IN_MATCH"
    DEAD = "DEAD"
    MATCH_END = "MATCH_END"
    DISCONNECTED = "DISCONNECTED"
    RECOVERING = "RECOVERING"
    UNKNOWN = "UNKNOWN"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"


# States where "nothing detected" is expected and normal, so the UNKNOWN
# catch-all (section 6.1: "nothing matched for 45s") must not fire there.
_UNKNOWN_EXEMPT = frozenset({
    State.IDLE, State.PAUSED, State.STOPPED, State.LAUNCHING, State.LOADING,
    State.RECOVERING, State.DISCONNECTED, State.UNKNOWN,
})

# "Active" states: the client is expected to be running. Outside these,
# a vanished process is not a recovery trigger (we may not have launched yet).
_ACTIVE_STATES = frozenset({
    State.LOBBY, State.MODE_SELECT, State.MIDGAME_JOIN, State.LOADOUT,
    State.IN_MATCH, State.DEAD, State.MATCH_END, State.UNKNOWN,
})


@dataclass(frozen=True)
class Signals:
    """This tick's confirmed detections, plus a couple of process facts."""

    lobby_play: bool = False
    mode_list: bool = False
    ffa_tile: bool = False
    map_vote: bool = False
    health_bar: bool = False
    respawn_prompt: bool = False
    weapon_picker: bool = False
    switch_weapons: bool = False
    midgame_join: bool = False
    match_end: bool = False
    disconnect_modal: bool = False
    roblox_updating: bool = False
    frozen: bool = False
    idle_warning: bool = False
    client_window_exists: bool = True
    process_running: bool = True

    def replace(self, **kw) -> Signals:
        return Signals(**{f.name: kw.get(f.name, getattr(self, f.name)) for f in fields(self)})


@dataclass
class Counters:
    respawns: int = 0
    reconnects: int = 0
    re_queues: int = 0
    loadout_fixes: int = 0
    time_lost_s: float = 0.0


class GameActions(Protocol):
    """Everything the state machine can ask the outside world to do.

    Phase 2 ships a working default for lobby/mode-select/respawn/match-end;
    ``run_loadout`` (Phase 3) and ``handle_recovering``/recovery internals
    (Phase 4) start as simple stand-ins and get replaced without this file
    changing.
    """

    def launch(self) -> None: ...
    def click_play(self) -> None: ...
    def scroll_mode_list(self) -> None: ...
    def click_ffa(self) -> None: ...
    def click_map_vote(self) -> None: ...
    def click_midgame_join(self) -> None: ...
    def click_match_continue(self) -> None: ...
    def press_respawn(self) -> None: ...
    def run_loadout(self) -> bool: ...
    def reapply_loadout_if_due(self) -> bool: ...
    def save_unknown_frame(self) -> None: ...
    def press_escape(self) -> None: ...
    def handle_recovering(self, cause: str) -> State: ...
    def on_incident(self, cause: str) -> None: ...
    def on_recovered(self) -> None: ...
    def on_stuck(self, message: str) -> None: ...
    def enter_match(self) -> None: ...
    def in_match_tick(self, idle_warning: bool) -> None: ...
    def leave_match(self) -> None: ...


class NullActions:
    """No-op default; useful as a base class or for dry imports."""

    def launch(self) -> None: pass
    def click_play(self) -> None: pass
    def scroll_mode_list(self) -> bool: return False
    def click_ffa(self) -> bool: return False
    def click_map_vote(self) -> bool: return False
    def click_midgame_join(self) -> None: pass
    def click_match_continue(self) -> None: pass
    def press_respawn(self) -> None: pass
    def run_loadout(self) -> bool: return True
    def reapply_loadout_if_due(self) -> bool: return False
    def save_unknown_frame(self) -> None: pass
    def press_escape(self) -> None: pass
    def handle_recovering(self, cause: str) -> State: return State.RECOVERING
    def on_incident(self, cause: str) -> None: pass
    def on_recovered(self) -> None: pass
    def on_stuck(self, message: str) -> None: pass
    def enter_match(self) -> None: pass
    def in_match_tick(self, idle_warning: bool) -> None: pass
    def leave_match(self) -> None: pass


def _call(actions, name: str, *args) -> None:
    """Optional GameActions hooks: older/fake action objects may not have them."""
    fn = getattr(actions, name, None)
    if fn is not None:
        fn(*args)


# --------------------------------------------------------------------------- confirmers


class _StreakConfirmer:
    """True signal must hold for >= min_captures AND >= min_seconds; any False resets it."""

    def __init__(self, min_captures: int, min_seconds: float):
        self.min_captures = min_captures
        self.min_seconds = min_seconds
        self._count = 0
        self._since: float | None = None

    def update(self, hit: bool, now: float) -> bool:
        if not hit:
            self._count = 0
            self._since = None
            return False
        self._count += 1
        if self._since is None:
            self._since = now
        return self._count >= self.min_captures and (now - self._since) >= self.min_seconds

    def reset(self) -> None:
        self._count = 0
        self._since = None


class _GapConfirmer:
    """True after the signal is seen twice with >= min_gap seconds between the two."""

    def __init__(self, min_gap: float):
        self.min_gap = min_gap
        self._first: float | None = None

    def update(self, hit: bool, now: float) -> bool:
        if not hit:
            return False
        if self._first is None:
            self._first = now
            return False
        if now - self._first >= self.min_gap:
            self._first = None
            return True
        return False

    def reset(self) -> None:
        self._first = None


# --------------------------------------------------------------------------- state machine


@dataclass
class Transition:
    frm: State
    to: State
    cause: str
    ts: float


class StateMachine:
    def __init__(
        self,
        actions: GameActions,
        timeouts: StateTimeouts | None = None,
        on_transition: Callable[[Transition], None] | None = None,
        clock: Callable[[], float] = time.monotonic,
        disconnect_confirm_captures: int = 3,
        disconnect_confirm_seconds: float = 1.5,
        recovery_confirm_gap: float = 5.0,
        mode_select_scroll_attempts: int = 12,
        lobby_click_interval: float = 4.0,
        ffa_click_interval: float = 2.5,
        max_soft_resets: int = 4,
        max_stuck_relaunches: int = 2,
    ):
        self.actions = actions
        self.timeouts = timeouts or StateTimeouts()
        self.on_transition = on_transition
        self.clock = clock
        self.counters = Counters()
        self.state = State.IDLE
        self._entered_at = clock()
        self._pre_pause: State = State.IDLE
        self._lobby_retries = 0
        self._last_play_click: float | None = None
        self.lobby_click_interval = lobby_click_interval
        # "Stuck" bookkeeping: a running client whose screens we just can't
        # recognize is retried in place (soft reset) before ever being
        # relaunched, and relaunched only a few times for that reason before
        # pausing - see _soft_reset(). Both reset on reaching IN_MATCH.
        self.max_soft_resets = max_soft_resets
        self.max_stuck_relaunches = max_stuck_relaunches
        self._soft_resets = 0
        self._stuck_relaunches = 0
        self._recovery_cause = "retry"
        self.stuck_message: str | None = None

        self._disconnect = _StreakConfirmer(disconnect_confirm_captures, disconnect_confirm_seconds)
        self._recovered = _GapConfirmer(recovery_confirm_gap)
        self._respawn = RespawnFlow(actions, clock)
        self._mode_select = ModeSelectSearch(actions, clock, max_attempts=mode_select_scroll_attempts,
                                             click_interval_s=ffa_click_interval)
        self._last_map_vote_click: float | None = None
        self._map_vote_click_interval = ffa_click_interval
        self._last_seen: float = clock()
        self._match_end_click_at: float = 0.0

    # -- plumbing -------------------------------------------------------

    def _since_entry(self, now: float) -> float:
        return now - self._entered_at

    def _go(self, new_state: State, cause: str, now: float) -> None:
        if new_state is self.state:
            return
        t = Transition(self.state, new_state, cause, now)
        log.info("state %s -> %s (%s)", self.state.value, new_state.value, cause)
        if self.state is State.IN_MATCH:
            # Never leave a movement key held down when we stop controlling the character.
            _call(self.actions, "leave_match")
        self.state = new_state
        self._entered_at = now
        if new_state is State.MODE_SELECT:
            self._mode_select.reset()
            self._last_map_vote_click = None
        if new_state is State.DEAD:
            self._respawn.reset()
            self.counters.respawns += 1
        if new_state is State.LOADOUT:
            _call(self.actions, "begin_loadout")
        if new_state is State.LOBBY:
            self._lobby_retries = 0
            self._last_play_click = None
        if new_state is State.IN_MATCH:
            self._soft_resets = 0
            self._stuck_relaunches = 0
            self.stuck_message = None
            # A fresh "confirmed in a match" moment, by any path - a disconnect
            # confirmer left mid-count from a prior incident must not let a
            # single future frame instantly re-trigger recovery, and whatever
            # owns recovery/backoff state gets told the incident is over.
            self._disconnect.reset()
            self.actions.on_recovered()
            _call(self.actions, "enter_match")
        if self.on_transition:
            self.on_transition(t)

    # -- public API -------------------------------------------------------

    def start(self, attach: bool = False) -> None:
        """Begin a session. ``attach=True`` means a Roblox client is already
        running: take it over where it is instead of opening the launch URI -
        opening ``roblox://`` while a client is up makes Roblox leave the
        current server and rejoin, which is exactly the "keeps rejoining" loop.
        """
        if self.state in (State.IDLE, State.STOPPED):
            now = self.clock()
            self._soft_resets = 0
            self._stuck_relaunches = 0
            self.stuck_message = None
            self._last_seen = now
            if attach:
                self._go(State.LOADING, "attached to running Roblox client", now)
            else:
                self.actions.launch()
                self._go(State.LAUNCHING, "user start", now)

    def pause(self) -> None:
        if self.state not in (State.PAUSED, State.STOPPED, State.IDLE):
            self._pre_pause = self.state
            self._go(State.PAUSED, "user pause", self.clock())

    def resume(self) -> None:
        if self.state is State.PAUSED:
            now = self.clock()
            # tick() no-ops the whole time we're paused (see tick()), so the
            # "nothing recognized" clock never advances either - but real
            # wall-clock time keeps passing. Without this, pausing for longer
            # than timeouts.unknown_after (default 45s) means the very next
            # tick after resuming sees now - _last_seen already over the
            # limit and immediately declares the (perfectly fine) screen
            # "stuck", escalating into a soft-reset/relaunch for no reason.
            # _entered_at already gets this treatment via _go(); _last_seen
            # is the one clock _go() doesn't touch, so it needs it here.
            self._last_seen = now
            self._go(self._pre_pause, "user resume", now)

    def stop(self) -> None:
        self._go(State.STOPPED, "user stop", self.clock())

    def force_state(self, state: State, cause: str = "forced") -> None:
        """Escape hatch for Phase 4's recovery flow, GUI actions, etc."""
        self._go(state, cause, self.clock())

    # -- recovery / stuck handling -------------------------------------------------------

    def _enter_recovery(self, cause: str, reason: str, now: float, count: bool = True) -> None:
        """Hard recovery: RecoverySequence closes and relaunches the client."""
        if count:
            self.counters.reconnects += 1
        self._recovery_cause = cause
        self._go(State.RECOVERING, reason, now)

    def _soft_reset(self, what: str, now: float) -> None:
        """The client is running but we never saw ``what`` - most often an
        uncalibrated detector, not a broken game. Escape out of whatever menu
        is open and retry from the lobby; only after ``max_soft_resets`` of
        those relaunch the client, and after ``max_stuck_relaunches`` such
        relaunches pause and say what's missing instead of looping forever.
        """
        self._soft_resets += 1
        if self._soft_resets <= self.max_soft_resets:
            self.actions.press_escape()
            if self.state is State.LOBBY:
                # Re-entering the same state: restart its clock and click Play again.
                self._entered_at = now
                self._lobby_retries = 0
                self._last_play_click = None
                log.info("lobby retry %d/%d (%s)", self._soft_resets, self.max_soft_resets, what)
                if self.on_transition:
                    self.on_transition(Transition(State.LOBBY, State.LOBBY,
                                                  f"retry {self._soft_resets}/{self.max_soft_resets}: {what}", now))
            else:
                self._go(State.LOBBY, f"retry {self._soft_resets}/{self.max_soft_resets}: {what}", now)
            return

        if self._stuck_relaunches < self.max_stuck_relaunches:
            self._stuck_relaunches += 1
            self._soft_resets = 0
            self.actions.on_incident("stuck")
            self._enter_recovery("stuck", f"stuck ({what}) - relaunching "
                                          f"{self._stuck_relaunches}/{self.max_stuck_relaunches}", now)
            return

        self.stuck_message = (
            f"Warden paused: it kept failing at the same step ({what}). This almost always means "
            f"that screen hasn't been calibrated for your monitor yet - open Calibration, capture "
            f"that screen, then press Resume."
        )
        self.actions.on_stuck(self.stuck_message)
        self._soft_resets = 0
        self._stuck_relaunches = 0
        self._pre_pause = State.LOBBY
        self._go(State.PAUSED, f"stuck: {what}", now)

    # -- main entry point -------------------------------------------------------

    def tick(self, signals: Signals, now: float | None = None) -> State:
        now = self.clock() if now is None else now
        if self.state in (State.IDLE, State.PAUSED, State.STOPPED):
            return self.state

        if self._global_interrupt(signals, now):
            return self.state

        handler = getattr(self, f"_handle_{self.state.value.lower()}", None)
        if handler is not None:
            handler(signals, now)
        return self.state

    # -- global interrupts -------------------------------------------------------

    def _global_interrupt(self, s: Signals, now: float) -> bool:
        # Once we're already RECOVERING, these two must not keep re-firing every
        # tick the underlying signal stays True - that would re-trigger the
        # DISCONNECTED->RECOVERING (or roblox_updating) transition forever and
        # the RECOVERING branch below (which actually drives recovery) would
        # never get a turn.
        if s.roblox_updating and self.state is not State.RECOVERING:
            self.actions.on_incident("roblox_updating")
            self._enter_recovery("roblox_updating", "roblox updating", now)
            return True

        if self.state not in (State.RECOVERING, State.DISCONNECTED) and self._disconnect.update(s.disconnect_modal, now):
            self.counters.reconnects += 1
            self.actions.on_incident("disconnect")
            self._go(State.DISCONNECTED, "disconnect modal confirmed", now)
            self._enter_recovery("disconnect", "disconnect", now, count=False)
            return True

        if self.state in _ACTIVE_STATES and not s.process_running:
            self.actions.on_incident("process_gone")
            self._enter_recovery("process_gone", "roblox process gone", now)
            return True

        if self.state is State.IN_MATCH and s.frozen:
            self.actions.on_incident("frozen")
            self._enter_recovery("frozen", "frame frozen", now)
            return True

        if self.state is State.RECOVERING:
            if self._recovered.update(s.health_bar, now):
                self._go(State.IN_MATCH, "recovery confirmed (health bar twice)", now)
                return True
            next_state = self.actions.handle_recovering(self._recovery_cause)
            if next_state is not State.RECOVERING:
                self._go(next_state, "recovery handed off", now)
            return True

        # Any primary signal resets the "nothing detected" clock.
        primary = (s.lobby_play or s.mode_list or s.ffa_tile or s.map_vote or s.health_bar
                   or s.respawn_prompt or s.weapon_picker or s.switch_weapons or s.midgame_join
                   or s.match_end)
        if primary:
            self._last_seen = now
        elif self.state not in _UNKNOWN_EXEMPT and now - self._last_seen >= self.timeouts.unknown_after:
            self.actions.save_unknown_frame()
            self.actions.press_escape()
            self._go(State.UNKNOWN, "nothing recognized for too long", now)
            return True

        if s.midgame_join and self.state not in (State.MIDGAME_JOIN, State.LOADOUT, State.DEAD):
            self._go(State.MIDGAME_JOIN, "mid-game join prompt", now)
            return True

        return False

    # -- per-state handlers -------------------------------------------------------

    def _handle_launching(self, s: Signals, now: float) -> None:
        if s.client_window_exists:
            self._go(State.LOADING, "client window appeared", now)
        elif self._since_entry(now) >= self.timeouts.launching:
            self._enter_recovery("launch_timeout", "launch timeout", now)

    def _handle_loading(self, s: Signals, now: float) -> None:
        if s.health_bar:
            self._go(State.IN_MATCH, "already in a match on load", now)
        elif s.respawn_prompt:
            self._go(State.DEAD, "respawn prompt visible on load", now)
        elif s.weapon_picker:
            self._go(State.LOADOUT, "weapon picker visible on load", now)
        elif s.mode_list or s.ffa_tile:
            self._go(State.MODE_SELECT, "mode list visible on load", now)
        elif s.lobby_play:
            self._go(State.LOBBY, "lobby visible", now)
        elif self._since_entry(now) >= self.timeouts.loading:
            if s.process_running and s.client_window_exists:
                # The game is up; we just don't recognize its screen. Don't
                # kill a healthy client for that - try the lobby route.
                self._soft_reset("lobby Play button (lobby_play) never recognized", now)
            else:
                self._enter_recovery("loading_timeout", "loading timeout", now)

    def _handle_lobby(self, s: Signals, now: float) -> None:
        if s.mode_list or s.ffa_tile:
            self._go(State.MODE_SELECT, "mode list opened", now)
            return
        if s.weapon_picker:
            self._go(State.LOADOUT, "weapon picker appeared", now)
            return
        if s.respawn_prompt:
            self._go(State.DEAD, "respawn prompt appeared", now)
            return
        if s.health_bar:
            self._go(State.IN_MATCH, "already in a match", now)
            return
        if self._since_entry(now) >= self.timeouts.lobby:
            self._soft_reset("mode list (mode_list / ffa_tile) never opened after clicking Play", now)
            return
        # Click Play on entry, then again every lobby_click_interval while the
        # mode list still hasn't opened (a single click is easily lost while
        # the lobby is still loading in).
        if self._last_play_click is None or now - self._last_play_click >= self.lobby_click_interval:
            self.actions.click_play()
            self._last_play_click = now

    def _handle_mode_select(self, s: Signals, now: float) -> None:
        # Early abort: these mean we're already past mode select.
        if s.weapon_picker:
            self._go(State.LOADOUT, "weapon picker appeared (early abort)", now)
            return
        if s.respawn_prompt:
            self._go(State.DEAD, "respawn prompt appeared (early abort)", now)
            return
        if s.health_bar:
            self._go(State.IN_MATCH, "health bar appeared (early abort)", now)
            return
        if s.map_vote:
            # After FFA is picked, RIVALS shows a map-vote screen (countdown
            # timer + map tiles) that needs its own click before the match
            # actually starts. Without this, nothing happened here at all -
            # Warden just sat idle until the mode_select timeout gave up and
            # soft-reset (escape back to the lobby), which looked like it had
            # quit and needed a hand to get back in. Clicks "Random" (always
            # one of the options, unlike the other rotating map names).
            if (self._last_map_vote_click is None
                    or now - self._last_map_vote_click >= self._map_vote_click_interval):
                self.actions.click_map_vote()
                self._last_map_vote_click = now
            return
        if self._since_entry(now) >= self.timeouts.mode_select:
            what = ("clicked FFA but the match never started (no health_bar / weapon_picker)"
                    if self._mode_select.clicks else "FFA tile (ffa_tile) never found in the mode list")
            self._soft_reset(what, now)
            return
        self._mode_select.tick(s.ffa_tile, now)

    def _handle_midgame_join(self, s: Signals, now: float) -> None:
        if not s.midgame_join:
            self._go(State.MODE_SELECT, "join prompt resolved", now)
            return
        if self._since_entry(now) >= self.timeouts.midgame_join:
            self._go(State.MODE_SELECT, "midgame join timeout", now)
            return
        self.actions.click_midgame_join()

    def _handle_loadout(self, s: Signals, now: float) -> None:
        if s.respawn_prompt:
            self._go(State.DEAD, "died mid-loadout transaction", now)
            return
        if not s.weapon_picker and self._since_entry(now) > 1.0:
            # Picker vanished on its own (e.g. opened by mistake) - fall through.
            self._go(State.IN_MATCH if s.health_bar else State.MODE_SELECT, "picker closed", now)
            return
        if self._since_entry(now) >= self.timeouts.loadout:
            self.actions.on_incident("loadout_timeout")
            self._go(State.IN_MATCH if s.health_bar else State.MODE_SELECT, "loadout timeout", now)
            return
        if self.actions.run_loadout():
            self._go(State.IN_MATCH, "loadout committed", now)

    def _handle_in_match(self, s: Signals, now: float) -> None:
        if s.respawn_prompt:
            self._go(State.DEAD, "died", now)
            return
        if s.weapon_picker:
            self._go(State.LOADOUT, "weapon picker opened", now)
            return
        if s.match_end:
            self._go(State.MATCH_END, "match ended", now)
            return
        if not s.health_bar:
            # Health bar missing but nothing else fired; wait rather than
            # thrashing state - the unknown-screen timer covers the stuck case.
            return
        # Alive in a match: move / shoot / abilities / anti-idle (section 6.7).
        _call(self.actions, "in_match_tick", s.idle_warning)

    def _handle_dead(self, s: Signals, now: float) -> None:
        if self._since_entry(now) >= self.timeouts.dead:
            self._go(State.UNKNOWN, "stuck on respawn prompt", now)
            return
        done = self._respawn.tick(s.respawn_prompt, s.switch_weapons, s.health_bar, now)
        if done:
            self._go(State.IN_MATCH, "respawn sequence complete", now)

    def _handle_match_end(self, s: Signals, now: float) -> None:
        if s.mode_list:
            self.counters.re_queues += 1
            self._go(State.MODE_SELECT, "back at mode select", now)
            return
        if s.lobby_play:
            self._go(State.LOBBY, "back at lobby", now)
            return
        if self._since_entry(now) >= self.timeouts.match_end:
            self._soft_reset("match-end screen never closed", now)
            return
        if now - self._match_end_click_at >= 2.0:
            self.actions.click_match_continue()
            self._match_end_click_at = now

    def _handle_unknown(self, s: Signals, now: float) -> None:
        self.actions.on_incident("unknown_screen")
        if s.process_running and s.client_window_exists:
            # Escape was already pressed on the way in; retry from the lobby
            # rather than closing a client that's still running fine.
            self._soft_reset("screen not recognized for too long", now)
        else:
            self._enter_recovery("unknown_screen", "unknown screen handled", now)
