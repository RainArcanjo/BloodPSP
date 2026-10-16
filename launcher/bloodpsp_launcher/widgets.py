"""Project artwork, PSP button assets and Qt configuration editors."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QRectF
from PySide6.QtGui import QPainter, QPixmap, QIcon
from PySide6.QtWidgets import (QApplication, QStyle, QFrame, QToolButton, QWidget,
    QHBoxLayout, QLabel, QStyledItemDelegate, QSpinBox, QLineEdit, QComboBox)
from PySide6.QtSvg import QSvgRenderer  # also ensures SVG support in frozen builds
from .resources import resource


def icon(name: str, color: str = "", size: int = 24) -> QIcon:
    if name == "blood":
        return QIcon(str(resource("assets/blood-icon.png")))
    standard = {"folder": QStyle.StandardPixmap.SP_DirOpenIcon,
                "save": QStyle.StandardPixmap.SP_DialogSaveButton,
                "download": QStyle.StandardPixmap.SP_ArrowDown,
                "info": QStyle.StandardPixmap.SP_MessageBoxInformation}
    return QApplication.style().standardIcon(standard.get(name, QStyle.StandardPixmap.SP_FileIcon))


def button_icon(name: str) -> QIcon:
    path = resource("assets/buttons/" + name + ".svg")
    if not path.is_file():
        path = path.with_suffix(".png")
    return QIcon(str(path))


def label(text: str, role: str = "", wrap: bool = False) -> QLabel:
    widget = QLabel(text)
    widget.setObjectName(role)
    widget.setWordWrap(wrap)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    return widget


def button_label(name: str, title: str, scheme: str) -> QWidget:
    container = QWidget()
    row = QHBoxLayout(container)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(5)
    names = (["l", "r", "cross"] if scheme == "current" else ["l", "triangle"]) if name == "secondary" else ["l", "square"] if name == "run" else [name]
    for i, key in enumerate(names):
        if i:
            row.addWidget(label("+"))
        image = QLabel()
        image.setPixmap(button_icon(key).pixmap(22, 22))
        image.setFixedSize(24, 24)
        row.addWidget(image)
    if len(names) == 1:
        row.addWidget(label(title))
    container.setToolTip(title)
    row.addStretch()
    return container


class ControllerCanvas(QFrame):
    selected = Signal(str)

    def __init__(self):
        super().__init__()
        self.setFixedHeight(184)
        self.setMinimumWidth(500)
        self.artwork = QPixmap(str(resource("assets/psp.png")))
        self.current = ""
        self.buttons = {}
        self.positions = {
            "up": (146, 128, 34, 34), "left": (111, 164, 34, 34),
            "down": (147, 198, 34, 34), "right": (179, 164, 34, 34),
            "triangle": (659, 127, 34, 34), "square": (620, 164, 34, 34),
            "cross": (658, 202, 34, 34), "circle": (696, 164, 34, 34),
            "l": (150, 47, 86, 24), "r": (650, 47, 86, 24),
            "select": (541, 302, 38, 23), "start": (583, 302, 38, 23),
            "analog": (147, 257, 49, 49),
        }
        for name in self.positions:
            button = QToolButton(self)
            button.setObjectName("PspButton")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setAccessibleName(name.title())
            button.setToolTip("Start: game menu (fixed)" if name == "start" else "Edit " + name.title())
            button.clicked.connect(lambda checked=False, name=name: self.selected.emit(name))
            self.buttons[name] = button

    def highlight(self, name: str) -> None:
        self.current = name
        for key, button in self.buttons.items():
            button.setChecked(name == key)

    def image_rect(self):
        scale = min(self.width() / 813, self.height() / 355)
        return scale, (self.width() - 813 * scale) / 2, (self.height() - 355 * scale) / 2

    def resizeEvent(self, event):
        scale, left, top = self.image_rect()
        for name, (x, y, width, height) in self.positions.items():
            self.buttons[name].setGeometry(round(left + (x - width / 2) * scale), round(top + (y - height / 2) * scale), round(width * scale), round(height * scale))
        super().resizeEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        scale, left, top = self.image_rect()
        painter.drawPixmap(QRectF(left, top, 813 * scale, 355 * scale), self.artwork, QRectF(self.artwork.rect()))
        painter.end()


class ValueDelegate(QStyledItemDelegate):
    def __init__(self, boolean_fields: set[tuple[str, str]], parent=None):
        super().__init__(parent)
        self.boolean_fields = boolean_fields

    def createEditor(self, parent, option, index):
        if index.column() != 1 or not index.data(Qt.ItemDataRole.UserRole):
            return None
        section, key = index.data(Qt.ItemDataRole.UserRole)
        value = index.data(Qt.ItemDataRole.EditRole)
        if (section, key) in self.boolean_fields and value in ("0", "1"):
            editor = QComboBox(parent)
            editor.addItems(["0 — Off", "1 — On"])
            return editor
        try:
            int(value)
            editor = QSpinBox(parent)
            editor.setRange(-2147483648, 2147483647)
            return editor
        except (ValueError, TypeError):
            return QLineEdit(parent)

    def setEditorData(self, editor, index):
        value = index.data(Qt.ItemDataRole.EditRole)
        if isinstance(editor, QComboBox):
            editor.setCurrentIndex(int(value))
        elif isinstance(editor, QSpinBox):
            editor.setValue(int(value))
        else:
            editor.setText(value)

    def setModelData(self, editor, model, index):
        if isinstance(editor, QComboBox):
            value = str(editor.currentIndex())
        elif isinstance(editor, QSpinBox):
            value = str(editor.value())
        else:
            value = editor.text()
        model.setData(index, value, Qt.ItemDataRole.EditRole)
