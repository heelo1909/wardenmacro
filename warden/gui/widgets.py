"""Small reusable widget builders shared by every page - keeps the pages
themselves focused on layout/behavior instead of boilerplate styling.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget


def card(margins: tuple[int, int, int, int] = (18, 16, 18, 16), spacing: int = 10) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame(objectName="Card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(*margins)
    layout.setSpacing(spacing)
    return frame, layout


def page_header(title: str) -> QLabel:
    label = QLabel(title, objectName="PageTitle")
    return label


def muted(text: str) -> QLabel:
    label = QLabel(text, objectName="Muted")
    label.setWordWrap(True)
    return label


def section_label(text: str) -> QLabel:
    label = QLabel(text.upper())
    label.setObjectName("Section")
    return label


class StatTile(QFrame):
    """A small 'number + caption' tile, e.g. for the counters row on Home."""

    def __init__(self, caption: str, value: str = "0"):
        super().__init__(objectName="Card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(2)
        self.value_label = QLabel(value)
        self.value_label.setObjectName("StatValue")
        self.caption_label = QLabel(caption.upper())
        self.caption_label.setObjectName("Muted")
        layout.addWidget(self.value_label)
        layout.addWidget(self.caption_label)

    def set_value(self, value: str) -> None:
        self.value_label.setText(value)


class StatusChip(QLabel):
    STATES = {
        "ready": ("Ready", "muted"),
        "running": ("Running", "success"),
        "queueing": ("Queueing", "accent"),
        "in_match": ("In match", "success"),
        "recovering": ("Recovering", "warn"),
        "paused": ("Paused", "warn"),
        "stopped": ("Stopped", "muted"),
    }

    def __init__(self):
        super().__init__("Ready")
        self.setObjectName("StatusChip")
        self.setAlignment(Qt.AlignCenter)
        self.set_state("ready")

    def set_state(self, key: str) -> None:
        text, tone = self.STATES.get(key, (key.title(), "muted"))
        self.setText(text)
        self.setProperty("tone", tone)
        self.style().unpolish(self)
        self.style().polish(self)


class ImageCanvas(QLabel):
    """Shows a captured frame and lets the user drag out a selection rectangle
    (HANDOFF §7.4's "click/drag to sample" / "coordinate picker"). Selection
    is tracked in *original frame* pixels regardless of how the pixmap is
    scaled to fit the label, so ``selection_fractions()`` is always correct.
    """

    def __init__(self):
        super().__init__()
        self.setMinimumSize(320, 180)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("background:#000; border-radius:8px;")
        self._frame_size: tuple[int, int] | None = None  # (w, h) of the original frame
        self._pixmap_rect = None  # where the scaled pixmap sits inside this label
        self._drag_start = None
        self._selection_px: tuple[int, int, int, int] | None = None  # in ORIGINAL frame pixels

    def set_frame(self, frame) -> None:
        import cv2
        from PySide6.QtGui import QImage, QPixmap

        h, w = frame.shape[:2]
        self._frame_size = (w, h)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB) if frame.ndim == 3 else frame
        image = QImage(rgb.data, w, h, rgb.strides[0], QImage.Format_RGB888)
        self.setPixmap(QPixmap.fromImage(image))
        self._selection_px = None
        self.update()

    def _frame_to_label(self, fx: int, fy: int) -> tuple[int, int]:
        if not self._frame_size or not self.pixmap():
            return (fx, fy)
        pm = self.pixmap()
        scale = min(self.width() / pm.width(), self.height() / pm.height(), 1.0) if pm.width() else 1.0
        disp_w, disp_h = pm.width() * scale, pm.height() * scale
        ox, oy = (self.width() - disp_w) / 2, (self.height() - disp_h) / 2
        fscale_x = disp_w / self._frame_size[0]
        fscale_y = disp_h / self._frame_size[1]
        return (int(ox + fx * fscale_x), int(oy + fy * fscale_y))

    def _label_to_frame(self, lx: int, ly: int) -> tuple[int, int]:
        if not self._frame_size or not self.pixmap():
            return (lx, ly)
        pm = self.pixmap()
        scale = min(self.width() / pm.width(), self.height() / pm.height(), 1.0) if pm.width() else 1.0
        disp_w, disp_h = pm.width() * scale, pm.height() * scale
        ox, oy = (self.width() - disp_w) / 2, (self.height() - disp_h) / 2
        fw, fh = self._frame_size
        fx = (lx - ox) / disp_w * fw if disp_w else 0
        fy = (ly - oy) / disp_h * fh if disp_h else 0
        return (int(min(max(fx, 0), fw)), int(min(max(fy, 0), fh)))

    def mousePressEvent(self, event) -> None:
        if self._frame_size:
            self._drag_start = self._label_to_frame(event.position().x(), event.position().y())

    def mouseMoveEvent(self, event) -> None:
        if self._drag_start is not None:
            end = self._label_to_frame(event.position().x(), event.position().y())
            self._selection_px = (*self._drag_start, *end)
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        self._drag_start = None

    def selection_fractions(self) -> tuple[float, float, float, float] | None:
        if self._selection_px is None or not self._frame_size:
            return None
        from warden.flows.calibration import px_rect_to_fractions

        x1, y1, x2, y2 = self._selection_px
        w, h = self._frame_size
        return px_rect_to_fractions(x1, y1, x2, y2, w, h)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self._selection_px is None:
            return
        from PySide6.QtGui import QColor, QPainter, QPen

        painter = QPainter(self)
        painter.setPen(QPen(QColor("#F2A93B"), 2))
        x1, y1 = self._frame_to_label(*self._selection_px[:2])
        x2, y2 = self._frame_to_label(*self._selection_px[2:])
        painter.drawRect(min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1))


def row(*widgets: QWidget, stretch_last: bool = False, spacing: int = 10) -> QWidget:
    container = QWidget()
    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(spacing)
    for w in widgets:
        layout.addWidget(w)
    if stretch_last:
        layout.addStretch(1)
    return container
