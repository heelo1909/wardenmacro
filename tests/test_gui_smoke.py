import shutil

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from warden.config import load_all  # noqa: E402
from warden.gui import theme  # noqa: E402
from warden.gui.main_window import PAGES, MainWindow  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_main_window_builds_themed_shell(qapp, bundled_config, tmp_path):
    # A temp copy: AppContext (built inside MainWindow since config is not
    # None) can write settings back to app_path/preset_path, which must
    # never point at the real checked-in config/ files.
    work = tmp_path / "config"
    shutil.copytree(bundled_config, work)
    loaded = load_all(work / "default.yaml")
    loaded.app.observe_only = True
    window = MainWindow(loaded)
    assert window.stack.count() == len(PAGES)
    assert theme.ACCENT in window.styleSheet() and theme.BG in window.styleSheet()
    window.nav.button(3).click()
    assert window.stack.currentIndex() == 3
    assert "glass" in window.statusBar().currentMessage().lower()
    window.close()
