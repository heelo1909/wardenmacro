"""Diagnostics - HANDOFF section 7.6."""

from __future__ import annotations

import contextlib
import io

from PySide6.QtWidgets import QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from warden.gui import theme
from warden.gui.context import AppContext
from warden.gui.widgets import card, page_header


class DiagnosticsPage(QWidget):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)
        layout.addWidget(page_header("Diagnostics"))

        body, body_layout = card()
        self.run_btn = QPushButton("Run diagnostics", objectName="Primary")
        self.run_btn.clicked.connect(self._run)
        body_layout.addWidget(self.run_btn)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setStyleSheet(f"font-family: {theme.MONOSPACE_STACK};")
        body_layout.addWidget(self.output)
        layout.addWidget(body, 1)
        self._run()

    def _run(self) -> None:
        from warden.tools import diagnostics_cli

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            diagnostics_cli.run()
        self.output.setPlainText(buf.getvalue())
