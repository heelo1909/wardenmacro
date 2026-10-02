"""Loadout - HANDOFF section 7.2."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from warden.config.loader import load_preset
from warden.config.schema import Contract, Preset
from warden.gui.context import AppContext
from warden.gui.widgets import card, page_header, section_label
from warden.gui.widgets import ResponsiveRow


class LoadoutPage(QWidget):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)
        layout.addWidget(page_header("Loadout"))

        body = ResponsiveRow(breakpoint=640)
        layout.addWidget(body)

        # -- preset list ---------------------------------------------------
        list_card, list_layout = card()
        list_layout.addWidget(section_label("Presets"))
        self.preset_list = QListWidget()
        self.preset_list.addItems(sorted(ctx.available_presets()))
        current = self.preset_list.findItems(ctx.preset_id, Qt.MatchExactly)
        if current:
            self.preset_list.setCurrentItem(current[0])
        self.preset_list.currentTextChanged.connect(self._load_selected)
        list_layout.addWidget(self.preset_list)
        btn_row = QHBoxLayout()
        new_btn, rename_btn, delete_btn = QPushButton("New"), QPushButton("Rename"), QPushButton("Delete")
        new_btn.clicked.connect(self._new_preset)
        rename_btn.clicked.connect(self._rename_preset)
        delete_btn.clicked.connect(self._delete_preset)
        for b in (new_btn, rename_btn, delete_btn):
            btn_row.addWidget(b)
        list_layout.addLayout(btn_row)
        body.add(list_card, 1)

        # -- editor ---------------------------------------------------
        editor_card, editor_layout = card()
        editor_layout.addWidget(section_label("Slots"))
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        self.random_box = QCheckBox("Random (pick from owned_weapons each match)")
        self.preset_list.setMinimumHeight(120)
        form.addRow(self.random_box)
        self.slot_edits = {}
        for slot in ("primary", "secondary", "melee", "utility"):
            edit = QLineEdit()
            self.slot_edits[slot] = edit
            form.addRow(slot.title(), edit)
        editor_layout.addLayout(form)

        verify_row = QHBoxLayout()
        self.verify_btn = QPushButton("Verify now")
        self.verify_btn.clicked.connect(self._verify_now)
        verify_row.addWidget(self.verify_btn)
        self.verify_result = QLabel("")
        self.verify_result.setObjectName("Muted")
        self.verify_result.setWordWrap(True)
        verify_row.addWidget(self.verify_result, 1)
        editor_layout.addLayout(verify_row)

        save_btn = QPushButton("Save preset", objectName="Primary")
        save_btn.clicked.connect(self._save)
        editor_layout.addWidget(save_btn)
        editor_layout.addStretch(1)
        body.add(editor_card, 2)

        self._editing_id = ctx.preset_id
        self._populate(ctx.preset)

    def _populate(self, preset: Preset) -> None:
        self.random_box.setChecked(preset.loadout.random)
        for slot, edit in self.slot_edits.items():
            edit.setText(getattr(preset.loadout, slot))

    def _load_selected(self, preset_id: str) -> None:
        if not preset_id:
            return
        path = self.ctx.available_presets().get(preset_id)
        if path is None:
            return
        self._editing_id = preset_id
        self._populate(load_preset(path))
        self.verify_result.setText("")

    def _save(self) -> None:
        path = self.ctx.available_presets().get(self._editing_id)
        if path is None:
            return
        preset = load_preset(path)
        preset.loadout.random = self.random_box.isChecked()
        for slot, edit in self.slot_edits.items():
            setattr(preset.loadout, slot, edit.text())
        from warden.config.loader import save_model

        save_model(preset, path)
        if self._editing_id == self.ctx.preset_id:
            self.ctx.preset = preset

    def _new_preset(self) -> None:
        name, ok = QInputDialog.getText(self, "New preset", "Preset id (letters/numbers/underscore):")
        if not ok or not name:
            return
        preset_id = name.strip().lower().replace(" ", "_")
        try:
            self.ctx.create_preset(preset_id, Preset(name=name, contract=Contract(label=name)))
        except FileExistsError:
            QMessageBox.warning(self, "Warden", f"Preset '{preset_id}' already exists.")
            return
        self.preset_list.addItem(preset_id)

    def _rename_preset(self) -> None:
        item = self.preset_list.currentItem()
        if item is None:
            return
        old_id = item.text()
        new_name, ok = QInputDialog.getText(self, "Rename preset", "Display name:")
        if not ok or not new_name:
            return
        path = self.ctx.available_presets()[old_id]
        preset = load_preset(path)
        preset.name = new_name
        from warden.config.loader import save_model

        save_model(preset, path)

    def _delete_preset(self) -> None:
        item = self.preset_list.currentItem()
        if item is None:
            return
        preset_id = item.text()
        try:
            self.ctx.delete_preset(preset_id)
        except ValueError as exc:
            QMessageBox.warning(self, "Warden", str(exc))
            return
        self.preset_list.takeItem(self.preset_list.row(item))

    def _verify_now(self) -> None:
        loop = self.ctx.tick_loop
        if loop is None:
            self.verify_result.setText("Start a session first to verify against the live client.")
            return
        loop.actions.loadout.reset(self.ctx.preset.loadout.slots())
        while not loop.actions.loadout.tick():
            pass
        parts = [f"{o.slot}: {'OK' if o.verified else 'FAIL'}" for o in loop.actions.loadout.result.slots.values()]
        self.verify_result.setText(", ".join(parts) or "no slots to verify")
