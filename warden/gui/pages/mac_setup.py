"""Mac setup - checks the three macOS permissions Warden needs (macOS only).

One row per permission: what it's for (one sentence), a status chip that
turns green when granted, and an "Open System Settings" button. If the deep
link doesn't open on this macOS version, the written steps appear instead.
Screen Recording only takes effect after Warden restarts, so a "Reopen
Warden" button is shown once it's granted.
"""

from __future__ import annotations

import logging
import subprocess
from collections.abc import Callable

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from warden.gui.widgets import card, muted, page_header
from warden.platform.permissions_mac import PERMISSIONS, PermissionChecker, relaunch_command

log = logging.getLogger(__name__)

GRANTED = "✓  Allowed"
MISSING = "Not allowed yet"


class _PermissionRow(QWidget):
    def __init__(self, perm, on_open: Callable[[str], None]):
        super().__init__()
        self.perm = perm
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 4, 0, 4)
        outer.setSpacing(4)
        top = QHBoxLayout()
        top.setSpacing(10)
        self.title = QLabel(perm.title, objectName="CardTitle")
        self.chip = QLabel(MISSING, objectName="StatusChip")
        self.button = QPushButton("Open System Settings")
        self.button.clicked.connect(lambda: on_open(perm.key))
        top.addWidget(self.title)
        top.addWidget(self.chip)
        top.addStretch(1)
        top.addWidget(self.button)
        outer.addLayout(top)
        self.why = muted(perm.why)
        outer.addWidget(self.why)
        self.steps = muted(perm.steps)
        self.steps.setHidden(True)
        outer.addWidget(self.steps)
        self.granted = False

    def set_granted(self, granted: bool) -> None:
        self.granted = granted
        self.chip.setText(GRANTED if granted else MISSING)
        self.chip.setProperty("tone", "success" if granted else "warn")
        self.chip.style().unpolish(self.chip)
        self.chip.style().polish(self.chip)
        self.button.setHidden(granted)
        if granted:
            self.steps.setHidden(True)

    def show_steps(self) -> None:
        self.steps.setHidden(False)


class MacSetupPage(QWidget):
    def __init__(self, checker: PermissionChecker | None = None,
                 relaunch: Callable[[], None] | None = None, poll_ms: int = 2000):
        super().__init__()
        self.checker = checker or PermissionChecker()
        self._relaunch = relaunch or _relaunch_warden
        self._initial: dict[str, bool] | None = None
        self._opened: set[str] = set()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)
        layout.addWidget(page_header("Mac setup"))
        layout.addWidget(muted(
            "macOS asks you to allow these once. Warden only uses them to see and control "
            "the Roblox window, and you can turn them off any time in System Settings. "
            "School and work Macs usually block these and aren't supported."))

        body, body_layout = card()
        self.rows: dict[str, _PermissionRow] = {}
        for perm in PERMISSIONS:
            row = _PermissionRow(perm, self._open)
            self.rows[perm.key] = row
            body_layout.addWidget(row)
        layout.addWidget(body)

        actions = QHBoxLayout()
        self.check_btn = QPushButton("Check again")
        self.check_btn.clicked.connect(self.refresh)
        self.reopen_btn = QPushButton("Reopen Warden", objectName="Primary")
        self.reopen_btn.clicked.connect(self._relaunch)
        self.reopen_btn.setHidden(True)
        actions.addWidget(self.check_btn)
        actions.addWidget(self.reopen_btn)
        actions.addStretch(1)
        layout.addLayout(actions)
        self.summary = muted("")
        layout.addWidget(self.summary)
        layout.addStretch(1)

        self.refresh()
        self._timer = QTimer(self)
        self._timer.setInterval(poll_ms)
        self._timer.timeout.connect(self.refresh)
        if poll_ms > 0:
            self._timer.start()

    def refresh(self) -> dict[str, bool]:
        status = self.checker.status()
        if self._initial is None:
            self._initial = dict(status)
        for key, row in self.rows.items():
            row.set_granted(status.get(key, False))
        # Screen Recording is only re-read by macOS when Warden starts, so it can
        # still read "not allowed" right after the user turns it on. Offer a
        # reopen once it was granted since launch, or once its Settings pane was
        # opened from here.
        needs_reopen = any(
            p.needs_reopen and not self._initial.get(p.key) and (status.get(p.key) or p.key in self._opened)
            for p in PERMISSIONS)
        self.reopen_btn.setHidden(not needs_reopen)
        if all(status.values()):
            self.summary.setText("All set - Warden has everything it needs.")
        elif needs_reopen:
            self.summary.setText("Reopen Warden so macOS applies Screen Recording.")
        else:
            missing = [p.title for p in PERMISSIONS if not status.get(p.key)]
            self.summary.setText("Still needed: " + ", ".join(missing))
        return status

    def all_granted(self) -> bool:
        return all(row.granted for row in self.rows.values())

    def _open(self, key: str) -> None:
        self._opened.add(key)
        self.checker.request(key)  # macOS's own prompt, where it has one
        opened = self.checker.open_settings(key)
        # The written steps show either way: if the deep link failed they're the
        # only way there, and if it worked people still need to know what to toggle.
        self.rows[key].show_steps()
        if not opened:
            log.info("System Settings deep link for %s didn't open; showing written steps", key)
        self.refresh()


def _relaunch_warden() -> None:
    from PySide6.QtWidgets import QApplication

    try:
        subprocess.Popen(relaunch_command(), close_fds=True)
    except Exception:
        log.exception("couldn't relaunch Warden")
        return
    QApplication.quit()
