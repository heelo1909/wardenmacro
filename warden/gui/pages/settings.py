"""Settings - HANDOFF section 7.3."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from warden.config.schema import LaunchMode
from warden.gui.context import AppContext
from warden.gui.widgets import card, page_header, section_label


class SettingsPage(QWidget):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx

        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 24)
        outer.setSpacing(16)
        header_row = QHBoxLayout()
        header_row.addWidget(page_header("Settings"))
        header_row.addStretch(1)
        self.save_btn = QPushButton("Save", objectName="Primary")
        self.save_btn.clicked.connect(self._save)
        header_row.addWidget(self.save_btn)
        outer.addLayout(header_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent; border: none;")
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setSpacing(14)
        scroll.setWidget(body)
        outer.addWidget(scroll)

        app, preset = ctx.app, ctx.preset

        # -- launch ---------------------------------------------------
        launch_card, f = self._form()
        layout.addWidget(launch_card)
        f.addRow(section_label("Launch"))
        self.launch_mode = QComboBox()
        self.launch_mode.addItems([m.value for m in LaunchMode])
        self.launch_mode.setCurrentText(preset.launch.mode.value)
        f.addRow("Mode", self.launch_mode)
        self.place_id = QLineEdit(str(preset.launch.place_id))
        f.addRow("Place ID", self.place_id)
        self.share_code = QLineEdit(preset.launch.share_code)
        f.addRow("Share code", self.share_code)
        warn = QLabel("share_link mode may not count toward contracts - public is the safe default.")
        warn.setObjectName("Muted")
        warn.setWordWrap(True)
        f.addRow(warn)

        # -- hotkeys ---------------------------------------------------
        hk_card, f = self._form()
        layout.addWidget(hk_card)
        f.addRow(section_label("Hotkeys"))
        self.hotkey_edits = {}
        for key in ("start", "pause", "stop", "screenshot"):
            edit = QLineEdit(getattr(app.hotkeys, key))
            self.hotkey_edits[key] = edit
            f.addRow(key.title(), edit)

        # -- behavior ---------------------------------------------------
        beh_card, f = self._form()
        layout.addWidget(beh_card)
        f.addRow(section_label("Behavior"))
        self.profile_combo = QComboBox()
        self.profile_combo.addItems(["fight", "patrol", "fire_loop", "idle_nudge", "hide_spot"])
        self.profile_combo.setCurrentText(preset.behavior.profile)
        f.addRow("Profile", self.profile_combo)
        hint = QLabel("fight = walk around + shoot · patrol = walk only · fire_loop = stand + shoot · "
                      "idle_nudge = barely move (anti-kick only)")
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        f.addRow(hint)
        self.fire_every = _spin(1, 600, preset.behavior.fire_every_seconds)
        f.addRow("Shoot every (s)", self.fire_every)
        self.anti_idle = _spin(10, 1100, preset.behavior.anti_idle_seconds)
        f.addRow("Anti-idle every (s)", self.anti_idle)
        self.jitter = _spin(0, 60, preset.behavior.jitter_pct)
        f.addRow("Timing jitter (%)", self.jitter)

        # -- contract / scheduler ---------------------------------------------------
        sch_card, f = self._form()
        layout.addWidget(sch_card)
        f.addRow(section_label("Target & scheduler"))
        self.target_hours = _spin(0.01, 10000, preset.contract.target_hours)
        f.addRow("Target hours", self.target_hours)
        self.auto_stop = QCheckBox("Auto-stop at target")
        self.auto_stop.setChecked(preset.contract.auto_stop_at_target)
        f.addRow(self.auto_stop)
        self.stop_at_time = QLineEdit(app.scheduler.stop_at_time or "")
        self.stop_at_time.setPlaceholderText("HH:MM (optional)")
        f.addRow("Stop at clock time", self.stop_at_time)
        self.after_stop = QComboBox()
        self.after_stop.addItems(["nothing", "sleep", "shutdown"])
        self.after_stop.setCurrentText(app.scheduler.after_stop)
        f.addRow("After stop", self.after_stop)

        # -- integrations ---------------------------------------------------
        int_card, f = self._form()
        layout.addWidget(int_card)
        f.addRow(section_label("Integrations"))
        self.webhook_enabled = QCheckBox("Discord webhook enabled")
        self.webhook_enabled.setChecked(app.integrations.discord_webhook.enabled)
        f.addRow(self.webhook_enabled)
        self.webhook_url = QLineEdit(app.integrations.discord_webhook.url)
        f.addRow("Webhook URL", self.webhook_url)
        self.lan_enabled = QCheckBox("LAN dashboard enabled")
        self.lan_enabled.setChecked(app.integrations.lan_dashboard.enabled)
        f.addRow(self.lan_enabled)
        self.toasts_enabled = QCheckBox("Windows toasts")
        self.toasts_enabled.setChecked(app.integrations.toasts)
        f.addRow(self.toasts_enabled)

        # -- app ---------------------------------------------------
        app_card, f = self._form()
        layout.addWidget(app_card)
        f.addRow(section_label("App"))
        self.always_on_top = QCheckBox("Main window always on top")
        self.always_on_top.setChecked(app.gui.always_on_top)
        f.addRow(self.always_on_top)
        self.log_verbosity = QComboBox()
        self.log_verbosity.addItems(["debug", "info", "warn", "error"])
        self.log_verbosity.setCurrentText(app.gui.log_verbosity)
        f.addRow("Log verbosity", self.log_verbosity)
        self.observe_only = QCheckBox("Observe-only (log actions, send no input)")
        self.observe_only.setChecked(app.observe_only)
        f.addRow(self.observe_only)

        layout.addStretch(1)

    @staticmethod
    def _form() -> tuple[QWidget, QFormLayout]:
        widget, layout = card()
        form = QFormLayout()
        form.setSpacing(8)
        # Narrow window: put a field under its label instead of squeezing both.
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        layout.addLayout(form)
        return widget, form

    def _save(self) -> None:
        app, preset = self.ctx.app, self.ctx.preset
        preset.launch.mode = LaunchMode(self.launch_mode.currentText())
        try:
            preset.launch.place_id = int(self.place_id.text())
        except ValueError:
            pass
        preset.launch.share_code = self.share_code.text()
        for key, edit in self.hotkey_edits.items():
            setattr(app.hotkeys, key, edit.text())
        preset.behavior.profile = self.profile_combo.currentText()
        preset.behavior.anti_idle_seconds = self.anti_idle.value()
        preset.behavior.fire_every_seconds = self.fire_every.value()
        preset.behavior.jitter_pct = self.jitter.value()
        preset.contract.target_hours = self.target_hours.value()
        preset.contract.auto_stop_at_target = self.auto_stop.isChecked()
        app.scheduler.stop_at_time = self.stop_at_time.text() or None
        app.scheduler.after_stop = self.after_stop.currentText()
        app.integrations.discord_webhook.enabled = self.webhook_enabled.isChecked()
        app.integrations.discord_webhook.url = self.webhook_url.text()
        app.integrations.lan_dashboard.enabled = self.lan_enabled.isChecked()
        app.integrations.toasts = self.toasts_enabled.isChecked()
        app.gui.always_on_top = self.always_on_top.isChecked()
        app.gui.log_verbosity = self.log_verbosity.currentText()
        app.observe_only = self.observe_only.isChecked()
        try:
            self.ctx.save_app_config()
            self.ctx.save_preset()
            self.save_btn.setText("Saved")
        except Exception as exc:  # pydantic validation, etc.
            self.save_btn.setText(f"Error: {exc}"[:40])


def _spin(lo: float, hi: float, value: float) -> QDoubleSpinBox:
    box = QDoubleSpinBox()
    box.setRange(lo, hi)
    box.setValue(value)
    box.setDecimals(2)
    return box
