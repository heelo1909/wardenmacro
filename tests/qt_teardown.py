"""Tear Qt down in a fixed order at the end of a test session (BUG-001).

GUI tests leave windows and pages behind. Left to the interpreter, the
QApplication can be destroyed before those widgets, which crashed pytest on
GitHub's macOS 15 runners ("shared QObject was deleted directly", then a bus
error / segfault) after every test had passed.
"""


def shutdown_qt_app():
    """Close and delete every top-level widget, then shut the QApplication down.

    Returns True if there was an application to shut down, False otherwise
    (PySide6 missing or no QApplication created).
    """
    try:
        from PySide6.QtCore import QCoreApplication, QEvent
        from PySide6.QtWidgets import QApplication
    except Exception:  # PySide6 not installed / no GUI libs
        return False
    app = QApplication.instance()
    if app is None:
        return False
    for widget in QApplication.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
    app.shutdown()
    return True
