"""Synthetic frame builders shared by vision tests."""

from __future__ import annotations

import cv2
import numpy as np

W, H = 1280, 720


def blank(w: int = W, h: int = H, bgr=(18, 18, 18)) -> np.ndarray:
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    frame[:] = bgr
    return frame


def draw_frac_rect(frame: np.ndarray, roi, bgr) -> np.ndarray:
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = roi
    cv2.rectangle(frame, (int(x1 * w), int(y1 * h)), (int(x2 * w), int(y2 * h)), bgr, -1)
    return frame


GREEN_BGR = (60, 200, 70)  # a solid "Roblox green" button colour in BGR


def green_button_frame(roi=(0.42, 0.85, 0.58, 0.95), w: int = W, h: int = H) -> np.ndarray:
    return draw_frac_rect(blank(w, h), roi, GREEN_BGR)


def make_template(w: int = 120, h: int = 40, bgr=(200, 200, 200)) -> np.ndarray:
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[:] = bgr
    cv2.rectangle(img, (4, 4), (w - 5, h - 5), (40, 40, 40), 2)
    return img


def paste(frame: np.ndarray, patch: np.ndarray, at_frac, scale: float = 1.0) -> np.ndarray:
    h, w = frame.shape[:2]
    ph, pw = patch.shape[:2]
    if scale != 1.0:
        patch = cv2.resize(patch, (int(pw * scale), int(ph * scale)))
        ph, pw = patch.shape[:2]
    x, y = int(at_frac[0] * w), int(at_frac[1] * h)
    frame[y:y + ph, x:x + pw] = patch
    return frame
