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
    """
