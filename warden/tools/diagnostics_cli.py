"""``python -m warden.tools.diagnostics_cli`` - prints window/DPI/capture/OCR info.

Safe to run with Roblox closed; every section degrades to "not found"/"n/a"
instead of crashing, since this is the first thing a confused user runs.
"""

from __future__ import annotations

import sys
import time

from warden.config.loader import load_all
from warden.geometry import Rect
from warden.platform import dpi
from warden.vision import ocr


def _section(title: str) -> None:
    print(f"\n== {title} ==")


def run() -> int:
    print("Warden diagnostics")

    _section("DPI awareness")
    awareness = dpi.ensure_dpi_awareness()
    print(f"process awareness: {awareness}")
    for i, mon in enumerate(dpi.monitors()):
        tag = " (primary)" if mon.primary else ""
        print(f"  monitor {i}{tag}: {mon.rect.width}x{mon.rect.height} @ {int(mon.scale * 100)}%")

    _section("Roblox window")
    if sys.platform != "win32":
        print("not on Windows - window detection unavailable")
        window = None
        backend = None
    else:
        from warden.platform.window import Win32Windows, pick_client, pick_updater

        backend = Win32Windows()
        windows = backend.list_windows()
        window = pick_client(windows)
        updater = pick_updater(windows)
        if window:
            print(f"found: hwnd={window.hwnd} class={window.class_name!r} "
                  f"client={window.client.width}x{window.client.height} minimized={window.minimized}")
        else:
            print("not found (is RobloxPlayerBeta.exe running with a visible window?)")
        if updater:
            print(f"NOTE: Roblox updater window is open: {updater.title!r}")

    _section("Focus test")
    if window and backend:
        from warden.platform.window import FocusGate

        gate = FocusGate(backend)
        gate.set_target(window.hwnd)
        print(f"currently foreground: {gate.is_focused()}")
    else:
        print("skipped (no client window)")

    _section("Capture")
    if window and window.client.width and window.client.height:
        from warden.vision.capture import MssCapturer, measure_fps

        rect = Rect(window.client.left, window.client.top, window.client.width, window.client.height)
        fps = measure_fps(MssCapturer(), rect, seconds=0.5)
        print(f"client-area capture: {fps:.1f} fps")
    else:
        print("skipped (no client window)")

    _section("OCR")
    print(f"tesseract available: {ocr.available()}")

    _section("Config")
    try:
        loaded = load_all()
        print(f"config OK: {loaded.app_path}")
        print(f"active preset: {loaded.preset_id} ({loaded.preset.contract.target_hours}h target)")
        print(f"detectors configured: {len(loaded.app.detectors)}")
    except Exception as exc:
        print(f"config problem: {exc}")

    return 0


def main() -> int:
    start = time.perf_counter()
    code = run()
    print(f"\n(done in {time.perf_counter() - start:.2f}s)")
    return code


if __name__ == "__main__":
    sys.exit(main())
