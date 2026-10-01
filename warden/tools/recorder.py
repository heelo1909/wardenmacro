"""Frame recorder: capture + detector output, saved for offline replay (section 8.7).

Each frame becomes ``NNNNNN.png`` plus a sidecar ``NNNNNN.json`` with its
timestamp and every detector's result, so ``tools/replay.py`` (Phase 2) can
feed an identical sequence through the state machine with no Roblox running.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path

import cv2
import numpy as np

from warden import paths
from warden.vision.detectors import Detection

log = logging.getLogger(__name__)

DetectFn = Callable[[np.ndarray], dict[str, Detection]]


def new_recording_dir(base: Path | None = None) -> Path:
    base = base or paths.data_dir("recordings")
    out = Path(base) / time.strftime("%Y%m%d_%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    return out


def save_frame(out_dir: Path, index: int, frame: np.ndarray, detections: dict[str, Detection],
               ts: float | None = None) -> Path:
    """Write one frame + sidecar JSON; returns the PNG path. Pure/sync, used directly by tests."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{index:06d}"
    png_path = out_dir / f"{stem}.png"
    cv2.imwrite(str(png_path), frame)
    meta = {
        "ts": ts if ts is not None else time.time(),
        "index": index,
        "detections": {name: asdict(d) for name, d in detections.items()},
    }
    (out_dir / f"{stem}.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return png_path


def load_recording(directory: Path) -> list[dict]:
    """Every frame's metadata (+ a loader for its image), in index order."""
    directory = Path(directory)
    frames = []
    for meta_path in sorted(directory.glob("*.json")):
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        png_path = meta_path.with_suffix(".png")
        meta["load_image"] = (lambda p=png_path: cv2.imread(str(p)))
        meta["image_path"] = png_path
        frames.append(meta)
    return frames


class Recorder:
    """Background loop: capture -> detect -> save, at a fixed dev-tool rate (not in-game timing)."""

    def __init__(self, capture: Callable[[], np.ndarray], detect: DetectFn, out_dir: Path | None = None,
                 fps: float = 2.0, clock: Callable[[], float] = time.time):
        self.capture = capture
        self.detect = detect
        self.out_dir = Path(out_dir) if out_dir else new_recording_dir()
        self.interval = 1.0 / fps if fps > 0 else 0.5
        self.clock = clock
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.count = 0

    def tick_once(self) -> Path | None:
        try:
            frame = self.capture()
        except Exception:
            log.exception("recorder: capture failed")
            return None
        detections = self.detect(frame)
        path = save_frame(self.out_dir, self.count, frame, detections, ts=self.clock())
        self.count += 1
        return path

    def start(self) -> None:
        def loop():
            while not self._stop.wait(self.interval):
                self.tick_once()

        self._stop.clear()
        self._thread = threading.Thread(target=loop, name="warden-recorder", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
