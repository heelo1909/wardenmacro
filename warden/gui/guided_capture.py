"""Auto-capture overlay for Calibration: a small always-on-top panel that walks
through each screen Warden needs ("go to the lobby", "open the mode menu", ...)
and takes the screenshot by itself after a short countdown, so nobody has to
alt-tab back to Warden and click "Capture" at the right moment.

The capture itself uses window capture (``vision.capture.WindowCapturer``), so
this panel sitting on top of the game never ends up in the screenshot; it's
also hidden for the instant of the grab in case window capture isn't available.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from warden.flows.calibration import GUIDES_BY_KEY
from warden.gui import theme


class GuidedCapture(QWidget):
    def __init__(
        self,
        steps: Sequence[Sequence[str]],
        grab: Callable[[], object],
        on_captured: Callable[[Sequence[str], object], None],
        on_finished: Callable[[list[str]], None],
        countdown_s: int = 8,
        anchor: tuple[int, int, int, int] | None = None,
    ):
        super().__init__(None, Qt.Tool | Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)  # don't steal focus from the game
        self.steps = [tuple(s) for s in steps]
        self._grab_frame = grab  # (not self.grab - that would shadow QWidget.grab)
        self.on_captured = on_captured
        self.on_finished = on_finished
        self.countdown_s = countdown_s
        self.index = 0
        self.remaining = countdown_s
        self.captured: list[str] = []
        self._paused_for_result = False

        self.setObjectName("GuidedCapture")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(theme.stylesheet(0.9) + f"""
            QWidget#GuidedCapture {{ background: {theme.CARD}; border: 2px solid {theme.ACCENT};
                                     border-radius: 12px; }}
        """)
        self.setFixedWidth(360)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)
        self.step_label = QLabel(objectName="Section")
        self.title_label = QLabel(objectName="StatValue")
        self.instruction = QLabel(objectName="Muted")
        self.instruction.setWordWrap(True)
        self.countdown_label = QLabel()
        self.countdown_label.setStyleSheet(f"color: {theme.ACCENT}; font-weight: 600;")
        layout.addWidget(self.step_label)
        layout.addWidget(self.title_label)
        layout.addWidget(self.instruction)
        layout.addWidget(self.countdown_label)

        buttons = QHBoxLayout()
        self.capture_btn = QPushButton("Capture now", objectName="Primary")
        self.more_btn = QPushButton("+10s")
        self.skip_btn = QPushButton("Skip")
        self.stop_btn = QPushButton("Done")
        self.capture_btn.clicked.connect(self.capture_now)
        self.more_btn.clicked.connect(self.more_time)
        self.skip_btn.clicked.connect(self.skip)
        self.stop_btn.clicked.connect(self.finish)
        for b in (self.capture_btn, self.more_btn, self.skip_btn, self.stop_btn):
            b.setFocusPolicy(Qt.NoFocus)
            buttons.addWidget(b)
        layout.addLayout(buttons)

        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._tick)
        self._place(anchor)
        self._show_step()

    # -- layout -------------------------------------------------------

    def _place(self, anchor: tuple[int, int, int, int] | None) -> None:
        """Top-right corner of the Roblox window (or the screen), out of the
        way of the menus that usually sit in the middle/bottom."""
        self.adjustSize()
        if anchor is None:
            screen = QGuiApplication.primaryScreen()
            geo = screen.availableGeometry() if screen else None
            anchor = (geo.x(), geo.y(), geo.width(), geo.height()) if geo else (0, 0, 1280, 720)
        x, y, w, _h = anchor
        ratio = self.devicePixelRatioF() or 1.0
        # Window rects come from Win32 in physical pixels; Qt positions in logical ones.
        self.move(int((x + w) / ratio) - self.width() - 24, int(y / ratio) + 60)

    # -- steps -------------------------------------------------------

    def current(self) -> tuple[str, ...] | None:
        return self.steps[self.index] if self.index < len(self.steps) else None

    def _show_step(self) -> None:
        step = self.current()
        if step is None:
            self.finish()
            return
        guide = GUIDES_BY_KEY.get(step[0])
        self.step_label.setText(f"AUTO-CAPTURE  ·  STEP {self.index + 1} OF {len(self.steps)}")
        self.title_label.setText(guide.title if guide else step[0])
        optional = "" if (guide and guide.required) else "  (optional - Skip if you can't get there now)"
        self.instruction.setText((guide.go_to if guide else "") + optional)
        self.remaining = self.countdown_s
        self._paused_for_result = False
        self._update_countdown()
        self.adjustSize()  # instruction text length differs per step
        self.timer.start()

    def _update_countdown(self) -> None:
        self.countdown_label.setText(f"Capturing in {self.remaining}…")

    def _tick(self) -> None:
        if self._paused_for_result:
            return
        self.remaining -= 1
        if self.remaining <= 0:
            self.capture_now()
        else:
            self._update_countdown()

    def more_time(self) -> None:
        self.remaining += 10
        self._update_countdown()

    def skip(self) -> None:
        self.timer.stop()
        self.index += 1
        self._show_step()

    def capture_now(self) -> None:
        self.timer.stop()
        self._paused_for_result = True
        self.hide()  # never let this panel end up in a screen-grab fallback
        QTimer.singleShot(180, self._do_capture)

    def _do_capture(self) -> None:
        frame = None
        try:
            frame = self._grab_frame()
        except Exception:
            frame = None
        self.show()
        step = self.current()
        if frame is None or step is None:
            self.countdown_label.setText("Roblox window not found - is it open?")
            self.remaining = self.countdown_s
            self._paused_for_result = False
            QTimer.singleShot(1500, lambda: (self._update_countdown(), self.timer.start()))
            return
        self.on_captured(step, frame)
        self.captured.extend(step)
        self.countdown_label.setText("✓ Captured")
        QTimer.singleShot(1200, self._advance)

    def _advance(self) -> None:
        self.index += 1
        self._show_step()

    def finish(self) -> None:
        self.timer.stop()
        self.hide()
        callback, self.on_finished = self.on_finished, (lambda _c: None)
        callback(list(self.captured))
        self.deleteLater()
