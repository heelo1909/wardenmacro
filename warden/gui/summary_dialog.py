"""End-of-session summary - HANDOFF section 7.7."""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QListWidget, QVBoxLayout

from warden.gui.widgets import muted, section_label


def _format_hms(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


class SummaryDialog(QDialog):
    def __init__(self, duration_s: float, in_match_s: float, counters, incidents: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Session summary")
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)

        pct = (in_match_s / duration_s * 100) if duration_s > 0 else 0
        layout.addWidget(QLabel(f"Duration: {_format_hms(duration_s)}", objectName="StatValue"))
        layout.addWidget(muted(f"In-match time: {_format_hms(in_match_s)} ({pct:.0f}%)"))

        layout.addWidget(section_label("Counters"))
        for label, value in (
            ("Respawns", counters.respawns), ("Reconnects", counters.reconnects),
            ("Re-queues", counters.re_queues), ("Loadout fixes", counters.loadout_fixes),
            ("Time lost", _format_hms(counters.time_lost_s)),
        ):
            layout.addWidget(QLabel(f"{label}: {value}"))

        layout.addWidget(section_label("Incidents"))
        incident_list = QListWidget()
        incident_list.addItems(incidents or ["(none)"])
        incident_list.setMaximumHeight(140)
        layout.addWidget(incident_list)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
