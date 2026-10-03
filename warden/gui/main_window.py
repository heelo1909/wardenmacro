"""Main window shell: left sidebar + the real pages from HANDOFF section 7."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QMessageBox,
    QScrollArea,
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

# The layout is designed at this size; smaller windows scale fonts/spacing
# down (never below MIN_SCALE) and anything that still doesn't fit scrolls.
DESIGN_SIZE = (1120, 740)
MIN_SCALE, MAX_SCALE = 0.72, 1.2
SIDEBAR_WIDTH = 196


def ui_scale_for(width: int, height: int) -> float:
    """Font/spacing scale for a window of this size, in 0.04 steps so a
    drag-resize doesn't restyle the whole app on every pixel.
    """
    raw = min(width / DESIGN_SIZE[0], height / DESIGN_SIZE[1])
    raw = min(max(raw, MIN_SCALE), MAX_SCALE)
    return round(round(raw / 0.04) * 0.04, 2)


def _scrollable(page: QWidget) -> QScrollArea:
    area = QScrollArea(objectName="PageScroll")
    area.setWidgetResizable(True)
    page.setObjectName(page.objectName() or "Page")
    area.setFrameShape(QFrame.NoFrame)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    area.setWidget(page)
    return area


class MainWindow(QMainWindow):
    # Global hotkeys fire on pynput's own thread; Qt widgets may only be
    # touched from the GUI thread, so hotkeys go through this queued signal.
    hotkey_pressed = Signal(str)

    def __init__(self, config: LoadedConfig | None = None, bus=None):
        super().__init__()
        self.config = config
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.setMinimumSize(560, 400)
        self._fit_to_screen()
        self._scale = 0.0  # forces the first _apply_scale() to style everything
        self._scale_timer = QTimer(self)
        self._scale_timer.setSingleShot(True)
        self._scale_timer.setInterval(60)
        self._scale_timer.timeout.connect(self._apply_scale)

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
        self.sidebar = sidebar
        sidebar.setFixedWidth(SIDEBAR_WIDTH)
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
            self.stack.addWidget(_scrollable(pages[name]))
        self.pages = pages
        self.nav.idClicked.connect(self._on_nav_clicked)
        self.nav.button(0).setChecked(True)
        side.addStretch(1)

        row.addWidget(sidebar)
        row.addWidget(self.stack, 1)
        self.setCentralWidget(root)

        if config is not None and config.app.gui.always_on_top:
            self.setWindowFlag(Qt.WindowStaysOnTop, True)

        preset = config.preset.name if config else "-"
        self.statusBar().showMessage(f"Ready  ·  preset: {preset}")

        self._apply_scale()

        if config is not None:
            self._setup_hotkeys()

    # -- responsive scaling -------------------------------------------------------

    def _fit_to_screen(self) -> None:
        """Open at the design size, or 90% of the screen if that's smaller."""
        width, height = DESIGN_SIZE
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            avail = screen.availableGeometry()
            width = min(width, int(avail.width() * 0.9))
            height = min(height, int(avail.height() * 0.9))
        self.resize(max(width, self.minimumWidth()), max(height, self.minimumHeight()))

    @property
    def ui_scale(self) -> float:
        return self._scale

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._scale_timer.start()

    def _apply_scale(self) -> None:
        scale = ui_scale_for(self.width(), self.height())
        if scale == self._scale:
            return
        self._scale = scale
        self.setStyleSheet(theme.stylesheet(scale))
        # Narrow windows get a narrower sidebar too, leaving room for the page.
        self.sidebar.setFixedWidth(int(SIDEBAR_WIDTH * min(scale, 1.0)))
        margin_x, margin_y = int(28 * scale), int(24 * scale)
        for page in getattr(self, "pages", {}).values():
            if page.layout() is not None:
                page.layout().setContentsMargins(margin_x, margin_y, margin_x, margin_y)
                page.layout().setSpacing(int(16 * scale))
            if hasattr(page, "apply_scale"):
                page.apply_scale(scale)

    # -- hotkeys -------------------------------------------------------

    def _setup_hotkeys(self) -> None:
        hk = self.config.app.hotkeys
        actions = {"start": self._hotkey_start, "pause": self._toggle_pause,
                   "stop": self._stop, "screenshot": self._screenshot}
        self.hotkey_pressed.connect(lambda name: actions[name](), Qt.QueuedConnection)
        self._hotkeys = Hotkeys({
            hk.start: lambda: self.hotkey_pressed.emit("start"),
            hk.pause: lambda: self.hotkey_pressed.emit("pause"),
            hk.stop: lambda: self.hotkey_pressed.emit("stop"),
            hk.screenshot: lambda: self.hotkey_pressed.emit("screenshot"),
        })
        self._hotkeys.start()

    def closeEvent(self, event) -> None:
        if self._hotkeys:
            self._hotkeys.stop()
        if self.ctx and self.ctx.tick_loop:
            self.ctx.tick_loop.stop()
        super().closeEvent(event)

    def _on_nav_clicked(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        history = self.pages.get("History") if hasattr(self, "pages") else None
        if PAGES[index] == "History" and hasattr(history, "refresh_sessions"):
            history.refresh_sessions()

    # -- session control (also reachable via hotkeys) -------------------------------------------------------

    def _start(self, ask: bool = True) -> None:
        if self.ctx is None:
            return
        self._incidents.clear()
        loop = self.ctx.ensure_tick_loop()
        if ask and not self._confirm_calibration(loop):
            return
        loop.start()
        if self.mini_overlay is not None:
            self.mini_overlay.mark_started()
            if self.config.app.gui.mini_overlay:
                self.mini_overlay.dock_outside(loop._client_rect)
                self.mini_overlay.show()
        if self.config.app.gui.minimize_on_start:
            self.showMinimized()
        self.statusBar().showMessage("Running")

    def _hotkey_start(self) -> None:
        if self.ctx is not None and self.ctx.tick_loop is not None and self.ctx.tick_loop._session_active:
            return  # already running - a second Start press must not rebuild/relaunch
        if self.home_page is not None:
            self.home_page._handle_start()  # keeps the Home buttons/timer in sync
        else:
            self._start()

    def _confirm_calibration(self, loop) -> bool:
        """If screens the lobby -> FFA path depends on were never calibrated,
        say so up front instead of letting the run time out and relaunch.
        """
        try:
            gaps = loop.calibration_gaps()
        except Exception:
            log.exception("calibration check failed")
            return True
        blocking = [m for sev, m in gaps if sev == "error"]
        minor = [m for sev, m in gaps if sev == "warn"]
        if not blocking:
            return True
        choice = self._ask_calibration(blocking, minor)
        if choice == "calibrate":
            index = PAGES.index("Calibration")
            self.nav.button(index).setChecked(True)
            self.stack.setCurrentIndex(index)
        if choice != "start":
            self._reset_home_buttons()
            return False
        return True

    def _ask_calibration(self, blocking: list[str], minor: list[str]) -> str:
        """Modal prompt -> "calibrate" | "start" | "cancel". Tests replace this."""
        text = ("Warden can't get into an FFA match yet - these screens haven't been calibrated "
                "for your monitor:\n\n" + "\n".join(f"•  {m}" for m in blocking))
        if minor:
            text += "\n\nAlso missing (weapons/respawn won't be handled):\n" + "\n".join(f"•  {m}" for m in minor)
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("Calibration needed")
        box.setText(text)
        calibrate = box.addButton("Open Calibration", QMessageBox.AcceptRole)
        start = box.addButton("Start anyway", QMessageBox.DestructiveRole)
        box.addButton(QMessageBox.Cancel)
        box.setDefaultButton(calibrate)
        box.exec()
        clicked = box.clickedButton()
        if clicked is calibrate:
            return "calibrate"
        if clicked is start:
            return "start"
        return "cancel"

    def _reset_home_buttons(self) -> None:
        if self.home_page is not None and hasattr(self.home_page, "reset_controls"):
            self.home_page.reset_controls()

    def _refresh_history_views(self) -> None:
        """A session just ended, which wrote a new sessions/*.json (HANDOFF
        section 9) - refresh every page that charts/lists past sessions."""
        if self.home_page is not None:
            self.home_page.refresh_history()
        history = getattr(self, "pages", {}).get("History")
        if history is not None and hasattr(history, "refresh_sessions"):
            history.refresh_sessions()

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
        self._reset_home_buttons()  # a hotkey/scheduled stop never went through HomePage's own Stop button
        self._refresh_history_views()
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
        elif event.topic == "session.stuck":
            self._incidents.append(event.message)
            self.showNormal()
            self.statusBar().showMessage("Paused - calibration needed (see the event log)")
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
        self._refresh_history_views()  # the preset that just ended wrote a new sessions/*.json
        self._start(ask=False)  # unattended queue advance: never block on a dialog


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
