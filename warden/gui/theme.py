"""Warden's own visual identity: graphite surfaces, single amber accent."""

from __future__ import annotations

BG = "#121417"
CARD = "#1B1E23"
CARD_HOVER = "#23272E"
BORDER = "#2A2F37"
TEXT = "#ECEDEF"
TEXT_MUTED = "#8B919B"
ACCENT = "#F2A93B"
ACCENT_PRESSED = "#D68F25"
SUCCESS = "#3FB97A"
ERROR = "#E5534B"

FONT_STACK = '"Segoe UI Variable Text", "Segoe UI Variable", "Segoe UI", "Inter", sans-serif'


def stylesheet(scale: float = 1.0) -> str:
    """The app stylesheet with every font size and spacing multiplied by
    ``scale``, so the whole UI (text included) shrinks with the window on a
    small monitor instead of getting clipped. MainWindow picks the scale.
    """

    def _pt(v: float) -> str:
        return f"{max(v * scale, 6.0):.1f}"

    def _px(v: int) -> int:
        return max(int(round(v * scale)), 1 if v else 0)

    return f"""
    * {{
        font-family: {FONT_STACK};
        font-size: {_pt(10)}pt;
        color: {TEXT};
    }}
    QMainWindow, QWidget#Root {{
        background: {BG};
    }}
    QScrollArea#PageScroll, QScrollArea#PageScroll > QWidget, QWidget#Page {{
        background: {BG};
    }}
    QWidget#Sidebar {{
        background: {BG};
        border-right: {_px(1)}px solid {BORDER};
    }}
    QLabel#Wordmark {{
        font-size: {_pt(15)}pt;
        font-weight: 600;
        color: {ACCENT};
        padding: {_px(18)}px {_px(18)}px {_px(14)}px {_px(18)}px;
    }}
    QPushButton#NavButton {{
        background: transparent;
        border: none;
        border-radius: {_px(8)}px;
        padding: {_px(9)}px {_px(14)}px;
        margin: {_px(2)}px {_px(10)}px;
        text-align: left;
        color: {TEXT_MUTED};
    }}
    QPushButton#NavButton:hover {{
        background: {CARD};
        color: {TEXT};
    }}
    QPushButton#NavButton:checked {{
        background: {CARD};
        color: {TEXT};
        border-left: {_px(3)}px solid {ACCENT};
    }}
    QFrame#Card {{
        background: {CARD};
        border: {_px(1)}px solid {BORDER};
        border-radius: {_px(12)}px;
    }}
    QLabel#PageTitle {{
        font-size: {_pt(18)}pt;
        font-weight: 600;
    }}
    QLabel#Muted {{
        color: {TEXT_MUTED};
    }}
    QLabel#Section {{
        color: {TEXT_MUTED};
        font-size: {_pt(8)}pt;
        font-weight: 600;
        letter-spacing: {_px(1)}px;
    }}
    QLabel#StatValue {{
        font-size: {_pt(17)}pt;
        font-weight: 600;
    }}
    QLabel#BigValue {{
        font-size: {_pt(24)}pt;
        font-weight: 600;
    }}
    QLabel#StatusChip {{
        border-radius: {_px(10)}px;
        padding: {_px(4)}px {_px(14)}px;
        font-weight: 600;
        background: {CARD_HOVER};
        color: {TEXT_MUTED};
        max-width: {_px(110)}px;
    }}
    QLabel#StatusChip[tone="success"] {{
        background: rgba(63, 185, 122, 0.18);
        color: {SUCCESS};
    }}
    QLabel#StatusChip[tone="warn"] {{
        background: rgba(242, 169, 59, 0.18);
        color: {ACCENT};
    }}
    QLabel#StatusChip[tone="accent"] {{
        background: rgba(242, 169, 59, 0.18);
        color: {ACCENT};
    }}
    QPushButton {{
        background: {CARD_HOVER};
        border: {_px(1)}px solid {BORDER};
        border-radius: {_px(8)}px;
        padding: {_px(7)}px {_px(16)}px;
    }}
    QPushButton:hover {{
        border-color: {ACCENT};
    }}
    QPushButton#Primary {{
        background: {ACCENT};
        color: {BG};
        border: none;
        font-weight: 600;
    }}
    QPushButton#Primary:pressed {{
        background: {ACCENT_PRESSED};
    }}
    QStatusBar {{
        background: {BG};
        color: {TEXT_MUTED};
        border-top: {_px(1)}px solid {BORDER};
    }}
    QListWidget, QTableWidget, QPlainTextEdit, QTextEdit {{
        background: {BG};
        color: {TEXT};
        border: {_px(1)}px solid {BORDER};
        border-radius: {_px(8)}px;
        padding: {_px(4)}px;
    }}
    QListWidget::item, QTableWidget::item {{
        padding: {_px(3)}px {_px(4)}px;
        border: none;
    }}
    QListWidget::item:selected, QTableWidget::item:selected {{
        background: {CARD_HOVER};
        color: {TEXT};
    }}
    QHeaderView::section {{
        background: {CARD};
        color: {TEXT_MUTED};
        border: none;
        border-bottom: {_px(1)}px solid {BORDER};
        padding: {_px(4)}px {_px(6)}px;
    }}
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
        background: {BG};
        color: {TEXT};
        border: {_px(1)}px solid {BORDER};
        border-radius: {_px(6)}px;
        padding: {_px(4)}px {_px(8)}px;
        selection-background-color: {ACCENT};
    }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
        border-color: {ACCENT};
    }}
    QComboBox::drop-down {{
        border: none;
        width: {_px(18)}px;
    }}
    QComboBox QAbstractItemView {{
        background: {CARD};
        color: {TEXT};
        selection-background-color: {CARD_HOVER};
        border: {_px(1)}px solid {BORDER};
        outline: none;
    }}
    QCheckBox {{
        spacing: {_px(8)}px;
    }}
    QCheckBox::indicator {{
        width: {_px(16)}px;
        height: {_px(16)}px;
        border-radius: {_px(4)}px;
        border: {_px(1)}px solid {BORDER};
        background: {BG};
    }}
    QCheckBox::indicator:checked {{
        background: {ACCENT};
        border-color: {ACCENT};
    }}
    QScrollArea {{
        border: none;
        background: transparent;
    }}
    QTabWidget::pane {{
        background: {CARD};
        border: {_px(1)}px solid {BORDER};
        border-radius: {_px(10)}px;
        top: -{_px(1)}px;
    }}
    QTabWidget > QWidget > QWidget {{
        background: {CARD};
    }}
    QTabBar::tab {{
        background: {BG};
        color: {TEXT_MUTED};
        border: {_px(1)}px solid {BORDER};
        border-bottom: none;
        border-top-left-radius: {_px(8)}px;
        border-top-right-radius: {_px(8)}px;
        padding: {_px(6)}px {_px(14)}px;
        margin-right: {_px(2)}px;
    }}
    QTabBar::tab:selected {{
        background: {CARD};
        color: {TEXT};
        border-color: {ACCENT};
    }}
    QTabBar::tab:hover {{
        color: {TEXT};
    }}
    QScrollBar:horizontal {{
        background: transparent;
        height: {_px(10)}px;
        margin: 0;
    }}
    QScrollBar::handle:horizontal {{
        background: {CARD_HOVER};
        border-radius: {_px(5)}px;
        min-width: {_px(24)}px;
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0;
    }}
    QScrollBar:vertical {{
        background: transparent;
        width: {_px(10)}px;
        margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background: {CARD_HOVER};
        border-radius: {_px(5)}px;
        min-height: {_px(24)}px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}
    """
