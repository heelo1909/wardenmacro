"""Game input: SendInput scan codes first, then pydirectinput, then pynput.

``InputController`` is the only thing the rest of Warden talks to. It
enforces the focus gate, observe-only mode and the emergency stop, and does
the jiggle-then-click sequence Roblox needs to register clicks.
"""

from __future__ import annotations

import ctypes
import logging
import sys
import threading
import time
from collections.abc import Callable
from typing import Protocol

from warden.behaviors.humanize import Humanizer
from warden.core.events import EventBus
from warden.geometry import Rect

log = logging.getLogger(__name__)

# name -> (scan code, extended?)
SCAN_CODES: dict[str, tuple[int, bool]] = {
    "ESCAPE": (0x01, False), "1": (0x02, False), "2": (0x03, False), "3": (0x04, False),
    "4": (0x05, False), "5": (0x06, False), "6": (0x07, False), "7": (0x08, False),
    "8": (0x09, False), "9": (0x0A, False), "0": (0x0B, False), "TAB": (0x0F, False),
    "Q": (0x10, False), "W": (0x11, False), "E": (0x12, False), "R": (0x13, False),
    "T": (0x14, False), "Y": (0x15, False), "U": (0x16, False), "I": (0x17, False),
    "O": (0x18, False), "P": (0x19, False), "ENTER": (0x1C, False), "CTRL": (0x1D, False),
    "A": (0x1E, False), "S": (0x1F, False), "D": (0x20, False), "F": (0x21, False),
    "G": (0x22, False), "H": (0x23, False), "J": (0x24, False), "K": (0x25, False),
    "L": (0x26, False), "SHIFT": (0x2A, False), "Z": (0x2C, False), "X": (0x2D, False),
    "C": (0x2E, False), "V": (0x2F, False), "B": (0x30, False), "N": (0x31, False),
    "M": (0x32, False), "ALT": (0x38, False), "SPACE": (0x39, False),
    "F1": (0x3B, False), "F2": (0x3C, False), "F3": (0x3D, False), "F4": (0x3E, False),
    "F5": (0x3F, False), "F6": (0x40, False), "F7": (0x41, False), "F8": (0x42, False),
    "F9": (0x43, False), "F10": (0x44, False), "F11": (0x57, False), "F12": (0x58, False),
    "UP": (0x48, True), "LEFT": (0x4B, True), "RIGHT": (0x4D, True), "DOWN": (0x50, True),
}
_ALIASES = {"ESC": "ESCAPE", "RETURN": "ENTER", "CONTROL": "CTRL", "LSHIFT": "SHIFT", " ": "SPACE"}


def normalize_key(name: str) -> str:
    key = name.strip().upper()
    key = _ALIASES.get(key, key)
    if key not in SCAN_CODES:
        raise ValueError(f"unsupported key '{name}'")
    return key


class InputError(Exception):
    pass


class InputMethod(Protocol):
    name: str

    def move_abs(self, x: int, y: int) -> None: ...
    def move_rel(self, dx: int, dy: int) -> None: ...
    def button(self, button: str, down: bool) -> None: ...
    def key(self, key: str, down: bool) -> None: ...
    def wheel(self, notches: int) -> None: ...


# --------------------------------------------------------------------------- SendInput


class SendInputMethod:
    name = "sendinput"

    def __init__(self):
        if sys.platform != "win32":
            raise OSError("SendInput requires Windows")
        from ctypes import wintypes

        ulong_ptr = ctypes.c_size_t

        class MOUSEINPUT(ctypes.Structure):
            _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                        ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ulong_ptr)]

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                        ("time", wintypes.DWORD), ("dwExtraInfo", ulong_ptr)]

        class HARDWAREINPUT(ctypes.Structure):
            _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]

        class _U(ctypes.Union):
            _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]

        class INPUT(ctypes.Structure):
            _fields_ = [("type", wintypes.DWORD), ("u", _U)]

        self._INPUT, self._MOUSEINPUT, self._KEYBDINPUT = INPUT, MOUSEINPUT, KEYBDINPUT
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
        self._user32.SendInput.restype = wintypes.UINT
        self._user32.GetSystemMetrics.argtypes = [ctypes.c_int]

    def _send(self, *inputs) -> None:
        arr = (self._INPUT * len(inputs))(*inputs)
        sent = self._user32.SendInput(len(inputs), arr, ctypes.sizeof(self._INPUT))
        if sent != len(inputs):
            raise InputError(f"SendInput inserted {sent}/{len(inputs)} events (error {ctypes.get_last_error()})")

    def _mouse(self, dx=0, dy=0, data=0, flags=0):
        return self._INPUT(type=0, u=type(self._INPUT().u)(mi=self._MOUSEINPUT(dx, dy, data & 0xFFFFFFFF, flags, 0, 0)))

    def move_abs(self, x: int, y: int) -> None:
        gsm = self._user32.GetSystemMetrics
        vx, vy, vw, vh = gsm(76), gsm(77), gsm(78), gsm(79)  # virtual desktop
        nx = int(round((x - vx) * 65535 / max(vw - 1, 1)))
        ny = int(round((y - vy) * 65535 / max(vh - 1, 1)))
        # MOVE | ABSOLUTE | VIRTUALDESK
        self._send(self._mouse(nx, ny, 0, 0x0001 | 0x8000 | 0x4000))

    def move_rel(self, dx: int, dy: int) -> None:
        self._send(self._mouse(dx, dy, 0, 0x0001))

    def button(self, button: str, down: bool) -> None:
        flags = {"left": (0x0002, 0x0004), "right": (0x0008, 0x0010), "middle": (0x0020, 0x0040)}[button]
        self._send(self._mouse(0, 0, 0, flags[0] if down else flags[1]))

    def key(self, key: str, down: bool) -> None:
        scan, extended = SCAN_CODES[key]
        flags = 0x0008  # KEYEVENTF_SCANCODE
        if extended:
            flags |= 0x0001
        if not down:
            flags |= 0x0002
        ki = self._KEYBDINPUT(0, scan, flags, 0, 0)
        self._send(self._INPUT(type=1, u=type(self._INPUT().u)(ki=ki)))

    def wheel(self, notches: int) -> None:
        self._send(self._mouse(0, 0, 120 * notches, 0x0800))


# --------------------------------------------------------------------------- fallbacks


class PyDirectInputMethod:
    name = "pydirectinput"

    def __init__(self):
        import pydirectinput  # optional dependency

        pydirectinput.PAUSE = 0
        pydirectinput.FAILSAFE = False
        self._p = pydirectinput

    def move_abs(self, x, y):
        self._p.moveTo(x, y)

    def move_rel(self, dx, dy):
        self._p.moveRel(dx, dy, relative=True)

    def button(self, button, down):
        (self._p.mouseDown if down else self._p.mouseUp)(button=button)

    def key(self, key, down):
        name = {"ESCAPE": "esc", "CTRL": "ctrl", "ENTER": "enter"}.get(key, key.lower())
        (self._p.keyDown if down else self._p.keyUp)(name)

    def wheel(self, notches):
        if not hasattr(self._p, "scroll"):
            raise InputError("pydirectinput build has no scroll()")
        self._p.scroll(notches)


class PynputMethod:
    name = "pynput"

    def __init__(self):
        from pynput import keyboard, mouse

        self._kb, self._ms = keyboard, mouse
        self._k = keyboard.Controller()
        self._m = mouse.Controller()

    def move_abs(self, x, y):
        self._m.position = (x, y)

    def move_rel(self, dx, dy):
        self._m.move(dx, dy)

    def button(self, button, down):
        btn = getattr(self._ms.Button, button)
        (self._m.press if down else self._m.release)(btn)

    def key(self, key, down):
        special = {"ESCAPE": "esc", "SPACE": "space", "ENTER": "enter", "TAB": "tab", "SHIFT": "shift",
                   "CTRL": "ctrl", "ALT": "alt", "UP": "up", "DOWN": "down", "LEFT": "left", "RIGHT": "right"}
        if key in special:
            k = getattr(self._kb.Key, special[key])
        elif key.startswith("F") and key[1:].isdigit():
            k = getattr(self._kb.Key, key.lower())
        else:
            k = key.lower()
        (self._k.press if down else self._k.release)(k)

    def wheel(self, notches):
        self._m.scroll(0, notches)


def build_methods(order: list[str]) -> list[InputMethod]:
    factories = {"sendinput": SendInputMethod, "pydirectinput": PyDirectInputMethod, "pynput": PynputMethod}
    methods: list[InputMethod] = []
    for name in order:
        try:
            methods.append(factories[name]())
        except Exception as exc:  # optional backends may be missing
            log.info("input method %s unavailable: %s", name, exc)
    return methods


# --------------------------------------------------------------------------- controller


class InputController:
    """Gatekeeper for every key and click Warden sends."""

    def __init__(
        self,
        methods: list[InputMethod],
        gate,
        rect: Callable[[], Rect | None],
        humanizer: Humanizer | None = None,
        bus: EventBus | None = None,
        sleep: Callable[[float], None] = time.sleep,
        observe_only: bool = False,
        jiggle_px: int = 3,
        key_hold_ms: tuple[int, int] = (40, 110),
    ):
        if not methods:
            raise InputError("no input method available")
        self.methods = methods
        self.gate = gate
        self.rect = rect
        self.h = humanizer or Humanizer()
        self.bus = bus
        self.sleep = sleep
        self.observe_only = observe_only
        self.jiggle_px = jiggle_px
        self.key_hold_ms = key_hold_ms
        self.stopped = threading.Event()  # emergency stop latch
        self.last_method: str | None = None
        self._held: set[str] = set()

    # -- plumbing -----------------------------------------------------------

    def _emit(self, topic: str, message: str, level: str = "debug", **data) -> None:
        if self.bus is not None:
            self.bus.emit(topic, message, level=level, **data)

    def _allowed(self, what: str) -> bool | None:
        """True = send, None = observe-only (pretend success), False = blocked."""
        if self.stopped.is_set():
            self._emit("input.blocked", f"{what} blocked: emergency stop is active", "warn")
            return False
        if self.observe_only:
            self._emit("input.observe", f"observe-only: would {what}", "info")
            return None
        if not self.gate.is_focused():
            self._emit("input.blocked", f"{what} skipped: Roblox is not the foreground window; refocusing", "warn")
            self.gate.refocus()
            return False
        return True

    def _do(self, op: str, *args) -> None:
        """Run one primitive through the fallback chain."""
        errors = []
        for method in self.methods:
            try:
                getattr(method, op)(*args)
            except Exception as exc:
                errors.append(f"{method.name}: {exc}")
                continue
            if method.name != self.last_method:
                self._emit("input.method", f"input via {method.name}", "debug", op=op)
                self.last_method = method.name
            return
        raise InputError(f"{op} failed on every method ({'; '.join(errors)})")

    def _guarded(self, what: str, body: Callable[[], None]) -> bool:
        allowed = self._allowed(what)
        if allowed is None:
            return True
        if not allowed:
            return False
        try:
            body()
        except InputError as exc:
            self._emit("input.error", f"{what} failed: {exc}", "error")
            return False
        return True

    # -- public actions -----------------------------------------------------

    def click_frac(self, fx: float, fy: float, button: str = "left", what: str = "click") -> bool:
        rect = self.rect()
        if rect is None or rect.is_empty():
            self._emit("input.blocked", f"{what} skipped: no client rect", "warn")
            return False
        x, y = rect.frac_to_px(fx, fy)

        def body():
            self._do("move_abs", x, y)
            self.sleep(self.h.between(0.03, 0.08))
            # Roblox can drop a click that has no preceding mouse motion.
            j = max(1, self.jiggle_px)
            dx, dy = self.h.offset_px(j) or 1, self.h.offset_px(j)
            self._do("move_rel", dx, dy)
            self.sleep(self.h.between(0.02, 0.06))
            self._do("move_rel", -dx, -dy)
            self.sleep(self.h.between(0.02, 0.06))
            self._do("button", button, True)
            self.sleep(self.h.hold_seconds(self.key_hold_ms))
            self._do("button", button, False)

        ok = self._guarded(f"{what} at ({fx:.3f}, {fy:.3f})", body)
        if ok:
            self._emit("input.click", f"{what} at ({fx:.3f}, {fy:.3f})", "debug", fx=fx, fy=fy)
        return ok

    def key_tap(self, key: str, hold_s: float | None = None) -> bool:
        k = normalize_key(key)
        hold = self.h.hold_seconds(self.key_hold_ms) if hold_s is None else self.h.jitter(hold_s)

        def body():
            self._do("key", k, True)
            self.sleep(hold)
            self._do("key", k, False)

        ok = self._guarded(f"press {k}", body)
        if ok:
            self._emit("input.key", f"pressed {k}", "debug", key=k)
        return ok

    def fire(self, hold_s: float, button: str = "left") -> bool:
        """Press and hold a mouse button where the cursor already is - in
        first person that's the crosshair; moving the cursor would jerk the
        camera instead."""

        def body():
            self._do("button", button, True)
            self.sleep(max(hold_s, 0.03))
            self._do("button", button, False)

        ok = self._guarded(f"fire ({hold_s:.2f}s)", body)
        if ok:
            self._emit("input.fire", f"fired for {hold_s:.2f}s", "debug")
        return ok

    def key_down(self, key: str) -> bool:
        k = normalize_key(key)

        def body():
            self._do("key", k, True)
            self._held.add(k)

        return self._guarded(f"hold {k}", body)

    def key_up(self, key: str) -> bool:
        k = normalize_key(key)
        if k not in self._held:
            return True
        self._held.discard(k)
        try:
            self._do("key", k, False)  # releasing is always allowed
            return True
        except InputError:
            return False

    def release_all(self) -> None:
        for k in list(self._held):
            self.key_up(k)

    def wheel(self, notches: int, at: tuple[float, float] | None = None) -> bool:
        """Scroll the wheel ``notches`` (negative = down), one notch at a time."""
        rect = self.rect()

        def body():
            if at is not None and rect is not None:
                self._do("move_abs", *rect.frac_to_px(*at))
                self.sleep(self.h.between(0.03, 0.08))
            step = -1 if notches < 0 else 1
            for _ in range(abs(notches)):
                self._do("wheel", step)
                self.sleep(self.h.between(0.04, 0.12))

        return self._guarded(f"scroll {notches:+d}", body)

    def look(self, dx: int, dy: int, steps: int = 6) -> bool:
        """Relative camera move spread over a few small steps."""

        def body():
            n = max(1, steps)
            done_x = done_y = 0
            for i in range(1, n + 1):
                tx, ty = round(dx * i / n), round(dy * i / n)
                self._do("move_rel", tx - done_x, ty - done_y)
                done_x, done_y = tx, ty
                self.sleep(self.h.between(0.008, 0.025))

        return self._guarded(f"look ({dx:+d}, {dy:+d})", body)

    def emergency_stop(self, reason: str) -> None:
        if not self.stopped.is_set():
            self.stopped.set()
            self.release_all()
            self._emit("input.emergency_stop", f"emergency stop: {reason}", "warn")

    def reset_stop(self) -> None:
        self.stopped.clear()


# --------------------------------------------------------------------------- emergency corner


class CornerWatch:
    """Fires once when the cursor sits in the top-left corner for ``hold_s`` seconds."""

    def __init__(self, cursor: Callable[[], tuple[int, int]], on_trigger: Callable[[str], None],
                 corner_px: int = 5, hold_s: float = 0.3, origin: tuple[int, int] = (0, 0),
                 clock: Callable[[], float] = time.monotonic):
        self.cursor = cursor
        self.on_trigger = on_trigger
        self.corner_px = corner_px
        self.hold_s = hold_s
        self.origin = origin
        self.clock = clock
        self._since: float | None = None
        self._fired = False
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def poll(self) -> bool:
        x, y = self.cursor()
        ox, oy = self.origin
        inside = ox <= x < ox + self.corner_px and oy <= y < oy + self.corner_px
        now = self.clock()
        if not inside:
            self._since = None
            self._fired = False
            return False
        if self._since is None:
            self._since = now
        if not self._fired and now - self._since >= self.hold_s:
            self._fired = True
            self.on_trigger("mouse held in the top-left corner")
            return True
        return False

    def start(self, interval: float = 0.03) -> None:
        def loop():
            while not self._stop.wait(interval):
                try:
                    self.poll()
                except Exception:
                    log.exception("corner watch poll failed")

        self._stop.clear()
        self._thread = threading.Thread(target=loop, name="warden-corner-watch", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
