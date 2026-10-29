"""M2: Quartz input + key map work (fake CGEvents); Windows input order unchanged."""

import types

from _util import check, run


class _Q:
    kCGHIDEventTap = 0
    kCGEventMouseMoved, kCGEventLeftMouseDown, kCGEventLeftMouseUp = 5, 1, 2
    kCGEventRightMouseDown, kCGEventRightMouseUp, kCGEventOtherMouseDown, kCGEventOtherMouseUp = 3, 4, 25, 26
    kCGEventLeftMouseDragged, kCGEventRightMouseDragged, kCGEventOtherMouseDragged = 6, 7, 27
    kCGMouseButtonLeft, kCGMouseButtonRight, kCGMouseButtonCenter = 0, 1, 2
    kCGMouseEventDeltaX, kCGMouseEventDeltaY, kCGScrollEventUnitLine = 4, 5, 1

    def __init__(self): self.posted = []
    def CGEventCreate(self, s): return {}
    def CGEventGetLocation(self, e): return types.SimpleNamespace(x=10.0, y=10.0)
    def CGEventCreateMouseEvent(self, s, t, pos, b): return {"t": t, "pos": pos}
    def CGEventCreateKeyboardEvent(self, s, code, down): return {"code": code, "down": down}
    def CGEventCreateScrollWheelEvent(self, s, u, n, d): return {"wheel": d}
    def CGEventSetIntegerValueField(self, e, f, v): e[f] = v
    def CGEventSetFlags(self, e, f): e["flags"] = f
    def CGEventPost(self, tap, e): self.posted.append(e)


def main():
    from warden.platform.input import SCAN_CODES, effective_order
    from warden.platform.input_mac import MAC_KEYCODES, QuartzMethod

    check("every key has a Mac key code", set(SCAN_CODES) == set(MAC_KEYCODES))
    check("Mac key codes are unique", len(set(MAC_KEYCODES.values())) == len(MAC_KEYCODES))
    q = _Q()
    m = QuartzMethod(quartz=q)
    m.move_abs(100, 200); m.button("left", True); m.button("left", False); m.key("W", True)
    check("click + key posted", [e.get("t", e.get("code")) for e in q.posted] == [5, 1, 2, 0x0D])
    default = ["sendinput", "pydirectinput", "pynput"]
    check("Windows input order unchanged", effective_order(default, "win32") == default)
    check("Mac tries Quartz first", effective_order(default, "darwin")[0] == "quartz")


run(main)
