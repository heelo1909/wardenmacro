"""Offline replay: run a recorded or synthetic signal sequence through the
state machine with no Roblox anywhere nearby (HANDOFF sections 8.7 / 11).

Two input shapes are supported:

* A list of ``Signals`` built by hand in a test (the common case for new
  regression fixtures).
* A recording directory from ``tools/recorder.py`` - its sidecar JSON
  ``detections`` map is converted to ``Signals`` via ``signals_from_detections``.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from warden.core.state_machine import GameActions, Signals, State, StateMachine, Transition
from warden.tools.recorder import load_recording


def signals_from_detections(detections: dict, process_running: bool = True,
                             client_window_exists: bool = True) -> Signals:
    """Recorder sidecar JSON's ``detections`` (name -> Detection dict) -> Signals."""
    hit = {name: bool(d.get("confirmed")) for name, d in detections.items()}
    return Signals(
        lobby_play=hit.get("lobby_play", False),
        mode_list=hit.get("mode_list", False),
        ffa_tile=hit.get("ffa_tile", False),
        map_vote=hit.get("map_vote", False),
        health_bar=hit.get("health_bar", False),
        respawn_prompt=hit.get("respawn_prompt", False),
        weapon_picker=hit.get("weapon_picker", False),
        switch_weapons=hit.get("switch_weapons", False),
        midgame_join=hit.get("midgame_join", False),
        match_end=hit.get("match_end", False),
        disconnect_modal=hit.get("disconnect_modal", False),
        roblox_updating=hit.get("roblox_updating", False),
        frozen=hit.get("frozen", False),
        idle_warning=hit.get("idle_warning", False),
        process_running=process_running,
        client_window_exists=client_window_exists,
    )


@dataclass
class ReplayResult:
    transitions: list[Transition]
    final_state: State

    def path(self) -> list[str]:
        return [self.final_state.value] if not self.transitions else (
            [self.transitions[0].frm.value] + [t.to.value for t in self.transitions]
        )


class ManualClock:
    """A controllable clock: advance it yourself, StateMachine just reads ``.t``."""

    def __init__(self, t: float = 0.0):
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> float:
        self.t += dt
        return self.t


def replay(
    frames: Iterable[Signals],
    actions: GameActions,
    sm: StateMachine | None = None,
    tick_s: float = 0.25,
    start: bool = True,
) -> ReplayResult:
    """Feed ``frames`` through a state machine ``tick_s`` apart.

    Builds its own ``ManualClock``-driven ``StateMachine`` when ``sm`` is None;
    if ``sm`` is supplied, its own clock is used as-is (and its existing
    ``on_transition``, if any, is chained rather than replaced).
    """
    transitions: list[Transition] = []
    clock = ManualClock(0.0)
    if sm is None:
        sm = StateMachine(actions, on_transition=transitions.append, clock=clock)
    else:
        previous = sm.on_transition

        def _chained(t: Transition) -> None:
            transitions.append(t)
            if previous:
                previous(t)

        sm.on_transition = _chained
        clock = sm.clock if isinstance(sm.clock, ManualClock) else None

    if start:
        sm.start()
    for signals in frames:
        if clock is not None:
            clock.advance(tick_s)
            sm.tick(signals)
        else:
            sm.tick(signals)  # caller's own (likely real-time) clock drives timing
    return ReplayResult(transitions, sm.state)


def replay_recording(directory: Path, actions: GameActions, sm: StateMachine | None = None) -> ReplayResult:
    frames = load_recording(directory)
    signals = [signals_from_detections(f["detections"]) for f in frames]
    return replay(signals, actions, sm)
