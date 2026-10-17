from __future__ import annotations

import time
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QComboBox, QLabel, QPushButton, QDialogButtonBox, QWidget, QStackedWidget)

from .controls import ACTION_LABELS
from .mappings import ChordCapture, Mapping, BUTTONS, chord, chord_text
from .widgets import ControllerCanvas, ChordPreview, label


class CaptureDialog(QDialog):
    def __init__(self, available_actions, initial_action="Jump", parent=None, reader=None):
        super().__init__(parent)
        self.setWindowTitle("Map button")
        self.setMinimumWidth(620)
        self.setModal(True)
        self.mapping = None
        self.capture = ChordCapture()
        self.reader = reader
        self.manual_buttons = set()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)
        form = QFormLayout()
        self.action_combo = QComboBox()
        for action in available_actions:
            if action != "Show_Console":
                self.action_combo.addItem(ACTION_LABELS.get(action, action.replace("_", " ")), action)
        self.action_combo.setCurrentIndex(max(0, self.action_combo.findData(initial_action)))
        form.addRow("Action", self.action_combo)
        self.input_combo = QComboBox()
        self.input_combo.addItems(["Connected controller", "On-screen buttons"])
        self.input_combo.currentIndexChanged.connect(self.mode_changed)
        form.addRow("Input", self.input_combo)
        layout.addLayout(form)
        self.device_label = label("Connecting controller…", "Muted")
        layout.addWidget(self.device_label)
        self.preview = ChordPreview("Press a button or combination")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumHeight(62)
        layout.addWidget(self.preview)
        self.canvas = ControllerCanvas()
        self.canvas.setFixedHeight(230)
        self.canvas.selected.connect(self.manual_clicked)
        for name, button in self.canvas.buttons.items():
            button.setEnabled(name in BUTTONS)
        layout.addWidget(self.canvas)
        self.hint = label("Hold buttons together, then release all to confirm.", "Muted", True)
        layout.addWidget(self.hint)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        buttons.rejected.connect(self.reject)
        self.use_button = buttons.addButton("Use selection", QDialogButtonBox.ButtonRole.AcceptRole)
        self.use_button.clicked.connect(self.accept_manual)
        self.use_button.hide()
        layout.addWidget(buttons)
        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self.poll)
        self.finished.connect(self.cleanup)
        if self.reader is None:
            try:
                from .gamepad import GamepadReader
                self.reader = GamepadReader()
            except Exception as ex:
                self.device_label.setText("Controller unavailable. Select on-screen buttons.")
                self.device_label.setToolTip(str(ex))
        self.timer.start()

    def mode_changed(self, index):
        self.capture.reset()
        self.manual_buttons.clear()
        self.canvas.highlight("")
        self.preview.setText("Press a button or combination" if index == 0 else "Select buttons on the PSP")
        self.use_button.setVisible(index == 1)
        self.use_button.setEnabled(False)
        self.hint.setText("Hold buttons together, then release all to confirm." if index == 0 else "Select one or more buttons, then choose Use selection.")
        self.device_label.setVisible(index == 0)

    def poll(self):
        if self.input_combo.currentIndex() != 0 or self.reader is None:
            return
        try:
            pressed = self.reader.poll()
        except Exception as ex:
            self.capture.reset()
            self.device_label.setText("Controller disconnected. Reconnect or use on-screen buttons.")
            self.device_label.setToolTip(str(ex))
            return
        self.device_label.setText(self.reader.name)
        if pressed is None:
            self.capture.reset()
            return
        result = self.capture.update(pressed, time.monotonic() * 1000)
        for name, button in self.canvas.buttons.items():
            button.setChecked(name in pressed)
        if self.capture.candidate:
            self.preview.set_buttons(chord(self.capture.candidate))
        if result:
            self.mapping = Mapping(result, self.action_combo.currentData())
            self.accept()

    def manual_clicked(self, name):
        if self.input_combo.currentIndex() != 1:
            return
        if name in self.manual_buttons:
            self.manual_buttons.remove(name)
        else:
            self.manual_buttons.add(name)
        for key, button in self.canvas.buttons.items():
            button.setChecked(key in self.manual_buttons)
        if self.manual_buttons:
            self.preview.set_buttons(chord(self.manual_buttons))
        else:
            self.preview.setText("Select buttons on the PSP")
        self.use_button.setEnabled(bool(self.manual_buttons))

    def accept_manual(self):
        if self.manual_buttons:
            self.mapping = Mapping(chord(self.manual_buttons), self.action_combo.currentData())
            self.accept()

    def cleanup(self, unused=0):
        self.timer.stop()
        if self.reader:
            self.reader.close()
            self.reader = None
