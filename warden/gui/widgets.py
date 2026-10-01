"""Small reusable widget builders shared by every page - keeps the pages
themselves focused on layout/behavior instead of boilerplate styling.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget


def card(margins: tuple[int, int, int, int] = (18, 16, 18, 16), spacing: int = 10) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame(objectName="Card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(*margins)
    layout.setSpacing(spacing)
    return frame, layout


def page_header(title: str) -> QLabel:
    label = QLabel(title, objectName="PageTitle")
    return label


def muted(text: str) -> QLabel:
    label = QLabel(text, objectName="Muted")
    label.setWordWrap(True)
    return label


def section_label(text: str) -> QLabel:
    label = QLabel(text.upper())
    label.setObjectName("Section")
    return label


class StatTile(QFrame):
    """A small 'number + caption' tile, e.g. for the counters row on Home."""

    def __init__(self, caption: str, value: str = "0"):
        super().__init__(objectName="Card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(2)
        self.value_label = QLabel(value)
        self.value_label.setObjectName("StatValue")
        self.caption_label = QLabel(caption.upper())
        self.caption_label.setObjectName("Muted")
        layout.addWidget(self.value_label)
        layout.addWidget(self.caption_label)

    def set_value(self, value: str) -> None:
        self.value_label.setText(value)


class StatusChip(QLabel):
    STATES = {
        "ready": ("Ready", "muted"),
        "running": ("Running", "success"),
        "queueing": ("Queueing", "accent"),
        "in_match": ("In match", "success"),
        "recovering": ("Recovering", "warn"),
        "paused": ("Paused", "warn"),
        "stopped": ("Stopped", "muted"),
    }

    def __init__(self):
        super().__init__("Ready")
        self.setObjectName("StatusChip")
        self.setAlignment(Qt.AlignCenter)
        self.set_state("ready")

    def set_state(self, key: str) -> None:
        text, tone = self.STATES.get(key, (key.title(), "muted"))
        self.setText(text)
        self.setProperty("tone", tone)
        self.style().unpolish(self)
        self.style().polish(self)


def row(*widgets: QWidget, stretch_last: bool = False, spacing: int = 10) -> QWidget:
    container = QWidget()
    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(spacing)
    for w in widgets:
        layout.addWidget(w)
    if stretch_last:
        layout.addStretch(1)
    return container
