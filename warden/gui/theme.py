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


def stylesheet() -> str:
    return f"""
    * {{
        font-family: {FONT_STACK};
        font-size: 10pt;
        color: {TEXT};
    }}
    QMainWindow, QWidget#Root {{
        background: {BG};
    }}
    QWidget#Sidebar {{
        background: {BG};
        border-right: 1px solid {BORDER};
    }}
    QLabel#Wordmark {{
        font-size: 15pt;
        font-weight: 600;
        color: {ACCENT};
        padding: 18px 18px 14px 18px;
    }}
    QPushButton#NavButton {{
        background: transparent;
        border: none;
        border-radius: 8px;
        padding: 9px 14px;
        margin: 2px 10px;
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
        border-left: 3px solid {ACCENT};
    }}
    QFrame#Card {{
        background: {CARD};
        border: 1px solid {BORDER};
        border-radius: 12px;
    }}
    QLabel#PageTitle {{
        font-size: 18pt;
        font-weight: 600;
    }}
    QLabel#Muted {{
        color: {TEXT_MUTED};
    }}
    QLabel#Section {{
        color: {TEXT_MUTED};
        font-size: 8pt;
        font-weight: 600;
        letter-spacing: 1px;
    }}
    QLabel#StatValue {{
        font-size: 17pt;
        font-weight: 600;
    }}
    QLabel#StatusChip {{
        border-radius: 10px;
        padding: 4px 14px;
        font-weight: 600;
        background: {CARD_HOVER};
        color: {TEXT_MUTED};
        max-width: 110px;
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
        border: 1px solid {BORDER};
        border-radius: 8px;
        padding: 7px 16px;
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
        border-top: 1px solid {BORDER};
    }}
    QListWidget, QTableWidget, QPlainTextEdit, QTextEdit {{
        background: {BG};
        color: {TEXT};
        border: 1px solid {BORDER};
        border-radius: 8px;
        padding: 4px;
    }}
    QListWidget::item, QTableWidget::item {{
        padding: 3px 4px;
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
        border-bottom: 1px solid {BORDER};
        padding: 4px 6px;
    }}
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
        background: {BG};
        color: {TEXT};
        border: 1px solid {BORDER};
        border-radius: 6px;
        padding: 4px 8px;
        selection-background-color: {ACCENT};
    }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
        border-color: {ACCENT};
    }}
    QComboBox::drop-down {{
        border: none;
        width: 18px;
    }}
    QComboBox QAbstractItemView {{
        background: {CARD};
        color: {TEXT};
        selection-background-color: {CARD_HOVER};
        border: 1px solid {BORDER};
        outline: none;
    }}
    QCheckBox {{
        spacing: 8px;
    }}
    QCheckBox::indicator {{
        width: 16px;
        height: 16px;
        border-radius: 4px;
        border: 1px solid {BORDER};
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
    QScrollBar:vertical {{
        background: transparent;
        width: 10px;
        margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background: {CARD_HOVER};
        border-radius: 5px;
        min-height: 24px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}
    """
