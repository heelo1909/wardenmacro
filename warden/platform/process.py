"""Roblox process control and launch targets."""

from __future__ import annotations

import logging
import os
import time
import webbrowser
from collections.abc import Callable

from warden.config.schema import LaunchMode, Preset
from warden.platform.window import CLIENT_PROCESS

log = logging.getLogger(__name__)


def launch_uri(preset: Preset) -> str:
    launch = preset.launch
    if launch.mode is LaunchMode.share_link:
        code = launch.share_code.strip()
        return f"roblox://navigation/share_links?code={code}&type=Server"
    return f"roblox://experiences/start?placeId={launch.place_id}"


def browser_url(preset: Preset) -> str:
    return f"https://www.roblox.com/games/{preset.launch.place_id}"


class Launcher:
    """Opens launch targets. ``opener`` is swappable for tests."""

    def __init__(self, opener: Callable[[str], None] | None = None,
                 browser: Callable[[str], None] | None = None):
        self._open = opener or _startfile
        self._browser = browser or (lambda url: webbrowser.open(url, new=2))

    def open_client(self, preset: Preset) -> str:
        uri = launch_uri(preset)
        self._open(uri)
        return uri

    def open_browser(self, preset: Preset) -> str:
        url = browser_url(preset)
        self._browser(url)
        return url


def _startfile(uri: str) -> None:
    os.startfile(uri)  # type: ignore[attr-defined]  # Windows only


class RobloxProcess:
    """Find, gracefully close, and if needed terminate the Roblox client."""

    def __init__(self, send_close: Callable[[int], None] | None = None, sleep: Callable[[float], None] = time.sleep):
        self._send_close = send_close
        self._sleep = sleep

    @staticmethod
    def pids() -> list[int]:
        import psutil

        out = []
        for proc in psutil.process_iter(["name"]):
            try:
                if (proc.info["name"] or "").lower() == CLIENT_PROCESS:
                    out.append(proc.pid)
            except Exception:
                continue
        return out

    def is_running(self) -> bool:
        return bool(self.pids())

    def close(self, hwnd: int | None, grace_s: float = 10.0) -> bool:
        """WM_CLOSE, wait ``grace_s``, then terminate. True when no client remains."""
        import psutil

        if hwnd and self._send_close:
            try:
                self._send_close(hwnd)
            except Exception:
                log.exception("WM_CLOSE failed")
        waited = 0.0
        while waited < grace_s and self.is_running():
            self._sleep(0.5)
            waited += 0.5
        for pid in self.pids():
            try:
                psutil.Process(pid).terminate()
            except Exception:
                pass
        for _ in range(20):
            if not self.is_running():
                return True
            self._sleep(0.25)
        for pid in self.pids():
            try:
                psutil.Process(pid).kill()
            except Exception:
                pass
        self._sleep(0.5)
        return not self.is_running()
