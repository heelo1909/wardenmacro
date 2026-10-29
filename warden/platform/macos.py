"""macOS-only startup wiring and first-run defaults.

Everything here is a no-op on Windows: ``configure`` returns immediately and
``mac_first_run_defaults`` is only called when seeding config on a Mac.
"""

from __future__ import annotations

import logging
import sys

log = logging.getLogger(__name__)

# Mac keyboards need Fn for F6-F9 (they default to brightness/media keys), so
# a fresh Mac install starts with letter combos instead. Still rebindable on
# the Settings page. Ctrl (not Cmd/Option): Cmd+letter is taken by macOS and
# Option+letter types special characters, which global hotkeys can mis-read.
MAC_HOTKEYS = {
    "start": "ctrl+shift+s",
    "pause": "ctrl+shift+p",
    "stop": "ctrl+shift+x",
    "screenshot": "ctrl+shift+k",
}


def is_mac(platform: str | None = None) -> bool:
    return (platform or sys.platform) == "darwin"


def mac_first_run_defaults(data: dict) -> dict:
    """Adjust a freshly seeded config.yaml (as a dict) for a Mac. Pure; returns ``data``.

    - Mac-friendly hotkeys (only where the Windows F-key defaults are still set).
    - Input: Quartz first, pynput fallback (SendInput/pydirectinput are Windows-only).
    - OCR off: Tesseract can't be installed without Terminal.
    """
    hotkeys = data.setdefault("hotkeys", {}) or {}
    data["hotkeys"] = hotkeys
    windows_defaults = {"start": "F6", "pause": "F7", "stop": "F8", "screenshot": "F9"}
    for name, combo in MAC_HOTKEYS.items():
        if str(hotkeys.get(name, windows_defaults[name])).upper() == windows_defaults[name]:
            hotkeys[name] = combo
    inp = data.setdefault("input", {}) or {}
    data["input"] = inp
    inp["methods"] = ["quartz", "pynput"]
    est = data.setdefault("estimate", {}) or {}
    data["estimate"] = est
    est["ocr_verify"] = False
    mac = data.setdefault("mac", {}) or {}
    data["mac"] = mac
    mac.setdefault("ocr", False)
    return data


def configure(app_config, platform: str | None = None) -> None:
    """Apply the ``mac:`` config section to the platform modules. Call once at startup."""
    if not is_mac(platform):
        return
    from warden.platform import window_mac
    from warden.vision import ocr

    window_mac.TITLE_BAR_PT = int(app_config.mac.title_bar_pt)
    ocr.set_enabled(bool(app_config.mac.ocr))
    log.info("macOS: title bar %dpt, OCR %s", window_mac.TITLE_BAR_PT, "on" if app_config.mac.ocr else "off")
