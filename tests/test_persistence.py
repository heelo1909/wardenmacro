from warden.core.persistence import (
    Counters,
    PersistenceManager,
    load_session_summaries,
    load_state,
    save_state,
)


def test_load_missing_file_returns_default(tmp_path):
    state = load_state(tmp_path / "nope.json")
    assert state.contracts == {} and state.all_time.respawns == 0


def test_load_corrupt_json_returns_default(tmp_path, caplog):
    path = tmp_path / "state.json"
    path.write_text("{not valid json", encoding="utf-8")
    state = load_state(path)
    assert state.contracts == {}


def test_save_load_round_trip(tmp_path):
    path = tmp_path / "state.json"
    mgr = PersistenceManager(path, tmp_path / "sessions")
    mgr.start_session("glass_wrap", "Glass Wrap", 24.0)
    mgr.maybe_flush(100.0, Counters(respawns=2), force=True)
    reloaded = load_state(path)
    assert reloaded.contracts["glass_wrap"].cumulative_seconds == 100.0
    assert reloaded.all_time.respawns == 2
    assert reloaded.last_session_incomplete is True


def test_atomic_save_leaves_no_tmp_files(tmp_path):
    path = tmp_path / "state.json"
    mgr = PersistenceManager(path, tmp_path / "sessions")
    mgr.start_session("p", "P", 1.0)
    mgr.maybe_flush(1.0, Counters(), force=True)
    assert not list(tmp_path.glob(".*tmp*"))


def test_flush_applies_delta_not_absolute(tmp_path):
    mgr = PersistenceManager(tmp_path / "state.json", tmp_path / "sessions")
    mgr.start_session("p", "P", 24.0)
    mgr.maybe_flush(60.0, Counters(respawns=1), force=True)
    mgr.maybe_flush(150.0, Counters(respawns=3), force=True)  # +90s, +2 respawns since last flush
    assert mgr.state.contracts["p"].cumulative_seconds == 150.0
    assert mgr.state.all_time.respawns == 3  # not 1+3=4 (would be double counting)


def test_maybe_flush_respects_interval_unless_forced(tmp_path):
    t = [0.0]
    mgr = PersistenceManager(tmp_path / "state.json", tmp_path / "sessions",
                              save_interval_s=30.0, clock=lambda: t[0])
    mgr.start_session("p", "P", 24.0)
    t[0] = 10.0
    assert mgr.maybe_flush(10.0, Counters()) is False
    t[0] = 31.0
    assert mgr.maybe_flush(31.0, Counters()) is True


def test_end_session_clears_incomplete_flag_and_writes_summary(tmp_path):
    sessions_dir = tmp_path / "sessions"
    mgr = PersistenceManager(tmp_path / "state.json", sessions_dir, wall_clock=lambda: 1000.0)
    mgr.start_session("glass_wrap", "Glass Wrap", 24.0)
    path = mgr.end_session(3600.0, Counters(respawns=5), ["disconnect at 00:01:00"])
    assert path.exists()
    reloaded = load_state(tmp_path / "state.json")
    assert reloaded.last_session_incomplete is False
    summaries = load_session_summaries(sessions_dir)
    assert len(summaries) == 1
    assert summaries[0]["counters"]["respawns"] == 5
    assert summaries[0]["incidents"] == ["disconnect at 00:01:00"]


def test_crash_simulation_leaves_incomplete_flag_set(tmp_path):
    path = tmp_path / "state.json"
    mgr = PersistenceManager(path, tmp_path / "sessions")
    mgr.start_session("p", "P", 24.0)
    mgr.maybe_flush(500.0, Counters(respawns=1), force=True)
    # "crash": no end_session() ever called - a fresh load must still show incomplete=True.
    reloaded = load_state(path)
    assert reloaded.last_session_incomplete is True
    assert reloaded.last_session_preset_id == "p"
    assert reloaded.contracts["p"].cumulative_seconds == 500.0  # progress up to the last flush survives


def test_separate_presets_tracked_independently(tmp_path):
    mgr = PersistenceManager(tmp_path / "state.json", tmp_path / "sessions")
    mgr.start_session("glass_wrap", "Glass Wrap", 24.0)
    mgr.end_session(3600.0, Counters(), [])
    mgr.start_session("random", "Random", 10.0)
    mgr.end_session(1800.0, Counters(), [])
    assert mgr.state.contracts["glass_wrap"].cumulative_seconds == 3600.0
    assert mgr.state.contracts["random"].cumulative_seconds == 1800.0


def test_contract_progress_accumulates_across_multiple_sessions_same_preset(tmp_path):
    mgr = PersistenceManager(tmp_path / "state.json", tmp_path / "sessions")
    mgr.start_session("glass_wrap", "Glass Wrap", 24.0)
    mgr.end_session(3600.0, Counters(), [])
    mgr.start_session("glass_wrap", "Glass Wrap", 24.0)
    mgr.end_session(1800.0, Counters(), [])
    entry = mgr.state.contracts["glass_wrap"]
    assert entry.cumulative_seconds == 5400.0
    assert abs(entry.cumulative_hours - 1.5) < 1e-9
    assert mgr.state.all_time.total_sessions == 2


def test_contract_progress_fraction_clamped_at_one():
    from warden.core.persistence import ContractProgress

    entry = ContractProgress(label="X", target_hours=1.0, cumulative_seconds=7200.0)
    assert entry.fraction == 1.0
