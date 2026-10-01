from warden.core.state_machine import NullActions, Signals, State, StateMachine
from warden.tools.recorder import save_frame
from warden.tools.replay import ManualClock, replay, replay_recording, signals_from_detections
from warden.vision.detectors import Detection


def test_replay_runs_frames_through_a_fresh_machine():
    frames = [Signals(client_window_exists=True), Signals(lobby_play=True)]
    result = replay(frames, NullActions())
    assert result.final_state is State.LOBBY
    assert [t.to for t in result.transitions] == [State.LAUNCHING, State.LOADING, State.LOBBY]


def test_replay_path_lists_every_state_visited():
    frames = [Signals(client_window_exists=True), Signals(lobby_play=True)]
    result = replay(frames, NullActions())
    assert result.path() == ["IDLE", "LAUNCHING", "LOADING", "LOBBY"]


def test_replay_accepts_a_preexisting_state_machine():
    machine = StateMachine(NullActions(), clock=ManualClock(0.0))
    result = replay([Signals(client_window_exists=True)], NullActions(), sm=machine)
    assert result.final_state is State.LOADING
    assert machine.state is State.LOADING  # it's the same machine, mutated in place


def test_signals_from_detections_reads_the_confirmed_flag():
    detections = {
        "health_bar": {"confirmed": True, "hit": True},
        "respawn_prompt": {"confirmed": False, "hit": True},  # seen but not yet confirmed
    }
    signals = signals_from_detections(detections)
    assert signals.health_bar is True
    assert signals.respawn_prompt is False
    assert signals.lobby_play is False  # absent entirely -> default False


def test_replay_recording_round_trips_through_saved_frames(tmp_path):
    import numpy as np

    frame = np.zeros((4, 4, 3), dtype="uint8")
    lobby = {"lobby_play": Detection("lobby_play", True, True, 0.9)}
    mode_list = {"mode_list": Detection("mode_list", True, True, 0.9)}
    # LAUNCHING -> LOADING consumes frame 0 (client window already "exists" by
    # default); frame 1's lobby_play then takes LOADING -> LOBBY; frame 2's
    # mode_list is what finally moves LOBBY -> MODE_SELECT.
    save_frame(tmp_path, 0, frame, lobby)
    save_frame(tmp_path, 1, frame, lobby)
    save_frame(tmp_path, 2, frame, mode_list)
    result = replay_recording(tmp_path, NullActions())
    assert result.final_state is State.MODE_SELECT
