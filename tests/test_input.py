import pytest

from warden.geometry import Rect
from warden.platform.input import CornerWatch, InputController, InputError, normalize_key


class FakeGate:
    def __init__(self, focused=True, refocus_result=True):
        self.focused = focused
        self.refocus_calls = 0
        self.refocus_result = refocus_result

    def is_focused(self):
        return self.focused

    def refocus(self):
        self.refocus_calls += 1
        return self.refocus_result


class RecordingMethod:
    """Records every call; can be told to always fail."""

    def __init__(self, name, fail=False):
        self.name = name
        self.fail = fail
        self.calls = []

    def _maybe_fail(self, op, *args):
        self.calls.append((op, args))
        if self.fail:
            raise InputError(f"{self.name} is broken")

    def move_abs(self, x, y):
        self._maybe_fail("move_abs", x, y)

    def move_rel(self, dx, dy):
        self._maybe_fail("move_rel", dx, dy)

    def button(self, button, down):
        self._maybe_fail("button", button, down)

    def key(self, key, down):
        self._maybe_fail("key", key, down)

    def wheel(self, notches):
        self._maybe_fail("wheel", notches)


def make_controller(methods, focused=True, observe_only=False, refocus_result=True):
    gate = FakeGate(focused, refocus_result=refocus_result)
    return InputController(
        methods=methods, gate=gate,
        rect=lambda: Rect(0, 0, 1000, 1000),
        sleep=lambda s: None,
        observe_only=observe_only,
    ), gate


def test_click_blocked_when_not_focused_and_refocus_fails():
    primary = RecordingMethod("sendinput")
    ctl, gate = make_controller([primary], focused=False, refocus_result=False)
    ok = ctl.click_frac(0.5, 0.5)
    assert not ok
    assert gate.refocus_calls == 1
    assert primary.calls == []


def test_click_proceeds_in_the_same_call_after_a_successful_refocus():
    """2026-10-03 user report: a focus hiccup (e.g. mid weapon-pick) used to
    drop the action and make the caller wait for its own next retry cycle -
    even though the game was refocused within gate.refocus()'s own poll. Now
    a successful refocus sends the action right away instead of wasting a
    whole extra cycle."""
    primary = RecordingMethod("sendinput")
    ctl, gate = make_controller([primary], focused=False, refocus_result=True)
    ok = ctl.click_frac(0.5, 0.5)
    assert ok
    assert gate.refocus_calls == 1
    assert primary.calls != []


def test_click_sends_jiggle_then_button_down_up():
    primary = RecordingMethod("sendinput")
    ctl, _ = make_controller([primary])
    assert ctl.click_frac(0.5, 0.5, what="play button")
    ops = [c[0] for c in primary.calls]
    assert ops.count("move_rel") == 2  # jiggle out and back
    assert "button" in ops
    downs = [c for c in primary.calls if c[0] == "button" and c[1][1] is True]
    ups = [c for c in primary.calls if c[0] == "button" and c[1][1] is False]
    assert len(downs) == 1 and len(ups) == 1


def test_fallback_chain_moves_to_next_method_on_failure():
    broken = RecordingMethod("sendinput", fail=True)
    backup = RecordingMethod("pynput")
    ctl, _ = make_controller([broken, backup])
    assert ctl.key_tap("F6")
    assert ("key", ("F6", True)) in backup.calls
    assert ctl.last_method == "pynput"


def test_all_methods_failing_is_reported_not_raised():
    ctl, _ = make_controller([RecordingMethod("a", fail=True), RecordingMethod("b", fail=True)])
    assert not ctl.key_tap("SPACE")


def test_observe_only_sends_nothing():
    primary = RecordingMethod("sendinput")
    ctl, _ = make_controller([primary], observe_only=True)
    assert ctl.click_frac(0.2, 0.2)
    assert ctl.key_tap("M")
    assert primary.calls == []


def test_emergency_stop_blocks_and_releases_held_keys():
    primary = RecordingMethod("sendinput")
    ctl, _ = make_controller([primary])
    ctl.key_down("W")
    ctl.emergency_stop("test")
    assert not ctl.key_tap("SPACE")
    assert ("key", ("W", False)) in primary.calls  # held key released on stop
    ctl.reset_stop()
    assert ctl.key_tap("SPACE")


def test_normalize_key_aliases_and_unknown():
    assert normalize_key("esc") == "ESCAPE"
    assert normalize_key(" m ") == "M"
    with pytest.raises(ValueError):
        normalize_key("ZZZ_NOT_A_KEY")


def test_no_input_methods_raises_at_construction():
    with pytest.raises(InputError):
        InputController(methods=[], gate=FakeGate(), rect=lambda: None)


def test_corner_watch_fires_once_after_hold_and_resets_outside():
    t = [0.0]
    positions = iter([(2, 2), (2, 2), (2, 2), (2, 2), (500, 500), (1, 1), (1, 1)])
    fired = []
    watch = CornerWatch(cursor=lambda: next(positions), on_trigger=fired.append,
                         corner_px=5, hold_s=0.3, clock=lambda: t[0])
    for dt in (0.0, 0.1, 0.2, 0.35):  # still under 0.3s until the 4th poll
        watch.poll()
        t[0] += dt
    assert fired == ["mouse held in the top-left corner"]
    watch.poll()  # moved away -> resets
    watch.poll()  # back in corner, timer restarts
    assert fired == ["mouse held in the top-left corner"]
