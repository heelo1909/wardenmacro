import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from warden.config import load_all  # noqa: E402
from warden.gui import theme  # noqa: E402
from warden.gui.main_window import PAGES, MainWindow  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_main_window_builds_themed_shell(qapp, bundled_config):
    window = MainWindow(load_all(bundled_config / "default.yaml"))
    assert window.stack.count() == len(PAGES)
    assert theme.ACCENT in window.styleSheet() and theme.BG in window.styleSheet()
    window.nav.button(3).click()
    assert window.stack.currentIndex() == 3
    assert "glass" in window.statusBar().currentMessage().lower()
    window.close()
