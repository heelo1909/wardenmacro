"""Home (dashboard) - HANDOFF section 7.1."""

from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from warden.core.events import Event, Level
from warden.core.state_machine import State
from warden.gui.bridge import BusBridge
from warden.gui.context import AppContext
from warden.gui.widgets import StatTile, StatusChip, card, muted, page_header, row, section_label

STATE_TO_CHIP = {
    State.IDLE: "ready", State.STOPPED: "stopped", State.PAUSED: "paused",
    State.IN_MATCH: "in_match", State.RECOVERING: "recovering",
    State.LAUNCHING: "queueing", State.LOADING: "queueing", State.LOBBY: "queueing",
    State.MODE_SELECT: "queueing", State.MIDGAME_JOIN: "queueing", State.LOADOUT: "queueing",
    State.DEAD: "in_match", State.MATCH_END: "queueing", State.DISCONNECTED: "recovering",
    State.UNKNOWN: "recovering",
}

_LEVEL_ORDER = ["debug", "info", "success", "warn", "error"]


class HomePage(QWidget):
    def __init__(self, ctx: AppContext, on_start=None, on_pause=None, on_resume=None, on_stop=None):
        super().__init__()
        self.ctx = ctx
        self._on_start = on_start
        self._on_pause = on_pause
        self._on_resume = on_resume
        self._on_stop = on_stop
        self._session_start: float | None = None
        self._paused_at: float | None = None
        self._paused_total = 0.0
        self._in_match_seconds = 0.0
        self._last_sample = time.monotonic()
        self._verbose = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)
        layout.addWidget(page_header("Home"))

        # -- controls row ---------------------------------------------------
        self.start_btn = QPushButton("Start", objectName="Primary")
        self.pause_btn = QPushButton("Pause")
        self.stop_btn = QPushButton("Stop")
        self.pause_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        self.start_btn.clicked.connect(self._handle_start)
        self.pause_btn.clicked.connect(self._handle_pause)
        self.stop_btn.clicked.connect(self._handle_stop)
        self.status_chip = StatusChip()
        controls = row(self.start_btn, self.pause_btn, self.stop_btn, self.status_chip, stretch_last=True)
        layout.addWidget(controls)

        # -- resume banner (section 9: "On next launch, Home offers Resume last session") ---
        self.resume_banner = QWidget()
        banner_layout = QHBoxLayout(self.resume_banner)
        banner_layout.setContentsMargins(0, 0, 0, 0)
        self.resume_label = QLabel("")
        self.resume_label.setObjectName("Muted")
        resume_btn = QPushButton("Resume")
        resume_btn.clicked.connect(self._handle_start)
        banner_layout.addWidget(self.resume_label, 1)
        banner_layout.addWidget(resume_btn)
        self.resume_banner.setVisible(False)
        layout.addWidget(self.resume_banner)
        self._refresh_resume_banner()

        # -- timer + contract progress ---------------------------------------------------
        top_card, top_layout = card()
        timers_row = QHBoxLayout()
        self.session_timer_label = QLabel("00:00:00", objectName="StatValue")
        self.session_timer_label.setStyleSheet("font-size: 24pt;")
        timer_col = QVBoxLayout()
        timer_col.addWidget(section_label("Session"))
        timer_col.addWidget(self.session_timer_label)
        timers_row.addLayout(timer_col)
        timers_row.addStretch(1)
        top_layout.addLayout(timers_row)

        progress_header = QHBoxLayout()
        self.contract_label = muted("No preset loaded")
        progress_header.addWidget(self.contract_label)
        top_layout.addLayout(progress_header)
        self.progress_bar = _ProgressBar()
        top_layout.addWidget(self.progress_bar)
        layout.addWidget(top_card)

        # -- counters ---------------------------------------------------
        counters_card, counters_layout = card()
        counters_layout.addWidget(section_label("Counters"))
        grid = QGridLayout()
        grid.setSpacing(10)
        self.tiles = {
            "respawns": StatTile("Respawns"), "reconnects": StatTile("Reconnects"),
            "re_queues": StatTile("Re-queues"), "loadout_fixes": StatTile("Loadout fixes"),
            "time_lost": StatTile("Time lost"), "uptime": StatTile("In-match uptime"),
        }
        for i, tile in enumerate(self.tiles.values()):
            grid.addWidget(tile, 0, i)
        counters_layout.addLayout(grid)
        layout.addWidget(counters_card)

        # -- automation toggles ---------------------------------------------------
        auto_card, auto_layout = card()
        auto_layout.addWidget(section_label("Automation"))
        auto_row = QHBoxLayout()
        self.toggles: dict[str, QCheckBox] = {}
        for key, label in (("auto_reconnect", "Auto reconnect"), ("respawn_recovery", "Respawn recovery"),
                           ("auto_requeue", "Auto re-queue"), ("abilities", "Abilities"),
                           ("anti_idle", "Anti-idle")):
            box = QCheckBox(label)
            box.setChecked(getattr(ctx.app.automation, key))
            box.toggled.connect(lambda checked, k=key: self._set_automation(k, checked))
            self.toggles[key] = box
            auto_row.addWidget(box)
        auto_row.addStretch(1)
        auto_layout.addLayout(auto_row)
        layout.addWidget(auto_card)

        # -- loadout card + presets ---------------------------------------------------
        mid_row = QHBoxLayout()
        loadout_card, loadout_layout = card()
        loadout_layout.addWidget(section_label("Active loadout"))
        self.slot_labels = {}
        for slot in ("primary", "secondary", "melee", "utility"):
            lbl = QLabel(f"{slot.title()}: -")
            self.slot_labels[slot] = lbl
            loadout_layout.addWidget(lbl)
        mid_row.addWidget(loadout_card, 1)

        presets_card, presets_layout = card()
        presets_layout.addWidget(section_label("Quick presets"))
        preset_row = QHBoxLayout()
        for preset_id in ctx.available_presets():
            btn = QPushButton(preset_id.replace("_", " ").title())
            btn.clicked.connect(lambda _, p=preset_id: self._switch_preset(p))
            preset_row.addWidget(btn)
        presets_layout.addLayout(preset_row)
        mid_row.addWidget(presets_card, 1)
        layout.addLayout(mid_row)

        # -- thumbnail + log ---------------------------------------------------
        bottom_row = QHBoxLayout()
        thumb_card, thumb_layout = card()
        thumb_layout.addWidget(section_label("Roblox window"))
        self.thumbnail = QLabel("(not running)")
        self.thumbnail.setFixedSize(220, 130)
        self.thumbnail.setAlignment(Qt.AlignCenter)
        self.thumbnail.setStyleSheet("background:#000; border-radius:8px; color:#666;")
        thumb_layout.addWidget(self.thumbnail)
        bottom_row.addWidget(thumb_card)

        log_card, log_layout = card()
        log_header = QHBoxLayout()
        log_header.addWidget(section_label("Event log"))
        log_header.addStretch(1)
        self.level_combo = QComboBox()
        self.level_combo.addItems(["info", "debug", "warn", "error"])
        self.verbose_box = QCheckBox("Verbose")
        self.verbose_box.toggled.connect(self._set_verbose)
        log_header.addWidget(self.level_combo)
        log_header.addWidget(self.verbose_box)
        log_layout.addLayout(log_header)
        self.log_list = QListWidget()
        self.log_list.setMaximumHeight(160)
        log_layout.addWidget(self.log_list)
        bottom_row.addWidget(log_card, 1)
        layout.addLayout(bottom_row)
        layout.addStretch(1)

        self._refresh_loadout_card()
        self._refresh_contract_label()

        self.bridge = BusBridge(ctx.bus)
        self.bridge.event.connect(self._on_event)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._refresh_live_stats)
        self.timer.start(500)

    # -- actions -------------------------------------------------------

    def _handle_start(self) -> None:
        self._session_start = time.monotonic()
        self._paused_total = 0.0
        self._in_match_seconds = 0.0
        self.start_btn.setEnabled(False)
        self.pause_btn.setEnabled(True)
        self.pause_btn.setText("Pause")
        self.stop_btn.setEnabled(True)
        self.resume_banner.setVisible(False)
        if self._on_start:
            self._on_start()

    def _handle_pause(self) -> None:
        loop = self.ctx.tick_loop
        if loop is None:
            return
        if loop.sm.state.name == "PAUSED":
            if self._paused_at is not None:
                self._paused_total += time.monotonic() - self._paused_at
                self._paused_at = None
            self.pause_btn.setText("Pause")
            if self._on_resume:
                self._on_resume()
        else:
            self._paused_at = time.monotonic()
            self.pause_btn.setText("Resume")
            if self._on_pause:
                self._on_pause()

    def _handle_stop(self) -> None:
        self.start_btn.setEnabled(True)
        self.pause_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        if self._on_stop:
            self._on_stop()

    def _set_automation(self, key: str, value: bool) -> None:
        setattr(self.ctx.app.automation, key, value)
        self.ctx.save_app_config()

    def _set_verbose(self, value: bool) -> None:
        self._verbose = value

    # -- accessors for MainWindow's summary dialog -------------------------------------------------------

    def session_duration(self) -> float:
        if self._session_start is None:
            return 0.0
        return time.monotonic() - self._session_start - self._paused_total

    def in_match_seconds(self) -> float:
        return self._in_match_seconds

    def _switch_preset(self, preset_id: str) -> None:
        self.ctx.set_active_preset(preset_id)
        self._refresh_loadout_card()
        self._refresh_contract_label()
        self._refresh_resume_banner()

    # -- live refresh -------------------------------------------------------

    def _refresh_loadout_card(self) -> None:
        slots = self.ctx.preset.loadout.slots() if not self.ctx.preset.loadout.random else {}
        for slot, label in self.slot_labels.items():
            value = slots.get(slot, "") or ("random" if self.ctx.preset.loadout.random else "-")
            label.setText(f"{slot.title()}: {value}")

    def _refresh_contract_label(self) -> None:
        banked = self.ctx.contract_banked_hours()
        self.contract_label.setText(
            f"{self.ctx.preset.contract.label} — {banked:.2f}h / "
            f"{self.ctx.preset.contract.target_hours:.1f}h banked (estimated)"
        )
        self.progress_bar.set_target(self.ctx.preset.contract.target_hours)
        self.progress_bar.set_value(banked)

    def _refresh_resume_banner(self) -> None:
        state = self.ctx.persisted_state()
        if state.last_session_incomplete and state.last_session_preset_id == self.ctx.preset_id:
            banked = self.ctx.contract_banked_hours()
            self.resume_label.setText(
                f"Last session was interrupted - {banked:.2f}h already banked for "
                f"'{self.ctx.preset.contract.label}'. Progress is safe."
            )
            self.resume_banner.setVisible(True)
        else:
            self.resume_banner.setVisible(False)

    def _refresh_live_stats(self) -> None:
        now = time.monotonic()
        loop = self.ctx.tick_loop
        if self._session_start is not None and self._paused_at is None:
            elapsed = now - self._session_start - self._paused_total
            self.session_timer_label.setText(_format_hms(elapsed))
        if loop is not None:
            # TickLoop is the authoritative tracker (it's what gets persisted) - mirror it here.
            self._in_match_seconds = loop._in_match_seconds
            self.status_chip.set_state(STATE_TO_CHIP.get(loop.sm.state, "ready"))
            c = loop.sm.counters
            self.tiles["respawns"].set_value(str(c.respawns))
            self.tiles["reconnects"].set_value(str(c.reconnects))
            self.tiles["re_queues"].set_value(str(c.re_queues))
            self.tiles["loadout_fixes"].set_value(str(c.loadout_fixes))
            self.tiles["time_lost"].set_value(_format_hms(c.time_lost_s))
            session_s = max(now - (self._session_start or now) - self._paused_total, 0.001)
            self.tiles["uptime"].set_value(f"{min(self._in_match_seconds / session_s * 100, 100):.0f}%")
            self.progress_bar.set_value(self.ctx.contract_banked_hours() + self._in_match_seconds / 3600.0)
            self.progress_bar.set_value(self._in_match_seconds / 3600.0)
            self._update_thumbnail(loop)
        self._last_sample = now

    def _update_thumbnail(self, loop) -> None:
        rect = loop._client_rect
        if rect is None:
            self.thumbnail.setText("(not running)")
            self.thumbnail.setPixmap(QPixmap())
            return
        try:
            frame = loop.capturer.grab(rect)
        except Exception:
            return
        h, w = frame.shape[:2]
        image = QImage(frame.data, w, h, frame.strides[0], QImage.Format_BGR888)
        self.thumbnail.setPixmap(QPixmap.fromImage(image).scaled(
            self.thumbnail.width(), self.thumbnail.height(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def _on_event(self, event: Event) -> None:
        floor = Level.parse(self.level_combo.currentText())
        if event.level < floor:
            return
        if not self._verbose and event.level < Level.INFO:
            return
        item = QListWidgetItem(f"[{time.strftime('%H:%M:%S', time.localtime(event.ts))}] {event.message}")
        item.setForeground(_level_color(event.level))
        self.log_list.addItem(item)
        self.log_list.scrollToBottom()
        while self.log_list.count() > 500:
            self.log_list.takeItem(0)


def _format_hms(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _level_color(level: Level):
    from PySide6.QtGui import QColor

    from warden.gui import theme

    return QColor({
        Level.ERROR: theme.ERROR, Level.WARN: theme.ACCENT, Level.SUCCESS: theme.SUCCESS,
    }.get(level, theme.TEXT_MUTED))


class _ProgressBar(QFrame):
    """A simple amber progress bar (avoids QProgressBar's default platform chrome)."""

    def __init__(self):
        super().__init__()
        self.setFixedHeight(10)
        self.setStyleSheet(f"background:{'#2A2F37'}; border-radius:5px;")
        self._fill = QFrame(self)
        self._fill.setStyleSheet(f"background:#F2A93B; border-radius:5px;")
        self._target_hours = 1.0
        self._value_hours = 0.0

    def set_target(self, hours: float) -> None:
        self._target_hours = max(hours, 0.01)
        self._apply()

    def set_value(self, hours: float) -> None:
        self._value_hours = hours
        self._apply()

    def _apply(self) -> None:
        frac = min(self._value_hours / self._target_hours, 1.0)
        self._fill.setGeometry(0, 0, int(self.width() * frac), self.height())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply()
