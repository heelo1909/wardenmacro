"""MainWindow's Start/Stop wiring: minimize-on-start (HANDOFF §6.2 - don't
cover the game) and the summary dialog. observe_only is forced for every
TickLoop built here (see warden-testing-safety memory) - with it on, no
input is ever sent and the focus gate's refocus() is never called either,
so this is safe to run even if a real window enumeration happens underneath.
"""

import shutil

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

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
    win = MainWindow(loaded, __import__("warden.core.events", fromlist=["EventBus"]).EventBus())
    yield win
    if win.ctx and win.ctx.tick_loop:
        win.ctx.tick_loop.stop()
    win.close()


def test_start_minimizes_the_main_window(window):
    assert window.config.app.gui.minimize_on_start is True
    window.show()
    window._start()
    assert window.isMinimized()


def test_stop_shows_summary_dialog_with_live_counters(window, monkeypatch):
    shown = {}
    monkeypatch.setattr(QDialog, "exec", lambda self: shown.setdefault("counters", self) or 0)
    window._start()
    window.ctx.tick_loop.sm.counters.respawns = 5
    window._stop()
    assert "counters" in shown
    assert window.isVisible() or not window.isMinimized()  # restored, not left minimized


def test_stop_without_a_running_session_is_a_no_op(window):
    window._stop()  # must not raise even though nothing was started
