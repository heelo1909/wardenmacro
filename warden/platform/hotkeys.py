"""Global hotkeys (work while Roblox has focus) via pynput.

Windows uses pynput's ``GlobalHotKeys`` exactly as before. macOS uses a
small key-code matcher instead (``ComboMatcher``): with Ctrl held, macOS
reports letters as control characters, which ``GlobalHotKeys`` compares by
character and can miss. Matching on physical key codes avoids that. Global
hotkeys on macOS need the Input Monitoring permission.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable

log = logging.getLogger(__name__)

MODIFIERS = ("ctrl", "shift", "alt", "cmd")
_MOD_ALIASES = {"control": "ctrl", "option": "alt", "opt": "alt", "command": "cmd", "super": "cmd", "win": "cmd"}


def to_pynput(combo: str) -> str:
    """'F6' -> '<f6>', 'ctrl+shift+s' -> '<ctrl>+<shift>+s'."""
    parts = []
    for part in combo.lower().replace(" ", "").split("+"):
        if len(part) == 1:
            parts.append(part)
        else:
            parts.append(f"<{part}>")
    return "+".join(parts)


def parse_combo(combo: str) -> tuple[frozenset[str], str]:
    """'Ctrl+Shift+S' -> ({'ctrl', 'shift'}, 'S'); 'F8' -> (set(), 'F8')."""
    mods: set[str] = set()
    key = ""
    for part in combo.replace(" ", "").split("+"):
        if not part:
            continue
        low = _MOD_ALIASES.get(part.lower(), part.lower())
        if low in MODIFIERS:
            mods.add(low)
        else:
            key = part.upper()
    if not key:
        raise ValueError(f"hotkey '{combo}' has no main key")
    return frozenset(mods), key


class ComboMatcher:
    """Pure press/release tracker: fires a callback when exactly its modifiers
    are held and its main key goes down. Key names are Warden's own
    ('S', 'F8', 'ctrl', ...), so this is testable without any OS hooks."""

    def __init__(self, bindings: dict[str, Callable[[], None]]):
        self._combos = [(parse_combo(c), cb) for c, cb in bindings.items() if c]
        self._mods: set[str] = set()

    def press(self, name: str) -> bool:
        if name in MODIFIERS:
            self._mods.add(name)
            return False
        fired = False
        for (mods, key), cb in self._combos:
            if key == name.upper() and mods == self._mods:
                cb()
                fired = True
        return fired

    def release(self, name: str) -> None:
        if name in MODIFIERS:
            self._mods.discard(name)


def _mac_key_name(key) -> str | None:
    """pynput key object -> Warden key name, using the physical key code."""
    from warden.platform.input_mac import MAC_KEYCODES

    name = getattr(key, "name", None)  # pynput.keyboard.Key members
    if name:
        base = name.split("_")[0]  # ctrl_l -> ctrl, alt_r -> alt, cmd_l -> cmd
        if base in MODIFIERS:
            return base
        if base.startswith("f") and base[1:].isdigit():
            return base.upper()
    vk = getattr(key, "vk", None)
    if vk is None:
        value = getattr(key, "value", None)
        vk = getattr(value, "vk", None)
    if vk is None:
        return None
    for warden_name, code in MAC_KEYCODES.items():
        if code == vk:
            return warden_name
    return None


class Hotkeys:
    def __init__(self, bindings: dict[str, Callable[[], None]], platform: str | None = None):
        """``bindings`` maps a combo like 'F8' to a callback."""
        self.bindings = bindings
        self.platform = platform or sys.platform
        self._listener = None

    def start(self) -> bool:
        try:
            from pynput import keyboard
        except Exception as exc:
            log.warning("global hotkeys unavailable: %s", exc)
            return False
        if self.platform == "darwin":
            return self._start_mac(keyboard)
        mapping = {to_pynput(combo): self._safe(cb) for combo, cb in self.bindings.items() if combo}
        self._listener = keyboard.GlobalHotKeys(mapping)
        self._listener.daemon = True
        self._listener.start()
        return True

    def _start_mac(self, keyboard) -> bool:
        try:
            matcher = ComboMatcher({c: self._safe(cb) for c, cb in self.bindings.items() if c})
        except ValueError as exc:
            log.warning("hotkey config problem: %s", exc)
            return False

        def on_press(key):
            name = _mac_key_name(key)
            if name:
                matcher.press(name)

        def on_release(key):
            name = _mac_key_name(key)
            if name:
                matcher.release(name)

        self._listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        self._listener.daemon = True
        self._listener.start()
        return True

    @staticmethod
    def _safe(cb: Callable[[], None]) -> Callable[[], None]:
        def run():
            try:
                cb()
            except Exception:
                log.exception("hotkey handler failed")

        return run

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
