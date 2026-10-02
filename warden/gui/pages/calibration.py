"""Calibration - HANDOFF section 7.4: capture a template, sample an HSV
range, adjust a detector's ROI, and see a live detection overlay - all in
under a minute per screen. Also the unknown-screen gallery (section 8.8).

Easiest path (2026-10-02): "Auto-capture screens" walks through each screen
with a small on-top panel and takes the screenshots by itself; then pick each
screen in the checklist, drag one box, press "Save this screen".
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

from PySide6.QtCore import Qt, QTimer

from warden import paths
from warden.config.schema import DETECTOR_NAMES, SLOTS
from warden.flows.calibration import (
    CAPTURE_STEPS,
    GUIDES_BY_KEY,
    SCREEN_GUIDES,
    apply_hsv,
    apply_roi,
    calibration_capture_path,
    is_screen_calibrated,
    list_unknown_frames,
    make_template_from_unknown,
    quick_calibrate,
    sample_hsv_from_selection,
    save_template_from_frame,
    selection_problem,
)
from warden.flows.loadout import weapon_template_path
from warden.gui.context import AppContext
from warden.gui.widgets import FlowLayout, ImageCanvas, ResponsiveRow, card, flow, muted, page_header, row, section_label
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
        self._templates_root = templates_root or paths.templates_home()
        self._templates_fallbacks = [] if templates_root else [paths.repo_root()]

        self._frame_source: str | None = None  # screen whose auto-capture is on the canvas
        self._guided = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)
        layout.addWidget(page_header("Calibration"))
        layout.addWidget(self._build_checklist())

        tabs = QTabWidget()
        self.tabs = tabs
        tabs.addTab(self._build_wizard_tab(), "Detector wizard")
        tabs.addTab(self._build_weapon_tab(), "Weapon templates")
        tabs.addTab(self._build_gallery_tab(), "Unknown gallery")
        tabs.currentChanged.connect(lambda i: i == 1 and self._autoload_weapon_frame())
        layout.addWidget(tabs, 1)
        self._refresh_checklist()

    # -- setup checklist + auto-capture -------------------------------------------------------

    def _build_checklist(self) -> QWidget:
        frame, inner = card()
        inner.addWidget(section_label("Setup checklist"))
        inner.addWidget(muted(
            "1) Click Auto-capture and follow the little panel over Roblox - it takes each "
            "screenshot for you.  2) Click a screen below, drag ONE small box around the thing "
            "it describes, and press Save this screen. Green = Warden can see it."))
        self.auto_btn = QPushButton("▶  Auto-capture screens", objectName="Primary")
        self.auto_btn.clicked.connect(self.start_guided_capture)
        self.teach_btn = QPushButton("🎯  Learn my loadout")
        self.teach_btn.setToolTip("Pick your weapons once yourself in RIVALS - Warden watches and learns them.")
        self.teach_btn.clicked.connect(self.start_loadout_teacher)
        inner.addWidget(flow(self.auto_btn, self.teach_btn))
        self.checklist_buttons: dict[str, QPushButton] = {}
        for guide in SCREEN_GUIDES:
            btn = QPushButton(guide.title)
            btn.setObjectName("CheckItem")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _=False, k=guide.key: self.open_screen(k))
            self.checklist_buttons[guide.key] = btn
        inner.addWidget(flow(*self.checklist_buttons.values(), spacing=6))
        self.checklist_summary = muted("")
        inner.addWidget(self.checklist_summary)
        return frame

    def _refresh_checklist(self) -> None:
        templates = self._library()
        done_required = missing_required = 0
        for key, btn in self.checklist_buttons.items():
            guide = GUIDES_BY_KEY[key]
            ok = is_screen_calibrated(self.ctx.app, key, templates)
            captured = calibration_capture_path(key).exists()
            mark = "✓" if ok else ("●" if captured else "○")
            btn.setText(f"{mark}  {guide.title}" + ("" if guide.required else " (optional)"))
            btn.setProperty("state", "done" if ok else ("captured" if captured else "todo"))
            btn.style().unpolish(btn)
            btn.style().polish(btn)
            btn.setToolTip(f"{guide.go_to}\nBox: {guide.box_hint}")
            if guide.required:
                done_required += ok
                missing_required += not ok
        if missing_required:
            self.checklist_summary.setText(
                f"{done_required} of {done_required + missing_required} required screens done "
                "(○ = not captured yet, ● = captured, needs a box, ✓ = done).")
        else:
            self.checklist_summary.setText("All required screens are done - Warden can get into FFA. "
                                           "The optional ones improve respawn/loadout handling.")

    def open_screen(self, key: str) -> None:
        """Jump to the wizard with this screen selected and its capture loaded."""
        self.tabs.setCurrentIndex(0)
        self.screen_combo.setCurrentText(key)
        self._load_auto_capture(key, force=True)

    def start_guided_capture(self) -> None:
        from warden.gui.guided_capture import GuidedCapture

        if self._guided is not None:
            return
        anchor = None
        try:
            from warden.vision.capture import find_roblox_client

            found = find_roblox_client()
            if found is not None:
                _hwnd, rect = found
                anchor = (rect.left, rect.top, rect.width, rect.height)
        except Exception:
            anchor = None
        self.result_label.setText("Auto-capture running - follow the panel in the top-right of Roblox.")
        self._guided = GuidedCapture(CAPTURE_STEPS, grab=self._grab_for_guided,
                                     on_captured=self._on_guided_capture,
                                     on_finished=self._on_guided_finished, anchor=anchor)
        window = self.window()
        if window is not self:
            window.showMinimized()
        self._guided.show()

    def start_loadout_teacher(self) -> None:
        from warden.gui.loadout_teacher import LoadoutTeacher, start_pynput_click_listener
        from warden.vision.capture import MssCapturer, WindowCapturer, find_roblox_client

        if getattr(self, "_teacher", None) is not None:
            return
        preset = self.ctx.preset
        weapons = {} if preset.loadout.random else {k: v for k, v in preset.loadout.slots().items() if v}
        if not weapons:
            self.weapon_result.setText("Set your weapons on the Loadout page first (a preset that isn't Random).")
            self.result_label.setText(self.weapon_result.text())
            return
        anchor = None
        try:
            found = find_roblox_client()
            if found is not None:
                anchor = (found[1].left, found[1].top, found[1].width, found[1].height)
        except Exception:
            anchor = None
        try:
            listener = start_pynput_click_listener
        except Exception:
            listener = None
        self._teacher = LoadoutTeacher(
            weapons, learn=self._learn_weapon, on_finished=self._on_teacher_finished,
            find_client=find_roblox_client, make_capturer=lambda: WindowCapturer(fallback=MssCapturer()),
            start_listener=listener, anchor=anchor)
        window = self.window()
        if window is not self:
            window.showMinimized()
        self._teacher.show()

    def _learn_weapon(self, slot: str, weapon: str, frame, fx: float, fy: float) -> bool:
        from warden.flows.loadout import learn_row_template

        crop = learn_row_template(frame, fx, fy, self.ctx.app.loadout_ui)
        if crop is None:
            return False
        self._library(self.ctx.app.weapon_templates_dir).save(weapon_template_path(slot, weapon), crop)
        if self.ctx.app.loadout_ui.mode != "sequential":
            # Learning from clicks only makes sense for RIVALS' one-list-per-slot picker.
            self.ctx.app.loadout_ui.mode = "sequential"
            self.ctx.save_app_config()
        return True

    def _on_teacher_finished(self, learned: list[str]) -> None:
        self._teacher = None
        window = self.window()
        if window is not self:
            window.showNormal()
            window.raise_()
            window.activateWindow()
        names = ", ".join(f"{s} ({getattr(self.ctx.preset.loadout, s)})" for s in learned)
        text = f"✓ Learned {names}. Warden will pick these at the start of each match." if learned \
            else "No weapons were learned."
        self.result_label.setText(text)
        self.weapon_result.setText(text)
        self._refresh_checklist()

    def _grab_for_guided(self):
        from warden.vision.capture import grab_roblox_client

        return grab_roblox_client(focus=False)

    def _on_guided_capture(self, keys, frame) -> None:
        import cv2

        for key in keys:
            cv2.imwrite(str(calibration_capture_path(key)), frame)

    def _on_guided_finished(self, captured: list[str]) -> None:
        self._guided = None
        window = self.window()
        if window is not self:
            window.showNormal()
            window.raise_()
            window.activateWindow()
        self._refresh_checklist()
        first = next((g.key for g in SCREEN_GUIDES if g.key in captured
                      and not is_screen_calibrated(self.ctx.app, g.key, self._library())), None)
        if first:
            self.open_screen(first)
            self.result_label.setText(f"Captured {len(set(captured))} screen(s). Now: "
                                      f"{GUIDES_BY_KEY[first].title} - drag a box around "
                                      f"{GUIDES_BY_KEY[first].box_hint}, then press Save this screen.")
        elif not captured:
            self.result_label.setText("Nothing was captured.")

    def _load_auto_capture(self, key: str, force: bool = False) -> bool:
        """Show the auto-captured screenshot for ``key`` if there is one (and
        the canvas isn't showing something the user captured by hand)."""
        path = calibration_capture_path(key)
        if not path.exists() or (not force and self._frame is not None and self._frame_source is None):
            return False
        import cv2

        frame = cv2.imread(str(path))
        if frame is None:
            return False
        self._frame = frame
        self._frame_source = key
        self.canvas.set_frame(frame)
        return True

    def _on_screen_changed(self, key: str) -> None:
        guide = GUIDES_BY_KEY.get(key)
        if guide is not None:
            self.hint_label.setText(f"<b>{guide.title}</b> - in Roblox: {guide.go_to}<br>"
                                    f"Drag a box around: <b>{guide.box_hint}</b>")
        else:
            self.hint_label.setText(f"<b>{key}</b> - advanced detector; most people don't need this.")
        self._load_auto_capture(key)

    # -- detector wizard -------------------------------------------------------

    def _build_wizard_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        top_row_w = QWidget()
        top_row = FlowLayout(top_row_w)
        self.screen_combo = QComboBox()
        ordered = [g.key for g in SCREEN_GUIDES] + [n for n in DETECTOR_NAMES
                                                    if n not in GUIDES_BY_KEY]
        self.screen_combo.addItems(ordered)
        top_row.addWidget(QLabel("Screen:"))
        top_row.addWidget(self.screen_combo)
        capture_btn = QPushButton("Capture live frame")
        capture_btn.clicked.connect(self._capture_live)
        load_btn = QPushButton("Load image…")
        load_btn.clicked.connect(self._load_image)
        top_row.addWidget(capture_btn)
        top_row.addWidget(load_btn)
        layout.addWidget(top_row_w)

        self.hint_label = QLabel()
        self.hint_label.setWordWrap(True)
        self.hint_label.setTextFormat(Qt.RichText)
        layout.addWidget(self.hint_label)

        self.canvas = ImageCanvas()
        self.canvas.setMinimumHeight(300)
        layout.addWidget(self.canvas, 1)

        main_row_w = QWidget()
        main_row = FlowLayout(main_row_w)
        quick_btn = QPushButton("✓  Save this screen", objectName="Primary")
        quick_btn.clicked.connect(self._quick_save)
        main_row.addWidget(quick_btn)
        test_btn = QPushButton("Test")
        test_btn.clicked.connect(self._run_detection)
        main_row.addWidget(test_btn)
        layout.addWidget(main_row_w)

        action_row_w = QWidget()
        action_row = FlowLayout(action_row_w)
        action_row.addWidget(QLabel("Advanced:", objectName="Muted"))
        save_tpl_btn = QPushButton("Save selection as template")
        save_tpl_btn.clicked.connect(self._save_template)
        sample_btn = QPushButton("Sample HSV from selection")
        sample_btn.clicked.connect(self._sample_hsv)
        roi_btn = QPushButton("Set as detector ROI")
        roi_btn.clicked.connect(self._set_roi)
        for b in (save_tpl_btn, sample_btn, roi_btn):
            action_row.addWidget(b)
        layout.addWidget(action_row_w)

        self.result_label = muted("")
        layout.addWidget(self.result_label)
        self.screen_combo.currentTextChanged.connect(self._on_screen_changed)
        self._on_screen_changed(self.screen_combo.currentText())
        return tab

    def _quick_save(self) -> None:
        """One button: learn this screen from the box, then test it right away."""
        name = self.screen_combo.currentText()
        sel = self.canvas.selection_fractions()
        if self._frame is None:
            self.result_label.setText("Capture this screen first (Auto-capture, or Capture live frame).")
            return
        problem = selection_problem(sel)
        if problem:
            self.result_label.setText(problem)
            return
        if name not in self.ctx.app.detectors:
            self.result_label.setText(f"'{name}' has no detector config section yet.")
            return
        templates = self._library()
        new_cfg, how = quick_calibrate(self.ctx.app, name, self._frame, sel, templates)
        self.ctx.app.detectors[name] = new_cfg
        self.ctx.save_app_config()
        result = Detector(name, new_cfg, templates).evaluate(self._frame)
        title = GUIDES_BY_KEY[name].title if name in GUIDES_BY_KEY else name
        if result.hit:
            self.result_label.setText(f"✓ {title}: {how} - Warden can see it on this screenshot.")
        else:
            self.result_label.setText(f"⚠ {title}: {how}, but the test didn't find it again - "
                                      "try a slightly tighter box around something that doesn't move.")
        self._refresh_checklist()
        self._goto_next_todo(name)

    def _goto_next_todo(self, after: str) -> None:
        """After a successful save, move on to the next captured-but-unfinished screen."""
        templates = self._library()
        keys = [g.key for g in SCREEN_GUIDES]
        start = keys.index(after) + 1 if after in keys else 0
        for key in keys[start:]:
            if calibration_capture_path(key).exists() and not is_screen_calibrated(self.ctx.app, key, templates):
                previous = self.result_label.text()
                QTimer.singleShot(900, lambda k=key, p=previous: (
                    self.open_screen(k),
                    self.result_label.setText(f"{p}\nNext: {GUIDES_BY_KEY[k].title}.")))
                return

    def _library(self, subdir: str | None = None) -> TemplateLibrary:
        base = self._templates_root / subdir if subdir else self._templates_root
        fallbacks = [f / subdir if subdir else f for f in self._templates_fallbacks]
        return TemplateLibrary(base, fallbacks=fallbacks)

    def _grab_client(self):
        """A frame of the Roblox client - from the running session if there
        is one, otherwise straight from the window (no session needed, so
        nothing gets clicked while you calibrate).
        """
        loop = self.ctx.tick_loop
        if loop is not None and loop._client_rect is not None:
            return loop.capturer.grab(loop._client_rect)
        try:
            from warden.vision import capture

            frame = capture.grab_roblox_client()
            if frame is not None and getattr(capture.grab_roblox_client, "last_method", "window") == "screen":
                # Window capture unavailable -> a plain screen grab, which would
                # include Warden itself; get out of the way and grab again.
                window = self.window()
                window.showMinimized()
                try:
                    frame = capture.grab_roblox_client(focus=True)
                finally:
                    window.showNormal()
                    window.raise_()
                    window.activateWindow()
            return frame
        except Exception:
            return None

    def _capture_live(self) -> None:
        frame = self._grab_client()
        if frame is None:
            self.result_label.setText("Couldn't find the Roblox window - open Roblox (windowed is fine), "
                                      "or load a screenshot instead.")
            return
        self._frame = frame
        self._frame_source = None
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
        self._frame_source = None
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
        templates = self._library()
        cfg = self.ctx.app.detectors.get(name)
        rel = cfg.template.path if (cfg is not None and cfg.template is not None) else \
            f"templates/{_weapon_template_path_for(name)}"
        path = save_template_from_frame(templates, rel, self._frame, sel)
        note = ""
        if cfg is not None and cfg.method in ("color", "template") and (cfg.method != "template" or cfg.template is None):
            # A template was captured for a color detector (e.g. lobby_play):
            # switch it to template matching, otherwise the capture is never used.
            from warden.config.schema import TemplateSpec

            self.ctx.app.detectors[name] = cfg.model_copy(update={
                "method": "template", "template": TemplateSpec(path=rel, threshold=0.78),
            })
            self.ctx.save_app_config()
            note = f" - '{name}' now uses this template for detection"
        self.result_label.setText(f"Saved template: {path}{note}")
        self._refresh_checklist()

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
        templates = self._library()
        detector = Detector(name, cfg, templates)
        result = detector.evaluate(self._frame)
        if result.box:
            self.canvas._selection_px = None  # clear the drag selection so the detection box is unambiguous
        verdict = "✓ found" if result.hit else "✗ not found"
        self.result_label.setText(
            f"'{name}': {verdict} (hit={result.hit} confidence={result.confidence:.2f})"
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
            "picker in-game, land on the slot's category, capture (Auto-capture's weapon "
            "picker step loads here automatically), then drag a small box around just "
            "that weapon's row/tile - its name is usually the best part."
        ))

        top_row_w = QWidget()
        top_row = FlowLayout(top_row_w)
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
        layout.addWidget(top_row_w)

        self.weapon_canvas = ImageCanvas()
        self.weapon_canvas.setMinimumHeight(300)
        layout.addWidget(self.weapon_canvas, 1)

        save_btn = QPushButton("Save selection as this weapon's template", objectName="Primary")
        save_btn.clicked.connect(self._save_weapon_template)
        layout.addWidget(save_btn)
        teach_btn = QPushButton("🎯  Easiest: Learn my loadout (just pick your weapons in-game)")
        teach_btn.clicked.connect(self.start_loadout_teacher)
        layout.addWidget(teach_btn)
        self.weapon_result = muted("")
        layout.addWidget(self.weapon_result)

        self._refresh_weapon_name_options(self.weapon_slot_combo.currentText())
        return tab

    def _autoload_weapon_frame(self) -> bool:
        if self._weapon_frame_store is not None:
            return False
        path = calibration_capture_path("weapon_picker")
        if not path.exists():
            return False
        import cv2

        frame = cv2.imread(str(path))
        if frame is None:
            return False
        self._weapon_frame_store = frame
        self.weapon_canvas.set_frame(frame)
        self.weapon_result.setText("Loaded the auto-captured weapon picker.")
        return True

    def _refresh_weapon_name_options(self, slot: str) -> None:
        self.weapon_name_combo.clear()
        names = list(getattr(self.ctx.app.owned_weapons, slot, []) or [])
        preset_value = getattr(self.ctx.preset.loadout, slot, "") if not self.ctx.preset.loadout.random else ""
        if preset_value and preset_value not in names:
            names.insert(0, preset_value)
        self.weapon_name_combo.addItems(names)

    def _weapon_capture_live(self) -> None:
        frame = self._grab_client()
        if frame is None:
            self.weapon_result.setText("Couldn't find the Roblox window - open Roblox (windowed is fine), "
                                       "or load a screenshot instead.")
            return
        self._weapon_frame_store = frame
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
        problem = selection_problem(sel)
        if problem:
            self.weapon_result.setText(problem)
            return
        slot = self.weapon_slot_combo.currentText()
        templates = self._library(self.ctx.app.weapon_templates_dir)
        path = save_template_from_frame(templates, weapon_template_path(slot, name), self._weapon_frame_store, sel)
        self.weapon_result.setText(f"✓ Saved {slot} '{name}': {path}")

    # -- unknown gallery -------------------------------------------------------

    def _build_gallery_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.addWidget(muted("Every screen Warden couldn't recognize gets saved here. "
                               "Pick one, drag a region over the part that identifies it, "
                               "and turn it into a new template."))

        body = ResponsiveRow(breakpoint=560)
        list_card, list_layout = card()
        list_layout.addWidget(section_label("Unknown frames"))
        self.gallery_list = QListWidget()
        self.gallery_list.currentTextChanged.connect(self._load_gallery_frame)
        list_layout.addWidget(self.gallery_list)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._refresh_gallery)
        list_layout.addWidget(refresh_btn)
        body.add(list_card, 1)

        preview_card, preview_layout = card()
        self.gallery_canvas = ImageCanvas()
        preview_layout.addWidget(self.gallery_canvas, 1)
        make_row_w = QWidget()
        make_row = FlowLayout(make_row_w)
        self.gallery_name = QComboBox()
        self.gallery_name.setEditable(True)
        self.gallery_name.addItems(list(DETECTOR_NAMES))
        make_btn = QPushButton("Make template from selection", objectName="Primary")
        make_btn.clicked.connect(self._make_template_from_gallery)
        make_row.addWidget(self.gallery_name)
        make_row.addWidget(make_btn)
        preview_layout.addWidget(make_row_w)
        self.gallery_result = muted("")
        preview_layout.addWidget(self.gallery_result)
        body.add(preview_card, 2)
        layout.addWidget(body, 1)

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
        templates = self._library()
        unknown_path = paths.data_dir("unknown") / item.text()
        template_path = f"templates/{self.gallery_name.currentText()}.png"
        try:
            saved = make_template_from_unknown(templates, unknown_path, template_path, sel)
        except ValueError as exc:
            self.gallery_result.setText(str(exc))
            return
        self.gallery_result.setText(f"Saved: {saved}")
