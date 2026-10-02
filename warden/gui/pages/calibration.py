"""Calibration - HANDOFF section 7.4: capture a template, sample an HSV
range, adjust a detector's ROI, and see a live detection overlay - all in
under a minute per screen. Also the unknown-screen gallery (section 8.8).
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from warden import paths
from warden.config.schema import DETECTOR_NAMES, SLOTS
from warden.flows.calibration import (
    apply_hsv,
    apply_roi,
    list_unknown_frames,
    make_template_from_unknown,
    sample_hsv_from_selection,
    save_template_from_frame,
)
from warden.flows.loadout import weapon_template_path
from warden.gui.context import AppContext
from warden.gui.widgets import ImageCanvas, card, muted, page_header, row, section_label
from warden.vision.detectors import Detector
from warden.vision.templates import TemplateLibrary


def _weapon_template_path_for(name: str) -> str:
    return f"{name}.png"


class CalibrationPage(QWidget):
    def __init__(self, ctx: AppContext, templates_root: Path | None = None):
        super().__init__()
        self.ctx = ctx
        self._frame = None
        self._weapon_frame_store = None
        # Injectable so tests never write into the real checked-in templates/
        # folder - see warden-testing-safety memory for why this matters.
        self._templates_root = templates_root or paths.repo_root()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)
        layout.addWidget(page_header("Calibration"))

        tabs = QTabWidget()
        tabs.addTab(self._build_wizard_tab(), "Detector wizard")
        tabs.addTab(self._build_weapon_tab(), "Weapon templates")
        tabs.addTab(self._build_gallery_tab(), "Unknown gallery")
        layout.addWidget(tabs, 1)

    # -- detector wizard -------------------------------------------------------

    def _build_wizard_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.addWidget(muted("Pick a screen, capture it (live, or load a saved image), "
                               "drag a box over the part that matters, then save a template "
                               "and/or apply it as that detector's color range and ROI."))

        top_row = QHBoxLayout()
        self.screen_combo = QComboBox()
        self.screen_combo.addItems(list(DETECTOR_NAMES))
        top_row.addWidget(QLabel("Screen:"))
        top_row.addWidget(self.screen_combo)
        capture_btn = QPushButton("Capture live frame")
        capture_btn.clicked.connect(self._capture_live)
        load_btn = QPushButton("Load image…")
        load_btn.clicked.connect(self._load_image)
        top_row.addWidget(capture_btn)
        top_row.addWidget(load_btn)
        top_row.addStretch(1)
        layout.addLayout(top_row)

        self.canvas = ImageCanvas()
        self.canvas.setMinimumHeight(360)
        layout.addWidget(self.canvas, 1)

        action_row = QHBoxLayout()
        save_tpl_btn = QPushButton("Save selection as template")
        save_tpl_btn.clicked.connect(self._save_template)
        sample_btn = QPushButton("Sample HSV from selection")
        sample_btn.clicked.connect(self._sample_hsv)
        roi_btn = QPushButton("Set as detector ROI")
        roi_btn.clicked.connect(self._set_roi)
        detect_btn = QPushButton("Run detection", objectName="Primary")
        detect_btn.clicked.connect(self._run_detection)
        for b in (save_tpl_btn, sample_btn, roi_btn, detect_btn):
            action_row.addWidget(b)
        layout.addLayout(action_row)

        self.result_label = muted("")
        layout.addWidget(self.result_label)
        return tab

    def _capture_live(self) -> None:
        loop = self.ctx.tick_loop
        if loop is None or loop._client_rect is None:
            self.result_label.setText("No live client window - start a session first, or load an image.")
            return
        self._frame = loop.capturer.grab(loop._client_rect)
        self.canvas.set_frame(self._frame)
        self.result_label.setText("Captured live frame.")

    def _load_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Load calibration image", "", "Images (*.png *.jpg *.bmp)")
        if not path:
            return
        import cv2

        frame = cv2.imread(path)
        if frame is None:
            self.result_label.setText(f"Could not read {path}")
            return
        self._frame = frame
        self.canvas.set_frame(frame)
        self.result_label.setText(f"Loaded {Path(path).name}")

    def _selection_or_warn(self):
        sel = self.canvas.selection_fractions()
        if self._frame is None or sel is None:
            self.result_label.setText("Capture a frame and drag a selection first.")
            return None
        return sel

    def _save_template(self) -> None:
        sel = self._selection_or_warn()
        if sel is None:
            return
        name = self.screen_combo.currentText()
        templates = TemplateLibrary(self._templates_root)
        path = save_template_from_frame(templates, f"templates/{_weapon_template_path_for(name)}", self._frame, sel)
        self.result_label.setText(f"Saved template: {path}")

    def _sample_hsv(self) -> None:
        sel = self._selection_or_warn()
        if sel is None:
            return
        lower, upper = sample_hsv_from_selection(self._frame, sel)
        name = self.screen_combo.currentText()
        cfg = self.ctx.app.detectors.get(name)
        if cfg is None:
            self.result_label.setText(f"'{name}' has no detector config section yet.")
            return
        self.ctx.app.detectors[name] = apply_hsv(cfg, lower, upper)
        self.ctx.save_app_config()
        self.result_label.setText(f"HSV range applied to '{name}': lower={lower} upper={upper}")

    def _set_roi(self) -> None:
        sel = self._selection_or_warn()
        if sel is None:
            return
        name = self.screen_combo.currentText()
        cfg = self.ctx.app.detectors.get(name)
        if cfg is None:
            self.result_label.setText(f"'{name}' has no detector config section yet.")
            return
        self.ctx.app.detectors[name] = apply_roi(cfg, sel)
        self.ctx.save_app_config()
        self.result_label.setText(f"ROI applied to '{name}': {[round(v, 3) for v in sel]}")

    def _run_detection(self) -> None:
        if self._frame is None:
            self.result_label.setText("Capture a frame first.")
            return
        name = self.screen_combo.currentText()
        cfg = self.ctx.app.detectors.get(name)
        if cfg is None:
            self.result_label.setText(f"'{name}' has no detector config section yet.")
            return
        templates = TemplateLibrary(self._templates_root)
        detector = Detector(name, cfg, templates)
        result = detector.evaluate(self._frame)
        if result.box:
            self.canvas._selection_px = None  # clear the drag selection so the detection box is unambiguous
        self.result_label.setText(
            f"'{name}': hit={result.hit} confidence={result.confidence:.2f}"
            + (f" box={[round(v, 3) for v in result.box]}" if result.box else "")
        )

    # -- weapon templates -------------------------------------------------------

    def _build_weapon_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.addWidget(muted(
            "This is what makes a specific weapon selectable in the loadout picker "
            "(the Loadout page's 'Verify now' and the auto-equip logic both need this, "
            "separately from the detector templates on the other tab). Open the weapon "
            "picker in-game, land on the slot's category, capture, then drag a box "
            "tightly around the weapon's tile - its icon and/or name."
        ))

        top_row = QHBoxLayout()
        self.weapon_slot_combo = QComboBox()
        self.weapon_slot_combo.addItems(list(SLOTS))
        self.weapon_name_combo = QComboBox()
        self.weapon_name_combo.setEditable(True)
        self.weapon_slot_combo.currentTextChanged.connect(self._refresh_weapon_name_options)
        top_row.addWidget(QLabel("Slot:"))
        top_row.addWidget(self.weapon_slot_combo)
        top_row.addWidget(QLabel("Weapon:"))
        top_row.addWidget(self.weapon_name_combo)
        capture_btn = QPushButton("Capture live frame")
        capture_btn.clicked.connect(self._weapon_capture_live)
        load_btn = QPushButton("Load image…")
        load_btn.clicked.connect(self._weapon_load_image)
        top_row.addWidget(capture_btn)
        top_row.addWidget(load_btn)
        top_row.addStretch(1)
        layout.addLayout(top_row)

        self.weapon_canvas = ImageCanvas()
        self.weapon_canvas.setMinimumHeight(360)
        layout.addWidget(self.weapon_canvas, 1)

        save_btn = QPushButton("Save selection as this weapon's template", objectName="Primary")
        save_btn.clicked.connect(self._save_weapon_template)
        layout.addWidget(save_btn)
        self.weapon_result = muted("")
        layout.addWidget(self.weapon_result)

        self._refresh_weapon_name_options(self.weapon_slot_combo.currentText())
        return tab

    def _refresh_weapon_name_options(self, slot: str) -> None:
        self.weapon_name_combo.clear()
        names = list(getattr(self.ctx.app.owned_weapons, slot, []) or [])
        preset_value = getattr(self.ctx.preset.loadout, slot, "") if not self.ctx.preset.loadout.random else ""
        if preset_value and preset_value not in names:
            names.insert(0, preset_value)
        self.weapon_name_combo.addItems(names)

    def _weapon_capture_live(self) -> None:
        loop = self.ctx.tick_loop
        if loop is None or loop._client_rect is None:
            self.weapon_result.setText("No live client window - start a session first, or load an image.")
            return
        self._weapon_frame_store = loop.capturer.grab(loop._client_rect)
        self.weapon_canvas.set_frame(self._weapon_frame_store)
        self.weapon_result.setText("Captured live frame.")

    def _weapon_load_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Load calibration image", "", "Images (*.png *.jpg *.bmp)")
        if not path:
            return
        import cv2

        frame = cv2.imread(path)
        if frame is None:
            self.weapon_result.setText(f"Could not read {path}")
            return
        self._weapon_frame_store = frame
        self.weapon_canvas.set_frame(frame)
        self.weapon_result.setText(f"Loaded {Path(path).name}")

    def _save_weapon_template(self) -> None:
        sel = self.weapon_canvas.selection_fractions()
        name = self.weapon_name_combo.currentText().strip()
        if self._weapon_frame_store is None or sel is None:
            self.weapon_result.setText("Capture a frame and drag a selection first.")
            return
        if not name:
            self.weapon_result.setText("Type the weapon's name first (must match the preset exactly).")
            return
        slot = self.weapon_slot_combo.currentText()
        templates = TemplateLibrary(self._templates_root / self.ctx.app.weapon_templates_dir)
        path = save_template_from_frame(templates, weapon_template_path(slot, name), self._weapon_frame_store, sel)
        self.weapon_result.setText(f"Saved: {path}")

    # -- unknown gallery -------------------------------------------------------

    def _build_gallery_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.addWidget(muted("Every screen Warden couldn't recognize gets saved here. "
                               "Pick one, drag a region over the part that identifies it, "
                               "and turn it into a new template."))

        body = QHBoxLayout()
        list_card, list_layout = card()
        list_layout.addWidget(section_label("Unknown frames"))
        self.gallery_list = QListWidget()
        self.gallery_list.currentTextChanged.connect(self._load_gallery_frame)
        list_layout.addWidget(self.gallery_list)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._refresh_gallery)
        list_layout.addWidget(refresh_btn)
        body.addWidget(list_card, 1)

        preview_card, preview_layout = card()
        self.gallery_canvas = ImageCanvas()
        preview_layout.addWidget(self.gallery_canvas, 1)
        make_row = QHBoxLayout()
        self.gallery_name = QComboBox()
        self.gallery_name.setEditable(True)
        self.gallery_name.addItems(list(DETECTOR_NAMES))
        make_btn = QPushButton("Make template from selection", objectName="Primary")
        make_btn.clicked.connect(self._make_template_from_gallery)
        make_row.addWidget(self.gallery_name)
        make_row.addWidget(make_btn)
        preview_layout.addLayout(make_row)
        self.gallery_result = muted("")
        preview_layout.addWidget(self.gallery_result)
        body.addWidget(preview_card, 2)
        layout.addLayout(body)

        self._refresh_gallery()
        return tab

    def _refresh_gallery(self) -> None:
        self.gallery_list.clear()
        self.gallery_list.addItems([p.name for p in list_unknown_frames(paths.data_dir("unknown"))])

    def _load_gallery_frame(self, name: str) -> None:
        if not name:
            return
        import cv2

        path = paths.data_dir("unknown") / name
        frame = cv2.imread(str(path))
        if frame is not None:
            self.gallery_canvas.set_frame(frame)

    def _make_template_from_gallery(self) -> None:
        item = self.gallery_list.currentItem()
        sel = self.gallery_canvas.selection_fractions()
        if item is None or sel is None:
            self.gallery_result.setText("Pick a frame and drag a selection first.")
            return
        templates = TemplateLibrary(self._templates_root)
        unknown_path = paths.data_dir("unknown") / item.text()
        template_path = f"templates/{self.gallery_name.currentText()}.png"
        try:
            saved = make_template_from_unknown(templates, unknown_path, template_path, sel)
        except ValueError as exc:
            self.gallery_result.setText(str(exc))
            return
        self.gallery_result.setText(f"Saved: {saved}")
