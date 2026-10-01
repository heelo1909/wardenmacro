"""Main window shell: left sidebar + stacked pages (filled in during Phase 5)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from warden import APP_NAME, __version__
from warden.config import LoadedConfig
from warden.gui import theme

PAGES = ("Home", "Loadout", "Settings", "Calibration", "History", "Diagnostics")


def _placeholder_page(title: str, blurb: str) -> QWidget:
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(28, 24, 28, 24)
    layout.setSpacing(16)
    heading = QLabel(title)
    heading.setObjectName("PageTitle")
    layout.addWidget(heading)
    card = QFrame()
    card.setObjectName("Card")
    card_layout = QVBoxLayout(card)
    card_layout.setContentsMargins(20, 18, 20, 18)
    note = QLabel(blurb)
    note.setObjectName("Muted")
    note.setWordWrap(True)
    card_layout.addWidget(note)
    layout.addWidget(card)
    layout.addStretch(1)
    return page


class MainWindow(QMainWindow):
    def __init__(self, config: LoadedConfig | None = None):
        super().__init__()
        self.config = config
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.resize(1120, 720)
        self.setMinimumSize(880, 560)
        self.setStyleSheet(theme.stylesheet())

        root = QWidget(objectName="Root")
        row = QHBoxLayout(root)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        sidebar = QWidget(objectName="Sidebar")
        sidebar.setFixedWidth(196)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(0, 0, 0, 12)
        side.setSpacing(0)
        side.addWidget(QLabel(APP_NAME, objectName="Wordmark"))

        self.stack = QStackedWidget()
        self.nav = QButtonGroup(self)
        self.nav.setExclusive(True)
        for index, name in enumerate(PAGES):
            button = QPushButton(name, objectName="NavButton", checkable=True)
            button.setCursor(Qt.PointingHandCursor)
            self.nav.addButton(button, index)
            side.addWidget(button)
            self.stack.addWidget(_placeholder_page(name, f"The {name} page arrives in a later build phase."))
        self.nav.idClicked.connect(self.stack.setCurrentIndex)
        self.nav.button(0).setChecked(True)
        side.addStretch(1)

        row.addWidget(sidebar)
        row.addWidget(self.stack, 1)
        self.setCentralWidget(root)

        preset = config.preset.name if config else "-"
        self.statusBar().showMessage(f"Ready  ·  preset: {preset}")
