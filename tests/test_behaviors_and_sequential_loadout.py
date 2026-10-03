"""2026-10-02 user report: "it doesn't select Grenade Launcher" and "it doesn't
move or shoot anything". In-match behavior (HANDOFF 6.7) had never been wired
up, and RIVALS' picker is one list per slot (not tabs)."""

from __future__ import annotations

import numpy as np

from warden.behaviors.profiles import InMatchBehavior
from warden.config.schema import Abilities, AbilityKey, Behavior, GameKeys, LoadoutUI
from warden.core.state_machine import NullActions, Signals, State, StateMachine
from warden.flows.loadout import SequentialLoadoutTransaction, learn_row_template, weapon_template_path
from warden.tools.replay import ManualClock
from warden.vision.templates import TemplateLibrary


class FakeInput:
    def __init__(self):
        self.calls: list[tuple] = []
        self.held: set[str] = set()

    def key_tap(self, key, hold_s=None):
        self.calls.append(("tap", key))
        return True

    def key_down(self, key):
        self.calls.append(("down", key))
        self.held.add(key)
        return True

    def key_up(self, key):
        self.calls.append(("up", key))
        self.held.discard(key)
        return True

    def look(self, dx, dy, steps=6):
        self.calls.append(("look", dx, dy))
        return True

    def fire(self, hold_s, button="left"):
        self.calls.append(("fire", round(hold_s, 2)))
        return True

    def release_all(self):
        self.held.clear()


def run_behavior(profile: str, seconds: float, **kw):
    inp = FakeInput()
    t = [0.0]
    b = InMatchBehavior(inp, Behavior(profile=profile, fire_every_seconds=3, anti_idle_seconds=10, **kw),
                        Abilities(enabled=True, keys=[AbilityKey(key="F", every_seconds=5)]), GameKeys(),
                        clock=lambda: t[0])
    b.on_spawn()
    while t[0] < seconds:
        t[0] += 0.25
        b.tick()
    return inp, b


def test_fight_profile_moves_and_shoots():
    inp, _ = run_behavior("fight", 30)
    kinds = [c[0] for c in inp.calls]
    assert kinds.count("down") >= 5          # keeps walking
    assert kinds.count("fire") >= 5          # keeps shooting
    assert ("tap", "1") in inp.calls          # equipped the primary first
    assert ("tap", "F") in inp.calls          # ability used


def test_walking_keys_are_always_released():
    inp, b = run_behavior("patrol", 20)
    downs = sum(1 for c in inp.calls if c[0] == "down")
    ups = sum(1 for c in inp.calls if c[0] == "up")
    assert downs - ups <= 1
    b.stop()
    assert not inp.held


def test_idle_nudge_is_minimal_but_present():
    inp, _ = run_behavior("idle_nudge", 40)
    assert not any(c[0] in ("down", "fire") for c in inp.calls)
    assert 2 <= sum(1 for c in inp.calls if c[0] == "tap" and c[1] in "WASD") <= 6


def test_idle_warning_triggers_an_immediate_nudge():
    inp = FakeInput()
    b = InMatchBehavior(inp, Behavior(profile="idle_nudge", anti_idle_seconds=500), Abilities(), GameKeys(),
                        clock=lambda: 1.0)
    b.on_spawn(0.0)
    b.tick(idle_warning=True, now=1.0)
    assert any(c[0] == "tap" for c in inp.calls)


class BehaviorActions(NullActions):
    def __init__(self):
        self.events = []

    def enter_match(self):
        self.events.append("enter")

    def in_match_tick(self, idle_warning):
        self.events.append("tick")

    def leave_match(self):
        self.events.append("leave")


def test_state_machine_drives_behavior_only_while_alive_in_match():
    actions = BehaviorActions()
    clock = ManualClock(0.0)
    m = StateMachine(actions, clock=clock)
    m.force_state(State.IN_MATCH, "test")
    for _ in range(3):
        clock.advance(0.25)
        m.tick(Signals(health_bar=True))
    clock.advance(0.25)
    m.tick(Signals(respawn_prompt=True))  # died
    assert actions.events[0] == "enter"
    assert actions.events.count("tick") == 3
    assert actions.events[-1] == "leave"
    assert m.state is State.DEAD


# --------------------------------------------------------------------------- sequential picker


def picker_frame(names: list[str], highlight_shift: int = 0) -> np.ndarray:
    """A fake RIVALS weapon list: dark rows with distinct bright blocks per name."""
    import cv2

    frame = np.full((720, 1280, 3), 30, np.uint8)
    for i, name in enumerate(names):
        y = 180 + i * 60
        cv2.rectangle(frame, (487, y), (792, y + 52), (20, 15, 18), -1)
        cv2.putText(frame, name, (560, y + 36), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
    if highlight_shift:
        frame[100:140, 600 + highlight_shift:660 + highlight_shift] = 255
    return frame


class PickerSim:
    """Clicking a row advances to the next slot's list, like the real game."""

    LISTS = {
        "primary": ["Random", "Energy Rifle", "Grenade Launcher", "Minigun"],
        "secondary": ["Random", "Handgun", "Slingshot", "Uzi"],
        "melee": ["Random", "Fists", "Katana", "Scythe"],
        "utility": ["Random", "Medkit", "Grenade", "Molotov"],
    }

    def __init__(self):
        self.slot = 0
        self.clicked: list[str] = []

    def frame(self):
        order = list(self.LISTS)
        if self.slot >= len(order):
            return picker_frame([], highlight_shift=300)
        return picker_frame(self.LISTS[order[self.slot]], highlight_shift=self.slot * 70)

    def click_frac(self, fx, fy, what=""):
        order = list(self.LISTS)
        names = self.LISTS[order[self.slot]]
        row = int((fy * 720 - 180) // 60)
        if 0 <= row < len(names):
            self.clicked.append(names[row])
            self.slot += 1
        return True

    def scroll(self, notches, at):
        return True


def teach(sim_lists, tmp_path, ui):
    lib = TemplateLibrary(tmp_path)
    for slot, names in sim_lists.items():
        target = {"primary": "Grenade Launcher", "secondary": "Slingshot",
                  "melee": "Katana", "utility": "Grenade"}[slot]
        frame = picker_frame(names)
        row = names.index(target)
        fy = (180 + row * 60 + 26) / 720
        crop = learn_row_template(frame, 0.5, fy, ui)
        assert crop is not None
        lib.save(weapon_template_path(slot, target), crop)
    return lib


def test_sequential_picker_selects_each_weapon_in_order(tmp_path):
    ui = LoadoutUI(mode="sequential", verify_threshold=0.8)
    lib = teach(PickerSim.LISTS, tmp_path, ui)
    sim = PickerSim()
    tx = SequentialLoadoutTransaction(sim, lib, ui, get_frame=sim.frame, settle_s=0.0)
    tx.reset({"primary": "Grenade Launcher", "secondary": "Slingshot", "melee": "Katana", "utility": "Grenade"})
    for _ in range(40):
        if tx.tick():
            break
    assert sim.clicked == ["Grenade Launcher", "Slingshot", "Katana", "Grenade"]
    assert tx.result.success


def test_sequential_picker_stops_cleanly_when_a_weapon_is_unknown(tmp_path):
    ui = LoadoutUI(mode="sequential", verify_threshold=0.8, max_search_scrolls=2)
    lib = teach({"primary": PickerSim.LISTS["primary"]}, tmp_path, ui)
    sim = PickerSim()
    tx = SequentialLoadoutTransaction(sim, lib, ui, get_frame=sim.frame, settle_s=0.0, learn_missing=False)
    tx.reset({"primary": "Grenade Launcher", "secondary": "Slingshot", "melee": "Katana", "utility": "Grenade"})
    for _ in range(40):
        if tx.tick():
            break
    assert sim.clicked == ["Grenade Launcher"]
    assert not tx.result.success
    assert "pick it yourself" in tx.result.slots["secondary"].reason
    assert "skipped" in tx.result.slots["utility"].reason


def test_learn_row_template_ignores_clicks_off_the_list():
    ui = LoadoutUI(mode="sequential")
    assert learn_row_template(picker_frame(["Bow"]), 0.1, 0.5, ui) is None


def test_unknown_weapon_is_learned_from_the_players_own_pick(tmp_path):
    """Zero setup: Warden picks what it knows, waits on what it doesn't, learns
    it from the player's click, and knows it next match."""
    ui = LoadoutUI(mode="sequential", verify_threshold=0.8)
    lib = teach({"primary": PickerSim.LISTS["primary"]}, tmp_path, ui)  # only primary known
    sim = PickerSim()
    tx = SequentialLoadoutTransaction(sim, lib, ui, get_frame=sim.frame, settle_s=0.0)
    target = {"primary": "Grenade Launcher", "secondary": "Slingshot"}
    tx.reset(target)
    for _ in range(20):
        tx.tick()
        if tx.waiting_to_learn:
            break
    assert sim.clicked == ["Grenade Launcher"] and tx.waiting_to_learn
    # the player clicks Slingshot themselves (row 2 of the secondary list)
    frame_before = sim.frame()
    fy = (180 + 2 * 60 + 26) / 720
    sim.click_frac(0.5, fy)
    assert tx.learn_from_click(frame_before, 0.5, fy)
    assert tx.done and tx.result.success
    assert lib.exists(weapon_template_path("secondary", "Slingshot"))

    # next match: both picked automatically
    sim2 = PickerSim()
    tx2 = SequentialLoadoutTransaction(sim2, lib, ui, get_frame=sim2.frame, settle_s=0.0)
    tx2.reset(target)
    for _ in range(40):
        if tx2.tick():
            break
    assert sim2.clicked == ["Grenade Launcher", "Slingshot"]
