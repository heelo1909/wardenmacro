"""MainWindow advances the contract queue when TickLoop reports a target
reached (HANDOFF §8.11). observe_only forced throughout - see
warden-testing-safety memory.
"""

import shutil

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from warden.config import load_all  # noqa: E402
from warden.gui.main_window import MainWindow  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(qapp, bundled_config, tmp_path):
    work = tmp_path / "config"
    shutil.copytree(bundled_config, work)
    loaded = load_all(work / "default.yaml")
    loaded.app.observe_only = True
    loaded.app.contract_queue = ["glass_wrap", "random"]
    win = MainWindow(loaded, __import__("warden.core.events", fromlist=["EventBus"]).EventBus())
    yield win
    if win.ctx and win.ctx.tick_loop:
        win.ctx.tick_loop.stop()
    win.close()


def test_target_reached_advances_to_the_next_preset_and_restarts(window):
    assert window.ctx.preset_id == "glass_wrap"
    window._start()
    first_loop = window.ctx.tick_loop

    window.ctx.bus.emit("schedule.target_reached", "target reached for 'glass_wrap'",
                        level="success", preset_id="glass_wrap")

    assert window.ctx.preset_id == "random"
    assert window.ctx.tick_loop is not first_loop  # a fresh TickLoop was started for the new preset
    assert window.ctx.tick_loop.sm.state.name != "STOPPED"


def test_target_reached_for_a_preset_not_in_queue_is_ignored(window):
    window.ctx.app.contract_queue = []
    window._start()
    first_loop = window.ctx.tick_loop
    window.ctx.bus.emit("schedule.target_reached", "x", level="success", preset_id="glass_wrap")
    assert window.ctx.preset_id == "glass_wrap"
    assert window.ctx.tick_loop is first_loop  # nothing restarted


def test_target_reached_event_for_a_different_preset_is_ignored(window):
    window._start()
    first_loop = window.ctx.tick_loop
    window.ctx.bus.emit("schedule.target_reached", "x", level="success", preset_id="some_other_preset")
    assert window.ctx.preset_id == "glass_wrap"
    assert window.ctx.tick_loop is first_loop
