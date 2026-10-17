"""Visual PSP mappings and saved user presets."""
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QComboBox, QPushButton, QToolButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QGroupBox, QSpinBox, QInputDialog, QMessageBox, QDialog)

from .config import ConfigError, quote, tokens
from .controls import SCHEME_LABELS, ACTION_LABELS, actions
from .mappings import Mapping, read_mappings, write_mappings, has_native_mappings, chord_text, game_actions
from .profiles import ProfileStore
from .resources import default_document
from .widgets import label, icon, ControllerCanvas, ChordDelegate
from .capture import CaptureDialog


class ControlsEditor(QWidget):
    edit_requested = Signal(object)
    scheme_selected = Signal(str)
    preset_saved = Signal(str)
    apply_requested = Signal()

    def __init__(self, profiles: ProfileStore, parent=None):
        super().__init__(parent)
        self.store = profiles
        self.doc = None
        self.scheme = "current"
        self.refreshing = False
        self.mappings = []
        self.control_combos = {}
        self.selected_profile = ""
        self.applied_bytes = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        row = QHBoxLayout()
        row.addWidget(label("Control scheme"))
        self.scheme_combo = QComboBox()
        for key, text in SCHEME_LABELS.items():
            self.scheme_combo.addItem(text, key)
        self.scheme_combo.currentIndexChanged.connect(self.scheme_changed)
        row.addWidget(self.scheme_combo)
        row.addSpacing(16)
        row.addWidget(label("My presets"))
        self.profile_combo = QComboBox()
        self.profile_combo.setMinimumWidth(170)
        self.profile_combo.currentIndexChanged.connect(self.profile_changed)
        row.addWidget(self.profile_combo, 1)
        self.load_profile_button = QPushButton("Load preset")
        self.load_profile_button.clicked.connect(self.load_profile)
        row.addWidget(self.load_profile_button)
        self.save_profile_button = QPushButton("Save preset…")
        self.save_profile_button.clicked.connect(self.save_profile)
        row.addWidget(self.save_profile_button)
        self.delete_profile_button = QToolButton()
        self.delete_profile_button.setIcon(icon("trash"))
        self.delete_profile_button.setToolTip("Delete saved preset")
        self.delete_profile_button.clicked.connect(self.delete_profile)
        row.addWidget(self.delete_profile_button)
        layout.addLayout(row)
        self.controller = ControllerCanvas()
        self.controller.setFixedHeight(154)
        self.controller.selected.connect(self.select_button)
        layout.addWidget(self.controller)
        self.notice = label("", "Muted", True)
        self.notice.hide()
        layout.addWidget(self.notice)
        row = QHBoxLayout()
        row.addWidget(label("Button mappings"))
        row.addStretch()
        reset = QPushButton("Restore defaults")
        reset.clicked.connect(self.restore_defaults)
        row.addWidget(reset)
        self.add_button = QPushButton("Map button…")
        self.add_button.setObjectName("Accent")
        self.add_button.clicked.connect(self.add_mapping)
        row.addWidget(self.add_button)
        layout.addLayout(row)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Input", "Action", ""])
        self.table.verticalHeader().hide()
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setItemDelegateForColumn(0, ChordDelegate(self.table))
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(2, 42)
        self.table.setMinimumHeight(205)
        self.table.setMaximumHeight(296)
        self.table.itemSelectionChanged.connect(self.highlight_row)
        layout.addWidget(self.table, 1)
        group = QGroupBox("Analog stick")
        form = QFormLayout(group)
        form.setSpacing(6)
        self.axis_combos, self.axis_scales = [], []
        for axis, name in enumerate(("Horizontal", "Vertical")):
            row = QHBoxLayout()
            combo = QComboBox()
            for title, value in (("Turn", "analog_turning"), ("Move", "analog_moving"), ("Strafe", "analog_strafing"), ("Disabled", "")):
                combo.addItem(title, value)
            combo.currentIndexChanged.connect(lambda index, axis=axis, combo=combo: self.set_axis(axis, "Axes", quote(combo.currentData() or "")))
            scale = QSpinBox()
            scale.setRange(-131072, 131072)
            scale.setSingleStep(4096)
            scale.setToolTip("65536 is the default sensitivity. Negative values invert the axis.")
            scale.valueChanged.connect(lambda value, axis=axis: self.set_axis(axis, "Scale", value))
            row.addWidget(combo, 1)
            row.addWidget(label("Sensitivity"))
            row.addWidget(scale)
            self.axis_combos.append(combo)
            self.axis_scales.append(scale)
            form.addRow(name, row)
        layout.addWidget(group)
        footer = QHBoxLayout()
        self.apply_status = label("Apply saves the CFG. Restart the game afterward.", "Muted", True)
        footer.addWidget(self.apply_status, 1)
        self.apply_button = QPushButton("Apply controls")
        self.apply_button.setObjectName("Accent")
        self.apply_button.setToolTip("Save the current CFG, including button mappings and analog settings.")
        self.apply_button.clicked.connect(self.apply_requested.emit)
        footer.addWidget(self.apply_button)
        layout.addLayout(footer)
        self.reload_profiles()

    def refresh(self, doc, scheme, eboot=None):
        self.refreshing = True
        self.doc, self.scheme = doc, scheme
        try:
            if doc.to_bytes() != self.applied_bytes:
                self.show_apply_status(False)
            selected = self.table.currentRow()
            self.scheme_combo.setCurrentIndex(self.scheme_combo.findData(scheme))
            for axis in range(2):
                values = tokens(doc.get("Controls", f"JoystickAnalogAxes{axis}", '""'))
                value = values[0] if values else ""
                combo = self.axis_combos[axis]
                index = combo.findData(value)
                if index < 0:
                    combo.addItem(value, value)
                    index = combo.count() - 1
                combo.setCurrentIndex(index)
                self.axis_scales[axis].setValue(doc.number("Controls", f"JoystickAnalogScale{axis}", 65536))
            self.mappings = read_mappings(doc, scheme)
            # Qt defers deletion of replaced cell widgets. Hide them first so
            # reloading a smaller preset cannot leave floating input controls.
            for row in range(self.table.rowCount()):
                for column in (1, 2):
                    widget = self.table.cellWidget(row, column)
                    if widget:
                        widget.hide()
                        self.table.removeCellWidget(row, column)
            self.table.setRowCount(len(self.mappings))
            self.control_combos.clear()
            for row, mapping in enumerate(self.mappings):
                item = QTableWidgetItem(chord_text(mapping.buttons))
                item.setData(Qt.ItemDataRole.UserRole, list(mapping.buttons))
                item.setToolTip(chord_text(mapping.buttons))
                self.table.setItem(row, 0, item)
                combo = QComboBox()
                for action in game_actions():
                    if action != "Show_Console":
                        combo.addItem(ACTION_LABELS.get(action, action.replace("_", " ")), action)
                combo.setCurrentIndex(combo.findData(mapping.action))
                combo.currentIndexChanged.connect(lambda index, row=row, combo=combo: self.change_action(row, combo.currentData()))
                self.table.setCellWidget(row, 1, combo)
                if len(mapping.buttons) == 1:
                    self.control_combos[mapping.buttons[0]] = combo
                trash = QToolButton()
                trash.setIcon(icon("trash"))
                trash.setObjectName("DeleteMapping")
                trash.setToolTip("Delete " + chord_text(mapping.buttons))
                trash.setAccessibleName("Delete " + chord_text(mapping.buttons))
                trash.clicked.connect(lambda checked=False, row=row: self.delete_mapping(row))
                self.table.setCellWidget(row, 2, trash)
                self.table.setRowHeight(row, 32)
            self.table.setIconSize(QSize(22, 22))
            self.table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            if 0 <= selected < len(self.mappings):
                self.table.selectRow(selected)
            native = has_native_mappings(doc)
            incompatible = native and eboot is not None and not eboot.native_controls
            self.notice.setText("Select the updated EBOOT to use these mappings." if incompatible else "")
            self.notice.setVisible(incompatible)
        finally:
            self.refreshing = False

    def show_apply_status(self, saved):
        self.applied_bytes = self.doc.to_bytes() if saved and self.doc else None
        self.apply_status.setObjectName("BuildResult" if saved else "Muted")
        self.apply_status.setText("Controls saved. Restart the game." if saved else "Apply saves the CFG. Restart the game afterward.")
        self.apply_status.style().unpolish(self.apply_status)
        self.apply_status.style().polish(self.apply_status)

    def set_axis(self, axis, kind, value):
        if not self.refreshing:
            self.edit_requested.emit(lambda doc: doc.set("Controls", f"JoystickAnalog{kind}{axis}", value))

    def apply_mappings(self, mappings):
        self.selected_profile = ""
        self.profile_combo.blockSignals(True)
        self.profile_combo.setCurrentIndex(0)
        self.profile_combo.blockSignals(False)
        self.profile_changed()
        self.edit_requested.emit(lambda doc: write_mappings(doc, mappings))

    def change_action(self, row, action):
        if self.refreshing or not action:
            return
        mappings = list(self.mappings)
        mappings[row] = Mapping(mappings[row].buttons, action)
        self.apply_mappings(mappings)

    def delete_mapping(self, row):
        self.apply_mappings([m for i, m in enumerate(self.mappings) if i != row])

    def add_mapping(self):
        dialog = CaptureDialog(game_actions(), parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.mapping:
            self.apply_mappings([*self.mappings, dialog.mapping])

    def select_button(self, name):
        self.controller.highlight(name)
        if name == "analog":
            self.axis_combos[0].setFocus()
        for row, mapping in enumerate(self.mappings):
            if mapping.buttons == (name,):
                self.table.selectRow(row)
                self.table.scrollToItem(self.table.item(row, 0))
                self.table.cellWidget(row, 1).setFocus()
                break

    def highlight_row(self):
        row = self.table.currentRow()
        if 0 <= row < len(self.mappings):
            pressed = self.mappings[row].buttons
            for name, button in self.controller.buttons.items():
                button.setChecked(name in pressed)

    def scheme_changed(self):
        if not self.refreshing:
            self.scheme_selected.emit(self.scheme_combo.currentData())

    def restore_defaults(self):
        template = default_document(self.scheme)
        def change(doc):
            write_mappings(doc, read_mappings(template, self.scheme))
            for axis in range(2):
                for kind in ("Axes", "Scale"):
                    key = f"JoystickAnalog{kind}{axis}"
                    doc.set("Controls", key, template.get("Controls", key))
        self.edit_requested.emit(change)

    def reload_profiles(self):
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        self.profile_combo.addItem("Custom", "")
        try:
            for name in self.store.load():
                self.profile_combo.addItem(name, name)
        except ConfigError as ex:
            self.profile_combo.setToolTip(str(ex))
        self.profile_combo.setCurrentIndex(max(0, self.profile_combo.findData(self.selected_profile)))
        self.delete_profile_button.setEnabled(bool(self.profile_combo.currentData()))
        self.load_profile_button.setEnabled(bool(self.profile_combo.currentData()))
        self.profile_combo.blockSignals(False)

    def profile_changed(self):
        selected = bool(self.profile_combo.currentData())
        self.load_profile_button.setEnabled(selected)
        self.delete_profile_button.setEnabled(selected)

    def load_profile(self):
        name = self.profile_combo.currentData()
        if not name or self.doc is None:
            return
        try:
            updated = self.doc.clone()
            scheme = self.store.apply(name, updated)
            self.selected_profile = name
            self.scheme_selected.emit(scheme)
            self.edit_requested.emit(lambda doc: self.store.apply(name, doc))
            self.delete_profile_button.setEnabled(True)
        except (ConfigError, KeyError) as ex:
            QMessageBox.warning(self, "Control preset", str(ex))

    def save_profile(self):
        name, accepted = QInputDialog.getText(self, "Save control preset", "Name", text=self.selected_profile)
        if not accepted:
            return
        try:
            self.selected_profile = self.store.save(name, self.doc, self.scheme)
            self.reload_profiles()
            self.preset_saved.emit(self.selected_profile)
        except ConfigError as ex:
            QMessageBox.warning(self, "Control preset", str(ex))

    def delete_profile(self):
        name = self.profile_combo.currentData()
        if name:
            self.store.remove(name)
            self.selected_profile = ""
            self.reload_profiles()
