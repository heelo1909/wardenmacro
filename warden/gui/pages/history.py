"""History - HANDOFF section 7.5.

Full cross-session history (section 9's sessions/<timestamp>.json) lands in
Phase 6; for now this page shows the current session's state timeline live,
which is still useful and exercises the same event-bus plumbing Phase 6's
persisted view will reuse.
"""

from __future__ import annotations

import time

from PySide6.QtWidgets import QHeaderView, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from warden.core.events import Event
from warden.gui.bridge import BusBridge
from warden.gui.context import AppContext
from warden.gui.widgets import card, muted, page_header, section_label


class HistoryPage(QWidget):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)
        layout.addWidget(page_header("History"))
        layout.addWidget(muted("Full session-to-session history arrives with Phase 6 persistence. "
                               "This table is the current session's live state timeline."))

        table_card, table_layout = card()
        table_layout.addWidget(section_label("This session's timeline"))
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Time", "Transition", "Cause"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        table_layout.addWidget(self.table)
        layout.addWidget(table_card, 1)

        self.bridge = BusBridge(ctx.bus, min_level="info")
        self.bridge.event.connect(self._on_event)

    def _on_event(self, event: Event) -> None:
        if event.topic != "state.transition":
            return
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(time.strftime("%H:%M:%S", time.localtime(event.ts))))
        self.table.setItem(row, 1, QTableWidgetItem(f"{event.data.get('frm', '?')} -> {event.data.get('to', '?')}"))
        self.table.setItem(row, 2, QTableWidgetItem(str(event.data.get("cause", ""))))
        self.table.scrollToBottom()
