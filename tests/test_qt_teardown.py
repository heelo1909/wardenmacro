"""BUG-001: pytest must tear Qt down cleanly after GUI tests.

Runs in a child process so shutting down its QApplication can't affect the
QApplication the other GUI tests in this session share.
"""

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

CHILD = textwrap.dedent(
    """
    import sys
    sys.path.insert(0, {tests!r})
    from PySide6.QtWidgets import QApplication, QLabel, QWidget
    from qt_teardown import shutdown_qt_app

    app = QApplication([])
    leftover = QWidget()          # like a page a test never deleted
    QLabel("child", leftover)
    leftover.show()
    QLabel("closed but not deleted").close()
    assert shutdown_qt_app() is True
    assert QApplication.instance() is None
    assert shutdown_qt_app() is False  # second call is a no-op
    print("CLEAN")
    """
)


def test_shutdown_qt_app_without_pyside_or_app_is_a_noop():
    from qt_teardown import shutdown_qt_app

    pytest.importorskip("PySide6.QtWidgets")
    from PySide6.QtWidgets import QApplication

    if QApplication.instance() is not None:
        pytest.skip("this session already has a QApplication; covered by the child-process test")
    assert shutdown_qt_app() is False


def test_shutdown_qt_app_tears_down_leftover_widgets_cleanly():
    pytest.importorskip("PySide6.QtWidgets")
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    result = subprocess.run(
        [sys.executable, "-c", CHILD.format(tests=str(ROOT / "tests"))],
        capture_output=True, text=True, timeout=60, env=env,
    )
    assert result.returncode == 0, result.stderr
    assert "CLEAN" in result.stdout
    assert "shared QObject was deleted directly" not in result.stderr


def test_conftest_shuts_qt_down_when_the_session_ends():
    import conftest

    assert hasattr(conftest, "pytest_sessionfinish")
