"""Calibration - HANDOFF section 7.4.

The full wizard (capture a region, sample an HSV range, live detection
overlay, test-click) is Phase 8 scope. This page is useful in the
meantime: it tells you exactly which template images the current config
and active preset still need, so there's a concrete checklist once the
wizard exists.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QListWidget, QVBoxLayout, QWidget

from warden import paths
from warden.flows.loadout import weapon_template_path
from warden.gui.context import AppContext
from warden.gui.widgets import card, muted, page_header, section_label


class CalibrationPage(QWidget):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)
        layout.addWidget(page_header("Calibration"))
        layout.addWidget(muted("The step-by-step wizard (capture a region, sample a color range, "
                               "live detection overlay) arrives in Phase 8. For now, here's what "
                               "still needs a captured template image before detection will work."))

        body, body_layout = card()
        body_layout.addWidget(section_label("Missing templates"))
        self.list = QListWidget()
        body_layout.addWidget(self.list)
        layout.addWidget(body, 1)
        self._refresh()

    def _refresh(self) -> None:
        self.list.clear()
        root = paths.repo_root()
        for name, det in sorted(self.ctx.app.detectors.items()):
            if det.template is not None:
                full = root / det.template.path
                if not full.exists():
                    self.list.addItem(f"detector '{name}': {det.template.path}")
        weapons_root = root / self.ctx.app.weapon_templates_dir
        slots = self.ctx.preset.loadout.slots() if not self.ctx.preset.loadout.random else {}
        for slot, weapon in slots.items():
            if not weapon:
                continue
            full = weapons_root / weapon_template_path(slot, weapon)
            if not full.exists():
                self.list.addItem(f"loadout slot '{slot}': {weapon}")
        if self.list.count() == 0:
            self.list.addItem("Nothing missing for the active preset.")
