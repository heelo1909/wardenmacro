"""Warden's own visual identity: silver/white surfaces, graphite accent."""

from __future__ import annotations

BG = "#F7F8FA"
CARD = "#FFFFFF"
CARD_HOVER = "#EEF0F3"
BORDER = "#E0E3E8"
TEXT = "#1A1D21"
TEXT_MUTED = "#6B7280"
ACCENT = "#3A3F47"
ACCENT_PRESSED = "#24282E"
SUCCESS = "#2F9E5B"
ERROR = "#D6453F"

# Used only for the calibration marquee (ImageCanvas), drawn over arbitrary
# game screenshots rather than app chrome - stays a bright, saturated color
# independent of the main theme so it stays visible against any footage.
SELECTION = "#00B8D9"

# Subtle linear gradients layered over the flat colors above for a bit of
# "brushed metal" depth - kept light enough to stay minimalistic rather than
# glossy. Qt's QSS supports qlineargradient() directly; no images needed.
GRADIENT_PAGE = "qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #FBFCFD, stop:1 #F3F5F7)"
GRADIENT_SIDEBAR = "qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #FCFDFD, stop:1 #EDEFF2)"
GRADIENT_CARD = "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #FFFFFF, stop:1 #F5F7F9)"
GRADIENT_SURFACE = "qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #FFFFFF, stop:1 #EEF0F3)"
GRADIENT_NAV_CHECKED = "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #F1F2F5, stop:1 #FBFCFD)"
GRADIENT_ACCENT = "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #4A5058, stop:1 #24282E)"
GRADIENT_ACCENT_PRESSED = "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #24282E, stop:1 #15171A)"

FONT_STACK = ('"Segoe UI Variable Text", "Segoe UI Variable", "Segoe UI", '
              "-apple-system, BlinkMacSystemFont, "
              '".AppleSystemUIFont", "Helvetica Neue", '
              '"Inter", sans-serif')

MONOSPACE_STACK = 'Consolas, Menlo, Monaco, "SF Mono", monospace'


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
        background: {GRADIENT_PAGE};
    }}
    QDialog, QMessageBox {{
        background: {BG};
    }}
    QMessageBox QLabel, QInputDialog QLabel {{
        color: {TEXT};
        background: transparent;
    }}
    QScrollArea#PageScroll, QScrollArea#PageScroll > QWidget, QWidget#Page {{
        background: {GRADIENT_PAGE};
    }}
    QWidget#Sidebar {{
        background: {GRADIENT_SIDEBAR};
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
        background: {GRADIENT_NAV_CHECKED};
        color: {TEXT};
        border-left: {_px(3)}px solid {ACCENT};
    }}
    QFrame#Card {{
        background: {GRADIENT_CARD};
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
    }}
    QLabel#StatusChip[tone="success"] {{
        background: rgba(63, 185, 122, 0.18);
        color: {SUCCESS};
    }}
    QLabel#StatusChip[tone="warn"] {{
        background: rgba(229, 83, 75, 0.16);
        color: {ERROR};
    }}
    QLabel#StatusChip[tone="accent"] {{
        background: rgba(242, 169, 59, 0.18);
        color: {ACCENT};
    }}
    QPushButton {{
        background: {GRADIENT_SURFACE};
        border: {_px(1)}px solid {BORDER};
        border-radius: {_px(8)}px;
        padding: {_px(7)}px {_px(16)}px;
    }}
    QPushButton:hover {{
        border-color: {ACCENT};
    }}
    QPushButton:pressed {{
        background: {CARD_HOVER};
    }}
    QPushButton#CheckItem {{
        border-radius: {_px(14)}px;
        padding: {_px(5)}px {_px(12)}px;
        color: {TEXT_MUTED};
    }}
    QPushButton#CheckItem[state="done"] {{
        background: rgba(63, 185, 122, 0.18);
        border-color: {SUCCESS};
        color: {SUCCESS};
    }}
    QPushButton#CheckItem[state="captured"] {{
        background: rgba(242, 169, 59, 0.14);
        border-color: {ACCENT};
        color: {ACCENT};
    }}
    QPushButton#Primary {{
        background: {GRADIENT_ACCENT};
        color: {BG};
        border: none;
        font-weight: 600;
    }}
    QPushButton#Primary:pressed {{
        background: {GRADIENT_ACCENT_PRESSED};
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
        background: {GRADIENT_ACCENT};
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
