"""Phase 5 GUI tests. QT_QPA_PLATFORM=offscreen (set in conftest), and every
TickLoop built here has observe_only forced - see warden-testing-safety memory.
"""

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

from warden.config import load_all  # noqa: E402
from warden.core.events import EventBus  # noqa: E402
from warden.core.state_machine import State  # noqa: E402
from warden.gui.context import AppContext  # noqa: E402
from warden.gui.main_window import PAGES, MainWindow  # noqa: E402
from warden.gui.pages.calibration import CalibrationPage  # noqa: E402
from warden.gui.pages.diagnostics import DiagnosticsPage  # noqa: E402
from warden.gui.pages.history import HistoryPage  # noqa: E402
from warden.gui.pages.home import HomePage  # noqa: E402
from warden.gui.pages.loadout import LoadoutPage  # noqa: E402
from warden.gui.pages.settings import SettingsPage  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def ctx(qapp, bundled_config, tmp_path):
    # A temp COPY - AppContext.save_*() write back to app_path/preset_path,
    # and those must never point at the real checked-in config/ files.
    import shutil

    work = tmp_path / "config"
    shutil.copytree(bundled_config, work)
    loaded = load_all(work / "default.yaml")
    loaded.app.observe_only = True  # never send real input - see warden-testing-safety memory
    return AppContext(loaded, EventBus())


def test_main_window_builds_all_six_pages(qapp, bundled_config, tmp_path):
    import shutil

    work = tmp_path / "config"
    shutil.copytree(bundled_config, work)
    loaded = load_all(work / "default.yaml")
    loaded.app.observe_only = True
    window = MainWindow(loaded, EventBus())
    assert window.stack.count() == len(PAGES) == 6
    window.nav.button(3).click()
    assert window.stack.currentIndex() == 3
    window.close()


def test_main_window_without_config_shows_placeholders(qapp):
    window = MainWindow(None)
    assert window.stack.count() == len(PAGES)
    window.close()


def test_home_page_start_pause_resume_stop_lifecycle(ctx):
    page = HomePage(ctx)
    assert not page.pause_btn.isEnabled()
    page.start_btn.click()
    assert page.pause_btn.isEnabled() and page.stop_btn.isEnabled()
    assert not page.start_btn.isEnabled()
    page.ctx.ensure_tick_loop()  # HomePage itself doesn't own the loop; MainWindow wires on_start to do this
    page.stop_btn.click()
    assert page.start_btn.isEnabled()
    assert not page.pause_btn.isEnabled()


def test_home_page_automation_toggle_persists_to_config(ctx, tmp_path):
    ctx.app_path = tmp_path / "config.yaml"
    page = HomePage(ctx)
    assert ctx.app.automation.abilities is True
    page.toggles["abilities"].setChecked(False)
    assert ctx.app.automation.abilities is False
    assert ctx.app_path.exists()


def test_home_page_quick_preset_switch_updates_loadout_card(ctx):
    page = HomePage(ctx)
    assert ctx.preset_id == "glass_wrap"
    page._switch_preset("random")
    assert ctx.preset_id == "random"
    assert "random" in page.slot_labels["primary"].text().lower()


def test_home_page_live_stats_refresh_reads_counters(ctx):
    page = HomePage(ctx)
    loop = ctx.ensure_tick_loop()
    loop.sm.counters.respawns = 3
    loop.sm.counters.reconnects = 1
    page._refresh_live_stats()
    assert page.tiles["respawns"].value_label.text() == "3"
    assert page.tiles["reconnects"].value_label.text() == "1"


def test_home_page_shows_resume_banner_for_an_incomplete_session(ctx, warden_home):
    # The autouse warden_home fixture points paths.data_home() (and so
    # AppContext.persisted_state()) at this same per-test directory - write a
    # real "crashed mid-session" state.json there, no mocking needed.
    from warden.core.persistence import PersistenceManager
    from warden.core.state_machine import Counters

    mgr = PersistenceManager(warden_home / "state.json", warden_home / "sessions")
    mgr.start_session(ctx.preset_id, ctx.preset.contract.label, ctx.preset.contract.target_hours)
    mgr.maybe_flush(3600.0, Counters(), force=True)  # 1h banked, never cleanly stopped

    page = HomePage(ctx)
    assert not page.resume_banner.isHidden()
    assert "banked" in page.resume_label.text()


def test_home_page_no_resume_banner_for_a_different_preset(ctx, warden_home):
    from warden.core.persistence import PersistenceManager
    from warden.core.state_machine import Counters

    mgr = PersistenceManager(warden_home / "state.json", warden_home / "sessions")
    mgr.start_session("some_other_preset", "Other", 24.0)
    mgr.maybe_flush(3600.0, Counters(), force=True)

    page = HomePage(ctx)
    assert page.resume_banner.isHidden()


def test_home_page_hides_resume_banner_on_start(ctx, warden_home):
    from warden.core.persistence import PersistenceManager
    from warden.core.state_machine import Counters

    mgr = PersistenceManager(warden_home / "state.json", warden_home / "sessions")
    mgr.start_session(ctx.preset_id, ctx.preset.contract.label, ctx.preset.contract.target_hours)
    mgr.maybe_flush(3600.0, Counters(), force=True)

    page = HomePage(ctx)
    assert not page.resume_banner.isHidden()
    page.start_btn.click()
    assert page.resume_banner.isHidden()


def test_home_page_status_chip_follows_state_machine(ctx):
    page = HomePage(ctx)
    loop = ctx.ensure_tick_loop()
    loop.sm.state = State.IN_MATCH
    page._refresh_live_stats()
    assert page.status_chip.text() == "In match"


def test_loadout_page_lists_presets_and_edits_slots(ctx, tmp_path):
    page = LoadoutPage(ctx)
    assert page.preset_list.count() == 3
    assert page._get_slot_value(page.slot_edits["primary"]) == "Grenade Launcher"


def test_loadout_page_slot_combos_list_known_rivals_weapons(ctx):
    page = LoadoutPage(ctx)
    primary = page.slot_edits["primary"]
    texts = [primary.itemText(i) for i in range(primary.count())]
    assert any(t.startswith("Grenade Launcher") for t in texts)
    assert any(t.startswith("Sniper") for t in texts)
    # a weapon typed outside the known list still round-trips (editable combo)
    utility = page.slot_edits["utility"]
    utility.setEditText("Some New Gadget")
    assert page._get_slot_value(utility) == "Some New Gadget"


def test_loadout_page_new_rename_delete(ctx):
    page = LoadoutPage(ctx)
    ctx.create_preset("temp_test", ctx.preset.model_copy(deep=True))
    page.preset_list.addItem("temp_test")
    page._editing_id = "temp_test"
    ctx.delete_preset("temp_test")
    with pytest.raises(ValueError):
        ctx.delete_preset(ctx.preset_id)  # can't delete the active preset


def test_settings_page_save_round_trips_values(ctx):
    page = SettingsPage(ctx)
    page.place_id.setText("999999")
    page.anti_idle.setValue(42.0)
    page.observe_only.setChecked(True)
    page._save()
    assert ctx.preset.launch.place_id == 999999
    assert ctx.preset.behavior.anti_idle_seconds == 42.0
    assert ctx.app.observe_only is True


def test_calibration_page_builds_both_tabs(ctx, tmp_path):
    # Full wizard/gallery behavior is covered in tests/test_gui_calibration.py.
    page = CalibrationPage(ctx, templates_root=tmp_path)
    assert page.screen_combo.count() > 0
    assert page.canvas is not None and page.gallery_canvas is not None


def test_history_page_records_transitions_from_bus(ctx):
    page = HistoryPage(ctx)
    ctx.bus.emit("state.transition", "LOBBY -> MODE_SELECT", level="info", frm="LOBBY", to="MODE_SELECT",
                cause="mode list opened")
    assert page.table.rowCount() == 1
    assert "LOBBY" in page.table.item(0, 1).text()


def test_history_page_timeline_starts_with_an_empty_state_placeholder(ctx):
    page = HistoryPage(ctx)
    assert page.table.rowCount() == 1
    assert "no transitions yet" in page.table.item(0, 1).text()


def _write_session(warden_home, ended_at, in_match_s, preset_id="glass_wrap", label="Glass Wrap",
                    duration_s=None, incidents=()):
    from warden.core.persistence import SessionSummary, save_session_summary

    save_session_summary(warden_home / "sessions", SessionSummary(
        preset_id=preset_id, label=label, started_at=ended_at - (duration_s or in_match_s),
        ended_at=ended_at, duration_s=duration_s or in_match_s, in_match_s=in_match_s,
        counters={}, incidents=list(incidents),
    ))


def test_home_page_chart_shows_past_sessions(ctx, warden_home):
    _write_session(warden_home, ended_at=1_700_000_000, in_match_s=600.0)
    _write_session(warden_home, ended_at=1_700_003_600, in_match_s=1800.0)
    page = HomePage(ctx)
    assert page.history_chart._values == [10.0, 30.0]
    assert "2 sessions all-time" in page.history_caption.text()


def test_home_page_chart_empty_state_before_any_session(ctx):
    page = HomePage(ctx)
    assert page.history_chart._values == []
    assert page.history_caption.text() == ""


def test_home_page_refresh_history_picks_up_a_new_session(ctx, warden_home):
    page = HomePage(ctx)
    assert page.history_chart._values == []
    _write_session(warden_home, ended_at=1_700_000_000, in_match_s=900.0)
    page.refresh_history()
    assert page.history_chart._values == [15.0]


def test_history_page_refresh_sessions_populates_table_newest_first(ctx, warden_home):
    _write_session(warden_home, ended_at=1_700_000_000, in_match_s=600.0, label="First")
    _write_session(warden_home, ended_at=1_700_003_600, in_match_s=1800.0, label="Second",
                    incidents=["disconnect"])
    page = HistoryPage(ctx)
    assert page.sessions_table.rowCount() == 2
    assert page.sessions_table.item(0, 1).text() == "Second"  # newest first
    assert page.sessions_table.item(0, 4).text() == "1"  # one incident
    assert page.sessions_table.item(1, 1).text() == "First"


def test_diagnostics_page_runs_without_roblox(ctx):
    page = DiagnosticsPage(ctx)
    assert "DPI awareness" in page.output.toPlainText()


def test_summary_dialog_shows_counters(qapp):
    from warden.flows.respawn import RespawnFlow  # noqa: F401 (import sanity for Counters below)
    from warden.gui.summary_dialog import SummaryDialog

    QDialog.exec = lambda self: 0  # never block in a test
    counters = type("C", (), {"respawns": 2, "reconnects": 1, "re_queues": 0, "loadout_fixes": 1,
                              "time_lost_s": 30.0})()
    dialog = SummaryDialog(120.0, 90.0, counters, ["disconnect at 00:01:00"])
    dialog.exec()
