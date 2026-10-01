"""Main window shell: left sidebar + the real pages from HANDOFF section 7."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
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
from warden.core.events import Event
from warden.gui import theme
from warden.gui.bridge import BusBridge
from warden.gui.context import AppContext
from warden.gui.mini_overlay import MiniOverlay
from warden.gui.pages.calibration import CalibrationPage
from warden.gui.pages.diagnostics import DiagnosticsPage
from warden.gui.pages.history import HistoryPage
from warden.gui.pages.home import HomePage
from warden.gui.pages.loadout import LoadoutPage
from warden.gui.pages.settings import SettingsPage
from warden.gui.summary_dialog import SummaryDialog
from warden.platform.hotkeys import Hotkeys

log = logging.getLogger(__name__)

PAGES = ("Home", "Loadout", "Settings", "Calibration", "History", "Diagnostics")


class MainWindow(QMainWindow):
    def __init__(self, config: LoadedConfig | None = None, bus=None):
        super().__init__()
        self.config = config
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.resize(1120, 720)
        self.setMinimumSize(880, 560)
        self.setStyleSheet(theme.stylesheet())

        self.ctx: AppContext | None = None
        self._incidents: list[str] = []
        self._hotkeys: Hotkeys | None = None
        self.mini_overlay: MiniOverlay | None = None
        self._event_bridge: BusBridge | None = None

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

        if config is not None:
            from warden.core.events import bus as default_bus

            self.ctx = AppContext(config, bus or default_bus())
            pages = {
                "Home": HomePage(self.ctx, on_start=self._start, on_pause=self._pause,
                                  on_resume=self._resume, on_stop=self._stop),
                "Loadout": LoadoutPage(self.ctx),
                "Settings": SettingsPage(self.ctx),
                "Calibration": CalibrationPage(self.ctx),
                "History": HistoryPage(self.ctx),
                "Diagnostics": DiagnosticsPage(self.ctx),
            }
            self.home_page: HomePage | None = pages["Home"]
            self._event_bridge = BusBridge(self.ctx.bus, min_level="info")
            self._event_bridge.event.connect(self._on_bus_event)
            self.mini_overlay = MiniOverlay(self.ctx)
        else:
            pages = {name: _placeholder_page(name) for name in PAGES}
            self.home_page = None

        for index, name in enumerate(PAGES):
            button = QPushButton(name, objectName="NavButton", checkable=True)
            button.setCursor(Qt.PointingHandCursor)
            self.nav.addButton(button, index)
            side.addWidget(button)
            self.stack.addWidget(pages[name])
        self.nav.idClicked.connect(self.stack.setCurrentIndex)
        self.nav.button(0).setChecked(True)
        side.addStretch(1)

        row.addWidget(sidebar)
        row.addWidget(self.stack, 1)
        self.setCentralWidget(root)

        if config is not None and config.app.gui.always_on_top:
            self.setWindowFlag(Qt.WindowStaysOnTop, True)

        preset = config.preset.name if config else "-"
        self.statusBar().showMessage(f"Ready  ·  preset: {preset}")

        if config is not None:
            self._setup_hotkeys()

    # -- hotkeys -------------------------------------------------------

    def _setup_hotkeys(self) -> None:
        hk = self.config.app.hotkeys
        self._hotkeys = Hotkeys({
            hk.start: self._start, hk.pause: self._toggle_pause,
            hk.stop: self._stop, hk.screenshot: self._screenshot,
        })
        self._hotkeys.start()

    def closeEvent(self, event) -> None:
        if self._hotkeys:
            self._hotkeys.stop()
        if self.ctx and self.ctx.tick_loop:
            self.ctx.tick_loop.stop()
        super().closeEvent(event)

    # -- session control (also reachable via hotkeys) -------------------------------------------------------

    def _start(self) -> None:
        if self.ctx is None:
            return
        self._incidents.clear()
        loop = self.ctx.ensure_tick_loop()
        loop.start()
        if self.mini_overlay is not None:
            self.mini_overlay.mark_started()
            if self.config.app.gui.mini_overlay:
                self.mini_overlay.dock_outside(loop._client_rect)
                self.mini_overlay.show()
        if self.config.app.gui.minimize_on_start:
            self.showMinimized()
        self.statusBar().showMessage("Running")

    def _toggle_pause(self) -> None:
        if self.ctx is None or self.ctx.tick_loop is None:
            return
        from warden.core.state_machine import State

        if self.ctx.tick_loop.sm.state is State.PAUSED:
            self._resume()
        else:
            self._pause()

    def _pause(self) -> None:
        if self.ctx and self.ctx.tick_loop:
            self.ctx.tick_loop.pause()
            self.statusBar().showMessage("Paused")

    def _resume(self) -> None:
        if self.ctx and self.ctx.tick_loop:
            self.ctx.tick_loop.resume()
            self.statusBar().showMessage("Running")

    def _stop(self) -> None:
        if self.ctx is None or self.ctx.tick_loop is None:
            return
        loop = self.ctx.tick_loop
        counters = loop.sm.counters
        duration = self.home_page.session_duration() if self.home_page else 0.0
        in_match = self.home_page.in_match_seconds() if self.home_page else 0.0
        loop.stop()
        if self.mini_overlay is not None:
            self.mini_overlay.hide()
        self.showNormal()
        self.statusBar().showMessage("Stopped")
        dialog = SummaryDialog(duration, in_match, counters, list(self._incidents), parent=self)
        dialog.exec()

    def _screenshot(self) -> None:
        if self.ctx is None or self.ctx.tick_loop is None:
            return
        loop = self.ctx.tick_loop
        if loop._client_rect is None:
            return
        try:
            import time

            import cv2

            from warden import paths

            frame = loop.capturer.grab(loop._client_rect)
            out = paths.data_dir("diagnostics") / f"screenshot_{time.strftime('%Y%m%d_%H%M%S')}.png"
            cv2.imwrite(str(out), frame)
            self.ctx.bus.emit("screenshot.saved", f"saved screenshot to {out}", level="success")
        except Exception:
            log.exception("screenshot failed")

    def _on_bus_event(self, event: Event) -> None:
        if event.topic == "incident":
            self._incidents.append(event.message)
        elif event.topic == "schedule.target_reached":
            self._handle_target_reached(event.data.get("preset_id"))

    def _handle_target_reached(self, preset_id: str | None) -> None:
        """Contract queue (HANDOFF §8.11): advance to the next preset and keep going."""
        if self.ctx is None or preset_id != self.ctx.preset_id:
            return
        if not self.ctx.advance_contract_queue():
            return
        self.ctx.bus.emit("schedule.queue_advanced", f"contract queue: advancing to '{self.ctx.preset_id}'",
                          level="success")
        if self.ctx.tick_loop is not None:
            self.ctx.tick_loop.cancel_shutdown_countdown()
        if self.home_page is not None:
            self.home_page._refresh_loadout_card()
            self.home_page._refresh_contract_label()
            self.home_page._refresh_resume_banner()
        self._start()


def _placeholder_page(title: str) -> QWidget:
    from warden.gui.widgets import card, muted, page_header

    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(28, 24, 28, 24)
    layout.setSpacing(16)
    layout.addWidget(page_header(title))
    frame, inner = card()
    inner.addWidget(muted("No config loaded."))
    layout.addWidget(frame)
    layout.addStretch(1)
    return page
