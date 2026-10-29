"""B-001: pytest shuts Qt down cleanly after GUI tests (the Mac CI crashed on exit)."""

import os
import subprocess
import sys

from _util import ROOT, check, run

CHILD = """
import sys
sys.path.insert(0, {tests!r})
from PySide6.QtWidgets import QApplication, QWidget
from qt_teardown import shutdown_qt_app

QApplication([])
QWidget().show()
print("SHUT" if shutdown_qt_app() and QApplication.instance() is None else "LEFT")
"""


def main():
    conftest = (ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
    check("conftest shuts Qt down at session end",
          "def pytest_sessionfinish" in conftest and "shutdown_qt_app()" in conftest)

    try:
        import PySide6.QtWidgets  # noqa: F401
    except Exception:
        print("skip child run: PySide6 not installed")
        return
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    result = subprocess.run([sys.executable, "-c", CHILD.format(tests=str(ROOT / "tests"))],
                            capture_output=True, text=True, timeout=60, env=env)
    check("leftover widget torn down, exit 0", result.returncode == 0 and "SHUT" in result.stdout,
          (result.stdout + result.stderr)[-400:])
    check("no shared-QObject warning", "shared QObject was deleted directly" not in result.stderr)


run(main)
