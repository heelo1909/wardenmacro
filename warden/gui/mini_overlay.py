"""Mini overlay - HANDOFF section 8.12: a compact always-on-top strip that
docks outside the Roblox window so the main app can stay minimized.
"""

from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from warden.core.state_machine import State
from warden.gui import theme
from warden.gui.context import AppContext


class MiniOverlay(QWidget):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setStyleSheet(f"background: {theme.CARD}; border: 1px solid {theme.BORDER}; border-radius: 8px;")
        self.setFixedSize(260, 44)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        self.timer_label = QLabel("00:00:00")
        self.state_label = QLabel("Ready")
        self.state_label.setStyleSheet(f"color: {theme.ACCENT}; font-weight: 600;")
        self.counts_label = QLabel("R0 · C0")
        self.counts_label.setObjectName("Muted")
        for w in (self.timer_label, self.state_label, self.counts_label):
            layout.addWidget(w)

        self._session_start: float | None = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(500)

    def mark_started(self) -> None:
        self._session_start = time.monotonic()

    def _refresh(self) -> None:
        if self._session_start is not None:
            elapsed = int(time.monotonic() - self._session_start)
            h, rem = divmod(elapsed, 3600)
            m, s = divmod(rem, 60)
            self.timer_label.setText(f"{h:02d}:{m:02d}:{s:02d}")
        loop = self.ctx.tick_loop
        if loop is not None:
            self.state_label.setText(loop.sm.state.value.replace("_", " ").title())
            c = loop.sm.counters
            self.counts_label.setText(f"R{c.respawns} · C{c.reconnects}")

    def dock_outside(self, client_rect) -> None:
        """Place the overlay just to the right of the Roblox client, or top-left of the screen if that won't fit."""
        if client_rect is None:
            return
        from PySide6.QtGui import QGuiApplication

        screen = QGuiApplication.primaryScreen().geometry()
        x = client_rect.right + 8
        if x + self.width() > screen.width():
            x = max(client_rect.left - self.width() - 8, 8)
        self.move(x, client_rect.top)
