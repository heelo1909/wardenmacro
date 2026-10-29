"""Optional OCR. Every caller must cope with ``read_text`` returning None."""

from __future__ import annotations

import logging
import os
import re
import shutil
from functools import lru_cache

import cv2
import numpy as np

log = logging.getLogger(__name__)

_COMMON_PATHS = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
)


_enabled = True  # macOS turns this off at startup unless config mac.ocr is on


def set_enabled(on: bool) -> None:
    """Switch OCR on/off for this process (``platform.macos.configure`` calls it on a Mac)."""
    global _enabled
    _enabled = bool(on)


def _engine():
    return _find_engine() if _enabled else None


@lru_cache(maxsize=1)
def _find_engine():
    try:
        import pytesseract
    except ImportError:
        return None
    exe = shutil.which("tesseract") or next((p for p in _COMMON_PATHS if os.path.exists(p)), None)
    if exe is None:
        return None
    pytesseract.pytesseract.tesseract_cmd = exe
    try:
        pytesseract.get_tesseract_version()
    except Exception:
        return None
    return pytesseract


def available() -> bool:
    return _engine() is not None


def read_text(image: np.ndarray, psm: int = 7) -> str | None:
    engine = _engine()
    if engine is None or image is None or image.size == 0:
        return None
    gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    if gray.shape[0] < 40:  # tesseract likes text ~30px tall
        factor = 40 / gray.shape[0]
        gray = cv2.resize(gray, None, fx=factor, fy=factor, interpolation=cv2.INTER_CUBIC)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    if binary.mean() < 127:  # light text on dark -> invert to dark on light
        binary = 255 - binary
    try:
        return engine.image_to_string(binary, config=f"--psm {psm}").strip()
    except Exception as exc:
        log.debug("ocr failed: %s", exc)
        return None


def contains_any(text: str | None, needles: list[str]) -> bool:
    if not text:
        return False
    hay = re.sub(r"\s+", " ", text.upper())
    return any(n.upper() in hay for n in needles)


def error_code(text: str | None) -> int | None:
    if not text:
        return None
    m = re.search(r"error\s*code[:\s]*(\d{3})", text, re.IGNORECASE)
    return int(m.group(1)) if m else None
