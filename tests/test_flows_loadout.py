from pathlib import Path

import pytest

from tests.fixtures_frames import blank, make_template, paste
from warden.config.schema import LoadoutSlotUI, LoadoutUI, ROI
from warden.flows.loadout import LoadoutTransaction, weapon_template_path
from warden.vision.templates import TemplateLibrary

PRIMARY = LoadoutSlotUI(
    tab=(0.5, 0.05),
    grid_roi=ROI(x1=0.10, y1=0.20, x2=0.90, y2=0.80),
    verify_roi=ROI(x1=0.00, y1=0.90, x2=0.20, y2=1.00),
)
SECONDARY = LoadoutSlotUI(
    tab=(0.6, 0.05),
    grid_roi=ROI(x1=0.10, y1=0.20, x2=0.90, y2=0.80),
    verify_roi=ROI(x1=0.22, y1=0.90, x2=0.42, y2=1.00),
)


def ui(**kw):
    base = dict(slots={"primary": PRIMARY}, max_search_scrolls=4, verify_threshold=0.75, scroll_notches=2)
    base.update(kw)
    return LoadoutUI(**base)


class FakeActions:
    def __init__(self, on_click=None, on_scroll=None):
        self.clicks: list[tuple[float, float, str]] = []
        self.scrolls: list[tuple[int, tuple[float, float]]] = []
        self.on_click = on_click
        self.on_scroll = on_scroll

    def click_frac(self, fx, fy, what=""):
        self.clicks.append((fx, fy, what))
        if self.on_click:
            self.on_click(fx, fy, what)
        return True

    def scroll(self, notches, at):
        self.scrolls.append((notches, at))
        if self.on_scroll:
            self.on_scroll(notches, at)
        return True


def make_templates(tmp_path: Path, weapons: dict) -> TemplateLibrary:
    """weapons: {(slot, name): bgr_color} -> saved template library."""
    lib = TemplateLibrary(tmp_path)
    for (slot, name), bgr in weapons.items():
        lib.save(weapon_template_path(slot, name), make_template(bgr=bgr))
    return lib


def run_to_done(txn: LoadoutTransaction, max_ticks: int = 50) -> None:
    for _ in range(max_ticks):
        if txn.tick():
            return
    raise AssertionError("transaction never finished")


# --------------------------------------------------------------------------- basic outcomes


def test_already_equipped_slot_skips_without_any_click(tmp_path):
    templates = make_templates(tmp_path, {("primary", "Rifle"): (10, 200, 10)})
    frame = blank()
    paste(frame, make_template(bgr=(10, 200, 10)), (0.02, 0.91))  # already shows Rifle
    actions = FakeActions()
    txn = LoadoutTransaction(actions, templates, ui(), get_frame=lambda: frame)
    txn.reset({"primary": "Rifle"})
    run_to_done(txn)
    outcome = txn.result.slots["primary"]
    assert outcome.verified and not outcome.fixed
    assert actions.clicks == []


def test_finds_new_weapon_clicks_tab_then_tile_then_verifies(tmp_path):
    templates = make_templates(tmp_path, {
        ("primary", "OldGun"): (10, 200, 10),
        ("primary", "NewGun"): (200, 10, 10),
    })
    frame = blank()
    paste(frame, make_template(bgr=(10, 200, 10)), (0.02, 0.91))   # currently OldGun
    paste(frame, make_template(bgr=(200, 10, 10)), (0.45, 0.45))  # NewGun sits in the grid

    def on_click(fx, fy, what):
        if "weapon tile" in what:  # clicking the tile equips it
            paste(frame, make_template(bgr=(200, 10, 10)), (0.02, 0.91))

    actions = FakeActions(on_click=on_click)
    txn = LoadoutTransaction(actions, templates, ui(), get_frame=lambda: frame)
    txn.reset({"primary": "NewGun"})
    run_to_done(txn)

    outcome = txn.result.slots["primary"]
    assert outcome.verified and outcome.fixed
    assert any("tab" in c[2] for c in actions.clicks)
    assert any("weapon tile" in c[2] for c in actions.clicks)
    assert actions.clicks.index(next(c for c in actions.clicks if "tab" in c[2])) < \
        actions.clicks.index(next(c for c in actions.clicks if "weapon tile" in c[2]))


def test_scrolls_until_the_tile_is_revealed(tmp_path):
    templates = make_templates(tmp_path, {("primary", "Hidden"): (50, 50, 220)})
    frame = blank()  # Hidden not visible at first - must scroll to find it

    def on_scroll(notches, at):
        if len(actions.scrolls) >= 2:  # revealed after a couple of scrolls
            paste(frame, make_template(bgr=(50, 50, 220)), (0.5, 0.4))

    def on_click(fx, fy, what):
        if "weapon tile" in what:
            paste(frame, make_template(bgr=(50, 50, 220)), (0.02, 0.91))

    actions = FakeActions(on_scroll=on_scroll, on_click=on_click)
    txn = LoadoutTransaction(actions, templates, ui(), get_frame=lambda: frame)
    txn.reset({"primary": "Hidden"})
    run_to_done(txn)

    outcome = txn.result.slots["primary"]
    assert outcome.verified and outcome.fixed
    assert len(actions.scrolls) >= 2


def test_gives_up_after_max_scrolls_and_never_guesses_a_click(tmp_path):
    templates = make_templates(tmp_path, {("primary", "NeverThere"): (99, 99, 99)})
    frame = blank()  # never revealed, no matter how much we scroll
    actions = FakeActions()
    txn = LoadoutTransaction(actions, templates, ui(max_search_scrolls=3), get_frame=lambda: frame)
    txn.reset({"primary": "NeverThere"})
    run_to_done(txn)

    outcome = txn.result.slots["primary"]
    assert not outcome.verified
    assert outcome.reason == "weapon tile not found"
    assert len(actions.scrolls) == 3
    assert not any("weapon tile" in c[2] for c in actions.clicks)  # never guessed a tile position


def test_missing_template_fails_without_touching_input(tmp_path):
    templates = TemplateLibrary(tmp_path)  # nothing captured for this weapon yet
    actions = FakeActions()
    txn = LoadoutTransaction(actions, templates, ui(), get_frame=lambda: blank())
    txn.reset({"primary": "Uncaptured"})
    run_to_done(txn)
    outcome = txn.result.slots["primary"]
    assert not outcome.verified and outcome.reason == "no template captured"
    assert actions.clicks == [] and actions.scrolls == []


def test_slot_without_ui_calibration_fails_gracefully(tmp_path):
    templates = make_templates(tmp_path, {("secondary", "Pistol"): (1, 2, 3)})
    actions = FakeActions()
    txn = LoadoutTransaction(actions, templates, ui(slots={}), get_frame=lambda: blank())  # no slots calibrated
    txn.reset({"secondary": "Pistol"})
    run_to_done(txn)
    assert txn.result.slots["secondary"].reason == "not calibrated"


def test_blank_target_slot_is_left_untouched(tmp_path):
    templates = make_templates(tmp_path, {("primary", "Rifle"): (10, 200, 10)})
    actions = FakeActions()
    txn = LoadoutTransaction(actions, templates, ui(), get_frame=lambda: blank())
    txn.reset({"primary": "", "secondary": "Pistol"})  # primary blank = don't touch
    run_to_done(txn)
    assert "primary" not in txn.result.slots


def test_empty_target_finishes_immediately_with_no_actions(tmp_path):
    templates = TemplateLibrary(tmp_path)
    actions = FakeActions()
    txn = LoadoutTransaction(actions, templates, ui(), get_frame=lambda: blank())
    txn.reset({})
    assert txn.tick() is True
    assert txn.result.slots == {}
    assert actions.clicks == [] and actions.scrolls == []


# --------------------------------------------------------------------------- aggregate result


def test_four_slots_mixed_outcomes_aggregate_correctly(tmp_path):
    templates = make_templates(
        tmp_path, {("primary", "AlreadyOn"): (10, 200, 10), ("secondary", "Fresh"): (200, 10, 10)},
    )
    frame = blank()
    paste(frame, make_template(bgr=(10, 200, 10)), (0.02, 0.91))     # primary already equipped
    paste(frame, make_template(bgr=(200, 10, 10)), (0.45, 0.45))     # secondary's tile is visible

    def on_click(fx, fy, what):
        if "weapon tile" in what and "secondary" in what:
            paste(frame, make_template(bgr=(200, 10, 10)), (0.24, 0.91))

    actions = FakeActions(on_click=on_click)
    cfg = ui(slots={"primary": PRIMARY, "secondary": SECONDARY})
    txn = LoadoutTransaction(actions, templates, cfg, get_frame=lambda: frame)
    txn.reset({"primary": "AlreadyOn", "secondary": "Fresh"})
    run_to_done(txn)

    assert txn.result.success
    assert txn.result.fixes == 1  # only secondary actually needed a click
    assert txn.result.slots["primary"].fixed is False
    assert txn.result.slots["secondary"].fixed is True


def test_failed_slot_does_not_block_other_slots_from_committing(tmp_path):
    templates = make_templates(tmp_path, {("secondary", "Fresh"): (200, 10, 10)})  # no primary template
    frame = blank()
    paste(frame, make_template(bgr=(200, 10, 10)), (0.45, 0.45))

    def on_click(fx, fy, what):
        if "weapon tile" in what:
            paste(frame, make_template(bgr=(200, 10, 10)), (0.24, 0.91))

    actions = FakeActions(on_click=on_click)
    cfg = ui(slots={"primary": PRIMARY, "secondary": SECONDARY})
    txn = LoadoutTransaction(actions, templates, cfg, get_frame=lambda: frame)
    txn.reset({"primary": "MissingTemplate", "secondary": "Fresh"})
    run_to_done(txn)

    assert not txn.result.success  # primary failed
    assert txn.result.slots["secondary"].verified  # but secondary still went through


# --------------------------------------------------------------------------- diagnostics


def test_diagnostic_crop_saved_on_failure(tmp_path):
    diag_dir = tmp_path / "diag"
    templates = make_templates(tmp_path / "tpl", {("primary", "Gone"): (5, 5, 5)})
    actions = FakeActions()
    txn = LoadoutTransaction(actions, templates, ui(max_search_scrolls=1), get_frame=lambda: blank(),
                              diagnostics_dir=diag_dir)
    txn.reset({"primary": "Gone"})
    run_to_done(txn)
    saved = list(diag_dir.glob("*_primary.png"))
    assert len(saved) == 1


def test_no_diagnostic_saved_on_success(tmp_path):
    diag_dir = tmp_path / "diag"
    templates = make_templates(tmp_path / "tpl", {("primary", "Rifle"): (10, 200, 10)})
    frame = blank()
    paste(frame, make_template(bgr=(10, 200, 10)), (0.02, 0.91))
    actions = FakeActions()
    txn = LoadoutTransaction(actions, templates, ui(), get_frame=lambda: frame, diagnostics_dir=diag_dir)
    txn.reset({"primary": "Rifle"})
    run_to_done(txn)
    assert not diag_dir.exists() or not list(diag_dir.glob("*.png"))


def test_weapon_template_path_sanitizes_the_name():
    assert weapon_template_path("primary", "Grenade Launcher") == "primary/Grenade_Launcher.png"
    path = weapon_template_path("utility", "C4 (Sticky)")
    assert path.startswith("utility/C4") and path.endswith(".png")
    assert "(" not in path and ")" not in path and " " not in path
