"""macOS input via Quartz CGEvents (the Mac counterpart of ``SendInputMethod``).

Implements the same ``InputMethod`` shape as the Windows methods in
``platform/input.py``, so ``InputController`` (focus gate, observe-only,
emergency stop, jiggle-then-click) is unchanged. ``pynput`` stays behind it
as the fallback.

Coordinates are global display *points* (top-left origin) - the same space
Quartz window bounds use, so ``Rect.frac_to_px`` on a macOS client rect
already yields a valid click location; see ``platform/retina.py`` for the
pixel/point conversion used on the capture side.

Needs the macOS **Accessibility** permission. Without it, macOS silently
drops posted events; the Mac setup screen checks for it up front.
"""

from __future__ import annotations

import sys

# Warden key name (``platform.input.SCAN_CODES`` keys) -> macOS virtual key
# code (Carbon ``kVK_*`` constants from HIToolbox/Events.h). ANSI layout codes
# are physical key positions, the same idea as Windows scan codes.
MAC_KEYCODES: dict[str, int] = {
    "A": 0x00, "S": 0x01, "D": 0x02, "F": 0x03, "H": 0x04, "G": 0x05, "Z": 0x06, "X": 0x07,
    "C": 0x08, "V": 0x09, "B": 0x0B, "Q": 0x0C, "W": 0x0D, "E": 0x0E, "R": 0x0F, "Y": 0x10,
    "T": 0x11, "1": 0x12, "2": 0x13, "3": 0x14, "4": 0x15, "6": 0x16, "5": 0x17, "9": 0x19,
    "7": 0x1A, "8": 0x1C, "0": 0x1D, "O": 0x1F, "U": 0x20, "I": 0x22, "P": 0x23, "L": 0x25,
    "J": 0x26, "K": 0x28, "N": 0x2D, "M": 0x2E,
    "ENTER": 0x24, "TAB": 0x30, "SPACE": 0x31, "ESCAPE": 0x35,
    "SHIFT": 0x38, "ALT": 0x3A, "CTRL": 0x3B,  # ALT = Option
    "F1": 0x7A, "F2": 0x78, "F3": 0x63, "F4": 0x76, "F5": 0x60, "F6": 0x61,
    "F7": 0x62, "F8": 0x64, "F9": 0x65, "F10": 0x6D, "F11": 0x67, "F12": 0x6F,
    "LEFT": 0x7B, "RIGHT": 0x7C, "DOWN": 0x7D, "UP": 0x7E,
}

# CGEvent modifier flags, so a held Shift/Ctrl/Option is reported on the events
# that follow it (games read the flags, not just the modifier key events).
_MODIFIER_FLAGS = {"SHIFT": 0x00020000, "CTRL": 0x00040000, "ALT": 0x00080000}


def mac_keycode(key: str) -> int:
    try:
        return MAC_KEYCODES[key]
    except KeyError:
        raise ValueError(f"no macOS key code for '{key}'") from None


class QuartzMethod:
    """Posts CGEvents to the HID event tap. ``quartz`` is injectable for tests."""

    name = "quartz"

    def __init__(self, quartz=None):
        if quartz is None:
            if sys.platform != "darwin":
                raise OSError("Quartz input requires macOS")
            import Quartz as quartz  # pyobjc-framework-Quartz
        self._q = quartz
        self._buttons_down: set[str] = set()
        self._mods_down: set[str] = set()

    # -- helpers ---------------------------------------------------------

    def _post(self, event) -> None:
        if event is None:
            raise RuntimeError("CGEvent creation failed")
        flags = 0
        for mod in self._mods_down:
            flags |= _MODIFIER_FLAGS[mod]
        if flags:
            self._q.CGEventSetFlags(event, flags)
        self._q.CGEventPost(self._q.kCGHIDEventTap, event)

    def _cursor(self) -> tuple[float, float]:
        loc = self._q.CGEventGetLocation(self._q.CGEventCreate(None))
        return float(loc.x), float(loc.y)

    def _move_type(self) -> tuple[int, int]:
        """While a button is held, macOS expects *drag* events, not plain moves."""
        q = self._q
        if "left" in self._buttons_down:
            return q.kCGEventLeftMouseDragged, q.kCGMouseButtonLeft
        if "right" in self._buttons_down:
            return q.kCGEventRightMouseDragged, q.kCGMouseButtonRight
        if "middle" in self._buttons_down:
            return q.kCGEventOtherMouseDragged, q.kCGMouseButtonCenter
        return q.kCGEventMouseMoved, q.kCGMouseButtonLeft

    # -- InputMethod -----------------------------------------------------

    def move_abs(self, x: int, y: int) -> None:
        etype, button = self._move_type()
        self._post(self._q.CGEventCreateMouseEvent(None, etype, (float(x), float(y)), button))

    def move_rel(self, dx: int, dy: int) -> None:
        # Roblox reads the delta fields for camera look when the cursor is
        # locked; the absolute position is updated too for the unlocked case.
        q = self._q
        cx, cy = self._cursor()
        etype, button = self._move_type()
        event = q.CGEventCreateMouseEvent(None, etype, (cx + dx, cy + dy), button)
        if event is None:
            raise RuntimeError("CGEvent creation failed")
        q.CGEventSetIntegerValueField(event, q.kCGMouseEventDeltaX, int(dx))
        q.CGEventSetIntegerValueField(event, q.kCGMouseEventDeltaY, int(dy))
        self._post(event)

    def button(self, button: str, down: bool) -> None:
        q = self._q
        types = {
            "left": (q.kCGEventLeftMouseDown, q.kCGEventLeftMouseUp, q.kCGMouseButtonLeft),
            "right": (q.kCGEventRightMouseDown, q.kCGEventRightMouseUp, q.kCGMouseButtonRight),
            "middle": (q.kCGEventOtherMouseDown, q.kCGEventOtherMouseUp, q.kCGMouseButtonCenter),
        }
        if button not in types:
            raise ValueError(f"unknown mouse button '{button}'")
        down_type, up_type, cg_button = types[button]
        event = q.CGEventCreateMouseEvent(None, down_type if down else up_type, self._cursor(), cg_button)
        if down:
            self._buttons_down.add(button)
        else:
            self._buttons_down.discard(button)
        self._post(event)

    def key(self, key: str, down: bool) -> None:
        code = mac_keycode(key)
        if key in _MODIFIER_FLAGS:
            if down:
                self._mods_down.add(key)
            else:
                self._mods_down.discard(key)
        self._post(self._q.CGEventCreateKeyboardEvent(None, code, bool(down)))

    def wheel(self, notches: int) -> None:
        q = self._q
        self._post(q.CGEventCreateScrollWheelEvent(None, q.kCGScrollEventUnitLine, 1, int(notches)))
