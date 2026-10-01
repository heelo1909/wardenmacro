import shutil

from warden.config import load_all
from warden.core.events import EventBus
from warden.core.persistence import load_state
from warden.core.state_machine import State
from warden.core.tick import TickLoop
from warden.vision.detectors import Detection


def make_loop(bundled_config, tmp_path, monkeypatch, ocr_verify=True):
    work = tmp_path / "config"
    shutil.copytree(bundled_config, work)
    monkeypatch.setenv("WARDEN_HOME", str(tmp_path / "home"))
    loaded = load_all(work / "default.yaml")
    loaded.app.observe_only = True
    loaded.app.estimate.ocr_verify = ocr_verify
    return TickLoop(loaded.app, loaded.preset, EventBus())


def test_ocr_text_in_lobby_corrects_banked_hours(bundled_config, tmp_path, monkeypatch):
    loop = make_loop(bundled_config, tmp_path, monkeypatch)
    loop.start()
    loop.stop()  # just to create an initial session entry; re-open for the real test below
    loop._in_match_seconds = 500.0
    loop._session_active = True
    loop.persistence.start_session(loop.app.active_preset, loop.preset.contract.label,
                                    loop.preset.contract.target_hours)

    detections = {"contract_progress": Detection("contract_progress", False, False, 0.0, None,
                                                 "12h 30m / 1d 0h 0m", 0)}
    loop._maybe_verify_contract(detections, State.LOBBY)

    assert loop._in_match_seconds == 0.0  # reset so the next flush doesn't double count
    reloaded = load_state(loop.persistence.state_path)
    assert reloaded.contracts[loop.app.active_preset].cumulative_seconds == (12 + 30 / 60) * 3600.0


def test_ocr_verification_skipped_outside_lobby(bundled_config, tmp_path, monkeypatch):
    loop = make_loop(bundled_config, tmp_path, monkeypatch)
    loop._session_active = True
    loop._in_match_seconds = 500.0
    detections = {"contract_progress": Detection("contract_progress", False, False, 0.0, None, "12h 30m", 0)}
    loop._maybe_verify_contract(detections, State.IN_MATCH)
    assert loop._in_match_seconds == 500.0  # untouched


def test_ocr_verification_skipped_when_disabled_in_config(bundled_config, tmp_path, monkeypatch):
    loop = make_loop(bundled_config, tmp_path, monkeypatch, ocr_verify=False)
    loop._session_active = True
    loop._in_match_seconds = 500.0
    detections = {"contract_progress": Detection("contract_progress", False, False, 0.0, None, "12h 30m", 0)}
    loop._maybe_verify_contract(detections, State.LOBBY)
    assert loop._in_match_seconds == 500.0


def test_ocr_verification_ignores_unparseable_text(bundled_config, tmp_path, monkeypatch):
    loop = make_loop(bundled_config, tmp_path, monkeypatch)
    loop._session_active = True
    loop._in_match_seconds = 500.0
    detections = {"contract_progress": Detection("contract_progress", False, False, 0.0, None, "garbage", 0)}
    loop._maybe_verify_contract(detections, State.LOBBY)
    assert loop._in_match_seconds == 500.0


def test_ocr_verification_handles_missing_detection(bundled_config, tmp_path, monkeypatch):
    loop = make_loop(bundled_config, tmp_path, monkeypatch)
    loop._session_active = True
    loop._maybe_verify_contract({}, State.LOBBY)  # must not raise
