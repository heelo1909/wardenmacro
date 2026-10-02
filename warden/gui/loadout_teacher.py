""""Learn my loadout": pick your weapons once yourself in RIVALS while Warden
watches, and it learns what each one looks like in the picker - no boxes to
drag, no screenshots to take.

How it works: while this small on-top panel is open, Warden keeps the last
couple of frames of the Roblox window (window capture, so the panel itself is
never in them) and listens for left clicks. Each click that lands on the
weapon list is matched with the frame from just *before* the click, the row
under the cursor is cropped, and saved as the template for the slot being
taught - primary, then secondary, melee, utility, the same order the picker
goes in.
"""

from __future__ import annotations

import collections
import threading
import time
from collections.abc import Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from warden.config.schema import SLOTS
from warden.gui import theme


class LoadoutTeacher(QWidget):
    def __init__(
        self,
        weapons: dict[str, str],
        learn: Callable[[str, str, object, float, float], bool],
        on_finished: Callable[[list[str]], None],
        find_client: Callable[[], tuple[int, object] | None],
        make_capturer: Callable[[], object],
        start_listener: Callable[[Callable[[float, float], None]], object] | None = None,
        anchor: tuple[int, int, int, int] | None = None,
    ):
        super().__init__(None, Qt.Tool | Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.slots = [s for s in SLOTS if weapons.get(s)]
        self.weapons = weapons
        self.learn = learn
        self.on_finished = on_finished
        self.find_client = find_client
        self.capturer = make_capturer()
        self.index = 0
        self.learned: list[str] = []
        self._frames: collections.deque = collections.deque(maxlen=6)  # (t, frame)
        self._clicks: collections.deque = collections.deque()           # (t, screen x, screen y)
        self._lock = threading.Lock()
        self._client = None

        self.setObjectName("LoadoutTeacher")
        self.setStyleSheet(theme.stylesheet(0.9) + f"""
            QWidget#LoadoutTeacher {{ background: {theme.CARD}; border: 2px solid {theme.ACCENT};
                                      border-radius: 12px; }}
        """)
        self.setFixedWidth(370)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)
        self.step_label = QLabel(objectName="Section")
        self.title_label = QLabel(objectName="StatValue")
        self.instruction = QLabel(objectName="Muted")
        self.instruction.setWordWrap(True)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setStyleSheet(f"color: {theme.ACCENT}; font-weight: 600;")
        for w in (self.step_label, self.title_label, self.instruction, self.status):
            layout.addWidget(w)
        row = QHBoxLayout()
        skip = QPushButton("Skip")
        done = QPushButton("Done")
        skip.clicked.connect(self.skip)
        done.clicked.connect(self.finish)
        for b in (skip, done):
            b.setFocusPolicy(Qt.NoFocus)
            row.addWidget(b)
        layout.addLayout(row)

        self._capture_timer = QTimer(self)
        self._capture_timer.setInterval(120)
        self._capture_timer.timeout.connect(self._capture)
        self._click_timer = QTimer(self)
        self._click_timer.setInterval(60)
        self._click_timer.timeout.connect(self._process_clicks)
        self._listener = start_listener(self.on_click) if start_listener else None
        self._place(anchor)
        self._show_step()
        self._capture_timer.start()
        self._click_timer.start()

    def _place(self, anchor) -> None:
        from PySide6.QtGui import QGuiApplication

        self.adjustSize()
        if anchor is None:
            screen = QGuiApplication.primaryScreen()
            geo = screen.availableGeometry() if screen else None
            anchor = (geo.x(), geo.y(), geo.width(), geo.height()) if geo else (0, 0, 1280, 720)
        x, y, w, _h = anchor
        ratio = self.devicePixelRatioF() or 1.0
        self.move(int((x + w) / ratio) - self.width() - 24, int(y / ratio) + 60)

    # -- steps -------------------------------------------------------

    def current_slot(self) -> str | None:
        return self.slots[self.index] if self.index < len(self.slots) else None

    def _show_step(self) -> None:
        slot = self.current_slot()
        if slot is None:
            self.finish()
            return
        self.step_label.setText(f"LEARN MY LOADOUT  ·  {self.index + 1} OF {len(self.slots)}")
        self.title_label.setText(f"{slot.title()}: {self.weapons[slot]}")
        first = ("Open the weapon picker in RIVALS (start of an FFA match, or the shooting range). "
                 if self.index == 0 else "")
        self.instruction.setText(f"{first}Click {self.weapons[slot]} in the list, like you normally would.")
        self.adjustSize()

    def skip(self) -> None:
        self.index += 1
        self._show_step()

    # -- capture + clicks -------------------------------------------------------

    def _capture(self) -> None:
        try:
            found = self.find_client()
            if found is None:
                self.status.setText("Waiting for the Roblox window…")
                return
            hwnd, rect = found
            self._client = rect
            if hasattr(self.capturer, "hwnd"):
                self.capturer.hwnd = hwnd
            frame = self.capturer.grab(rect)
        except Exception:
            return
        with self._lock:
            self._frames.append((time.monotonic(), frame))

    def on_click(self, x: float, y: float) -> None:
        """Called from the mouse-listener thread for every left-button press."""
        with self._lock:
            self._clicks.append((time.monotonic(), x, y))

    def _frame_before(self, t: float):
        with self._lock:
            older = [f for ts, f in self._frames if ts <= t - 0.03]
            return older[-1] if older else (self._frames[-1][1] if self._frames else None)

    def _process_clicks(self) -> None:
        while True:
            with self._lock:
                if not self._clicks:
                    return
                t, x, y = self._clicks.popleft()
            self.handle_click(t, x, y)

    def handle_click(self, t: float, x: float, y: float) -> None:
        slot = self.current_slot()
        rect = self._client
        if slot is None or rect is None:
            return
        fx, fy = (x - rect.left) / max(rect.width, 1), (y - rect.top) / max(rect.height, 1)
        if not (0 <= fx <= 1 and 0 <= fy <= 1):
            return  # a click on this panel or another window
        frame = self._frame_before(t)
        if frame is None:
            self.status.setText("No picture of Roblox yet - click again in a second.")
            return
        weapon = self.weapons[slot]
        if self.learn(slot, weapon, frame, fx, fy):
            self.learned.append(slot)
            self.status.setText(f"✓ Learned {weapon}")
            self.index += 1
            QTimer.singleShot(400, self._show_step)
        else:
            self.status.setText("That click wasn't on the weapon list - click the weapon's name.")

    def finish(self) -> None:
        self._capture_timer.stop()
        self._click_timer.stop()
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None
        self.hide()
        callback, self.on_finished = self.on_finished, (lambda _l: None)
        callback(list(self.learned))
        self.deleteLater()


def start_pynput_click_listener(callback: Callable[[float, float], None]):
    """Global left-click listener (screen pixels). Returns the listener (has .stop())."""
    from pynput import mouse

    def on_click(x, y, button, pressed):
        if pressed and button == mouse.Button.left:
            callback(float(x), float(y))

    listener = mouse.Listener(on_click=on_click)
    listener.daemon = True
    listener.start()
    return listener
