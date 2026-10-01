import numpy as np

from warden.tools.recorder import Recorder, load_recording, save_frame
from warden.vision.detectors import Detection


def test_save_frame_and_load_round_trip(tmp_path):
    frame = np.full((20, 30, 3), 7, dtype=np.uint8)
    detections = {"health_bar": Detection("health_bar", True, True, 0.9, (0.1, 0.1, 0.2, 0.2), None, 2)}
    png = save_frame(tmp_path, 0, frame, detections, ts=123.0)
    assert png.exists()
    loaded = load_recording(tmp_path)
    assert len(loaded) == 1
    assert loaded[0]["ts"] == 123.0
    assert loaded[0]["detections"]["health_bar"]["confirmed"] is True
    img = loaded[0]["load_image"]()
    assert img.shape == (20, 30, 3)


def test_load_recording_is_index_ordered(tmp_path):
    frame = np.zeros((4, 4, 3), dtype=np.uint8)
    for i in (2, 0, 1):
        save_frame(tmp_path, i, frame, {})
    assert [f["index"] for f in load_recording(tmp_path)] == [0, 1, 2]


def test_recorder_tick_once_calls_capture_and_detect_and_increments_count():
    calls = {"capture": 0, "detect": 0}

    def capture():
        calls["capture"] += 1
        return np.zeros((4, 4, 3), dtype=np.uint8)

    def detect(frame):
        calls["detect"] += 1
        return {}

    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        rec = Recorder(capture, detect, out_dir=tmp, fps=10)
        rec.tick_once()
        rec.tick_once()
        assert calls == {"capture": 2, "detect": 2}
        assert rec.count == 2
        assert len(list(rec.out_dir.glob("*.png"))) == 2


def test_recorder_survives_capture_failure():
    def capture():
        raise RuntimeError("no window")

    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        rec = Recorder(capture, lambda f: {}, out_dir=tmp, fps=10)
        assert rec.tick_once() is None
        assert rec.count == 0


def test_recorder_start_stop_runs_in_background():
    import tempfile
    import time

    def capture():
        return np.zeros((4, 4, 3), dtype=np.uint8)

    with tempfile.TemporaryDirectory() as tmp:
        rec = Recorder(capture, lambda f: {}, out_dir=tmp, fps=20)
        rec.start()
        time.sleep(0.3)
        rec.stop()
        assert rec.count >= 2
