"""Small reusable widget builders shared by every page - keeps the pages
themselves focused on layout/behavior instead of boilerplate styling.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import (
    QBoxLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


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
        self.caption_label.setWordWrap(True)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
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

    Drawing is done entirely by hand in ``paintEvent`` (not via QLabel's own
    ``setPixmap``/``setScaledContents``) so the displayed image is always
    scaled to fit the widget, aspect-preserved - QLabel's default pixmap
    rendering shows it at native resolution instead, which for a real
    screen capture is almost always larger than the widget and so just
    looks cropped to whatever corner happens to be visible.
    """

    def __init__(self):
        super().__init__()
        self.setMinimumSize(240, 135)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet("background:#000; border-radius:8px;")
        self._frame_size: tuple[int, int] | None = None  # (w, h) of the original frame
        self._pixmap = None  # the original, full-resolution QPixmap
        self._drag_start = None
        self._selection_px: tuple[int, int, int, int] | None = None  # in ORIGINAL frame pixels

    def set_frame(self, frame) -> None:
        import cv2
        from PySide6.QtGui import QImage, QPixmap

        h, w = frame.shape[:2]
        self._frame_size = (w, h)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB) if frame.ndim == 3 else frame
        rgb = rgb.copy()  # own the memory - QImage doesn't copy the buffer it's given
        image = QImage(rgb.data, w, h, rgb.strides[0], QImage.Format_RGB888).copy()
        self._pixmap = QPixmap.fromImage(image)
        self._selection_px = None
        self.update()

    def _display_geometry(self) -> tuple[float, float, float, float, float] | None:
        """How ``self._pixmap`` is scaled/positioned to fit this widget: (disp_w, disp_h, ox, oy, scale)."""
        if self._pixmap is None or self._pixmap.isNull():
            return None
        pw, ph = self._pixmap.width(), self._pixmap.height()
        if pw <= 0 or ph <= 0 or self.width() <= 0 or self.height() <= 0:
            return None
        scale = min(self.width() / pw, self.height() / ph)
        disp_w, disp_h = pw * scale, ph * scale
        ox, oy = (self.width() - disp_w) / 2, (self.height() - disp_h) / 2
        return (disp_w, disp_h, ox, oy, scale)

    def _frame_to_label(self, fx: float, fy: float) -> tuple[float, float]:
        geo = self._display_geometry()
        if geo is None or not self._frame_size:
            return (fx, fy)
        disp_w, disp_h, ox, oy, _scale = geo
        fw, fh = self._frame_size
        return (ox + fx / fw * disp_w, oy + fy / fh * disp_h)

    def _label_to_frame(self, lx: float, ly: float) -> tuple[int, int]:
        geo = self._display_geometry()
        if geo is None or not self._frame_size:
            return (int(lx), int(ly))
        disp_w, disp_h, ox, oy, _scale = geo
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
        from PySide6.QtGui import QColor, QPainter, QPen

        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#000000"))
        geo = self._display_geometry()
        if self._pixmap is not None and geo is not None:
            disp_w, disp_h, ox, oy, _scale = geo
            painter.drawPixmap(int(ox), int(oy), int(disp_w), int(disp_h), self._pixmap)
        if self._selection_px is not None:
            painter.setPen(QPen(QColor("#F2A93B"), 2))
            x1, y1 = self._frame_to_label(*self._selection_px[:2])
            x2, y2 = self._frame_to_label(*self._selection_px[2:])
            painter.drawRect(int(min(x1, x2)), int(min(y1, y2)), int(abs(x2 - x1)), int(abs(y2 - y1)))


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


# --------------------------------------------------------------------------- responsive layout helpers
#
# The window has to stay usable on small/low-resolution monitors: nothing may
# be clipped, so rows of buttons wrap onto a new line, side-by-side cards
# stack vertically when there isn't room, and tiles reflow into fewer columns.


class FlowLayout(QLayout):
    """Lays children out left-to-right, wrapping onto new lines as needed."""

    def __init__(self, parent: QWidget | None = None, spacing: int = 8):
        super().__init__(parent)
        self._items = []
        self._spacing = spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item) -> None:  # noqa: N802 (Qt API)
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int):  # noqa: N802
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int):  # noqa: N802
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):  # noqa: N802
        return Qt.Orientations(0)

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect: QRect) -> None:  # noqa: N802
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self) -> QSize:  # noqa: N802
        return self.minimumSize()

    def minimumSize(self) -> QSize:  # noqa: N802
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        return size + QSize(m.left() + m.right(), m.top() + m.bottom())

    def _do_layout(self, rect: QRect, test_only: bool) -> int:
        m = self.contentsMargins()
        area = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x, y, line_h = area.x(), area.y(), 0
        for item in self._items:
            if item.widget() is not None and item.widget().isHidden():
                continue
            hint = item.sizeHint()
            w = min(hint.width(), max(area.width(), 1))
            if x > area.x() and x + w > area.right() + 1:
                x = area.x()
                y += line_h + self._spacing
                line_h = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), QSize(w, hint.height())))
            x += w + self._spacing
            line_h = max(line_h, hint.height())
        return y + line_h - rect.y() + m.bottom()


def flow(*widgets: QWidget, spacing: int = 8) -> QWidget:
    """A container whose children wrap onto extra lines when the window is narrow."""
    container = QWidget()
    layout = FlowLayout(container, spacing=spacing)
    for w in widgets:
        layout.addWidget(w)
    sp = container.sizePolicy()
    sp.setHeightForWidth(True)
    container.setSizePolicy(sp)
    return container


class ResponsiveRow(QWidget):
    """Children side by side when wide enough, stacked vertically when not."""

    def __init__(self, breakpoint: int = 760, spacing: int = 16):
        super().__init__()
        self.breakpoint = breakpoint
        self._layout = QBoxLayout(QBoxLayout.LeftToRight, self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(spacing)

    def add(self, widget: QWidget, stretch: int = 1) -> None:
        self._layout.addWidget(widget, stretch)

    def is_stacked(self) -> bool:
        return self._layout.direction() == QBoxLayout.TopToBottom

    def _children(self) -> list[QWidget]:
        out = []
        for i in range(self._layout.count()):
            w = self._layout.itemAt(i).widget()
            if w is not None and not w.isHidden():
                out.append(w)
        return out

    def _side_by_side_min(self) -> int:
        kids = self._children()
        return sum(k.minimumSizeHint().width() for k in kids) + self._layout.spacing() * max(len(kids) - 1, 0)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        # Only as wide as the widest child: the row can always stack instead
        # of forcing a horizontal scrollbar on a narrow window.
        kids = self._children()
        width = max((k.minimumSizeHint().width() for k in kids), default=0)
        return QSize(width, super().minimumSizeHint().height())

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        narrow = self.width() < max(self.breakpoint, self._side_by_side_min())
        direction = QBoxLayout.TopToBottom if narrow else QBoxLayout.LeftToRight
        if self._layout.direction() != direction:
            self._layout.setDirection(direction)
            self.updateGeometry()


class ResponsiveGrid(QWidget):
    """Equal-width tiles that reflow into as many columns as fit."""

    def __init__(self, min_item_width: int = 130, max_columns: int = 6, spacing: int = 10):
        super().__init__()
        self.min_item_width = min_item_width
        self.max_columns = max_columns
        self._items: list[QWidget] = []
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(spacing)
        self._columns = 0

    def add(self, widget: QWidget) -> None:
        self._items.append(widget)
        self._relayout(force=True)

    def columns(self) -> int:
        return self._columns

    def _relayout(self, force: bool = False) -> None:
        width = max(self.width(), 1)
        spacing = self._grid.spacing()
        n = len(self._items) or 1
        fit = max(1, min(self.max_columns, n, (width + spacing) // max(self.min_item_width + spacing, 1)))
        rows = -(-n // fit)
        cols = -(-n // rows)  # balance the rows: 6 tiles -> 6, 3x2 or 2x3, never 5+1
        if cols == self._columns and not force:
            return
        self._columns = cols
        for w in self._items:
            self._grid.removeWidget(w)
        for c in range(self.max_columns):
            self._grid.setColumnStretch(c, 1 if c < cols else 0)
        for i, w in enumerate(self._items):
            self._grid.addWidget(w, i // cols, i % cols)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._relayout()
