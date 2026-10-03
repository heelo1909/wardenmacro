"""History - HANDOFF section 7.5.

Past-session summaries (section 9's sessions/<timestamp>.json, written once
per session by PersistenceManager.end_session) back the "all sessions" chart
and table below; the last card is still the current session's live state
timeline, which the persisted view above doesn't replace - it's the one
place to watch *this* run transition state by state as it happens.
"""

from __future__ import annotations

import time

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHeaderView, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from warden.core.events import Event
from warden.gui.bridge import BusBridge
from warden.gui.context import AppContext
from warden.gui.widgets import SessionHistoryChart, card, page_header, section_label

_EMPTY_TIMELINE_ROW = "no transitions yet this session - they'll appear here as they happen"


class HistoryPage(QWidget):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)
        layout.addWidget(page_header("History"))

        chart_card, chart_layout = card()
        chart_layout.addWidget(section_label("All sessions"))
        self.chart = SessionHistoryChart(max_bars=24)
        chart_layout.addWidget(self.chart)
        layout.addWidget(chart_card)

        sessions_card, sessions_layout = card()
        sessions_layout.addWidget(section_label("Past sessions"))
        self.sessions_table = QTableWidget(0, 5)
        self.sessions_table.setHorizontalHeaderLabels(["Ended", "Preset", "Duration", "In-match", "Incidents"])
        self.sessions_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.sessions_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.sessions_table.verticalHeader().setVisible(False)
        self.sessions_table.setEditTriggers(QTableWidget.NoEditTriggers)
        sessions_layout.addWidget(self.sessions_table)
        layout.addWidget(sessions_card)
        self.refresh_sessions()

        table_card, table_layout = card()
        table_layout.addWidget(section_label("This session's timeline"))
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Time", "Transition", "Cause"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        table_layout.addWidget(self.table)
        layout.addWidget(table_card, 1)
        self._show_empty_timeline_row()

        self.bridge = BusBridge(ctx.bus, min_level="info")
        self.bridge.event.connect(self._on_event)

    def apply_scale(self, scale: float) -> None:
        self.chart.set_scale(scale)

    def refresh_sessions(self) -> None:
        """Re-reads sessions/*.json. Cheap enough to just call whenever this
        page might be visible again (MainWindow does, on every nav click)."""
        summaries = self.ctx.session_summaries()
        self.chart.set_sessions(summaries)
        self.sessions_table.setRowCount(0)
        for summary in reversed(summaries):  # newest first
            row = self.sessions_table.rowCount()
            self.sessions_table.insertRow(row)
            ended = time.strftime("%b %d, %H:%M", time.localtime(summary.get("ended_at", 0)))
            duration = _format_hms(summary.get("duration_s", 0.0))
            in_match = _format_hms(summary.get("in_match_s", 0.0))
            incidents = summary.get("incidents") or []
            label = summary.get("label") or summary.get("preset_id") or "-"
            for col, text in enumerate((ended, label, duration, in_match, str(len(incidents)))):
                self.sessions_table.setItem(row, col, QTableWidgetItem(text))

    def _on_event(self, event: Event) -> None:
        if event.topic != "state.transition":
            return
        if self.table.rowCount() == 1 and self.table.item(0, 1) is not None \
                and self.table.item(0, 1).text() == _EMPTY_TIMELINE_ROW:
            self.table.setRowCount(0)  # drop the empty-state placeholder row
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(time.strftime("%H:%M:%S", time.localtime(event.ts))))
        self.table.setItem(row, 1, QTableWidgetItem(f"{event.data.get('frm', '?')} -> {event.data.get('to', '?')}"))
        self.table.setItem(row, 2, QTableWidgetItem(str(event.data.get("cause", ""))))
        self.table.scrollToBottom()

    def _show_empty_timeline_row(self) -> None:
        self.table.setRowCount(1)
        placeholder = QTableWidgetItem(_EMPTY_TIMELINE_ROW)
        placeholder.setFlags(Qt.ItemIsEnabled)
        self.table.setItem(0, 1, placeholder)


def _format_hms(seconds) -> str:
    seconds = max(0, int(seconds or 0))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"
